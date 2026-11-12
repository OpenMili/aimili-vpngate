from __future__ import annotations

from html import escape
import unittest
from urllib.parse import parse_qs, urlsplit

import official_web
import snapshot_utils


def table_row(ip="8.8.8.8", country="CA", hostname="vpn123.opengw.net", link=None):
    link = link or (f"do_openvpn.aspx?fqdn={hostname}&ip={ip}"
                    "&tcp=443&udp=1194&sid=123&hid=456")
    return (f'<tr><td><img src="../images/flags/{country}.png">'
            f'{"Canada" if country == "CA" else "Japan"}</td>'
            f'<td>{hostname}</td><td>12 sessions</td><td>20.50 Mbps Ping: 18 ms</td>'
            f'<td><a href="{escape(link)}">Config file</a></td><td>1,234</td></tr>')


def profile(ip="8.8.8.8", port=443, proto="tcp", extra=""):
    return (f"client\ndev tun\nproto {proto}\nremote {ip} {port}\n{extra}"
            "<ca>\nCA\n</ca>\n<cert>\nCERT\n</cert>\n<key>\nKEY\n</key>\n")


class OfficialWebTests(unittest.TestCase):
    def test_nested_table_keeps_each_country_attached_to_its_own_node(self):
        html = "<table><tr><td><table>" + table_row() + table_row(
            "1.1.1.1", "JP") + "</table></td></tr></table>"
        nodes = official_web.parse_servers(html)
        self.assertEqual([("8.8.8.8", "CA"), ("1.1.1.1", "JP")],
                         [(n["ip"], n["country_short"]) for n in nodes])
        self.assertEqual((1234, 18, 20500000, 12),
                         tuple(nodes[0][k] for k in ("score", "ping", "speed", "sessions")))

    def test_untrusted_links_and_nonpublic_endpoints_are_ignored(self):
        html = table_row(link="https://evil.example/en/do_openvpn.aspx?ip=8.8.8.8")
        html += table_row("127.0.0.1") + table_row("10.0.0.1")
        html += table_row(link="http://www.vpngate.net/en/do_openvpn.aspx?ip=8.8.8.8")
        html += table_row(link="do_openvpn.aspx?fqdn=x&ip=8.8.8.8&tcp=443&udp=0&sid=x&hid=4")
        self.assertEqual([], official_web.parse_servers(html))

    def test_profile_cannot_change_remote_execute_programs_or_change_transport(self):
        node = official_web.parse_servers(table_row())[0]
        for text in (profile("1.1.1.1"), profile("127.0.0.1"), profile(port=444),
                     profile(proto="udp"), profile(extra="up /tmp/payload\n"),
                     profile(extra="remote 1.1.1.1 443\n")):
            with self.subTest(text=text), self.assertRaises(ValueError):
                official_web.validate_profile(text, node, "tcp")

    def test_failed_tcp_download_can_fall_back_to_valid_udp_profile(self):
        requested = []

        def fetch(url):
            requested.append(url)
            if url in official_web.PAGE_URLS:
                return table_row()
            parsed = urlsplit(url)
            self.assertEqual("https", parsed.scheme)
            self.assertEqual("www.vpngate.net", parsed.netloc)
            query = parse_qs(parsed.query)
            if "tcp" in query:
                return "<html>download unavailable</html>"
            return profile(port=1194, proto="udp")

        result = official_web.fetch_snapshot(fetch)
        rows = snapshot_utils.parse_and_validate_snapshot(result)
        self.assertEqual(1, len(rows))
        self.assertEqual("CA", rows[0]["CountryShort"])
        self.assertEqual(4, len(requested))  # Two table pages, one TCP, one UDP.

    def test_failed_page_does_not_discard_other_page_and_limits_downloads(self):
        downloads = []

        def fetch(url):
            if url == official_web.PAGE_URLS[0]:
                raise TimeoutError("page unavailable")
            if url == official_web.PAGE_URLS[1]:
                return table_row() + table_row("1.1.1.1", "JP")
            query = parse_qs(urlsplit(url).query)
            downloads.append(query["host"][0])
            return profile(query["host"][0])

        rows = snapshot_utils.parse_and_validate_snapshot(
            official_web.fetch_snapshot(fetch, max_nodes=1))
        self.assertEqual(["8.8.8.8"], downloads)
        self.assertEqual("CA", rows[0]["CountryShort"])

    def test_all_failed_downloads_cannot_produce_an_empty_successful_snapshot(self):
        def fetch(url):
            return table_row() if url in official_web.PAGE_URLS else "not an OpenVPN profile"

        with self.assertRaises(ValueError):
            official_web.fetch_snapshot(fetch)


if __name__ == "__main__":
    unittest.main()
