"""Obtain candidate profiles from VPNGate's official HTTPS server table.

The table is partial. Its country labels describe candidates, not verified exits.
No URL supplied by a relay is fetched; download URLs are built for the official
host using validated numeric table fields.
"""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
import csv
from html.parser import HTMLParser
import io
import ipaddress
import re
import shlex
from typing import Callable
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

import snapshot_utils

PAGE_URLS = ("https://www.vpngate.net/en/", "https://www.vpngate.net/cn/")
SOURCE_URL = PAGE_URLS[0]
OFFICIAL_HOST = "www.vpngate.net"


class ServerTable(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.rows = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "tr":
            self.stack.append({"links": [], "flags": [], "text": []})
        for row in self.stack:
            if tag == "a":
                href = attrs.get("href", "")
                if "do_openvpn.aspx" in href:
                    row["links"].append(href)
            elif tag == "img":
                flag = re.search(r"/images/flags/([A-Z]{2})\.png$", attrs.get("src", ""))
                if flag:
                    row["flags"].append(flag[1])

    def handle_data(self, data):
        if data.strip():
            for row in self.stack:
                row["text"].append(data.strip())

    def handle_endtag(self, tag):
        if tag == "tr" and self.stack:
            row = self.stack.pop()
            if len(row["links"]) == len(row["flags"]) == 1:
                self.rows.append(row)


def parse_servers(html: str) -> list[dict]:
    if len(html.encode("utf-8")) > snapshot_utils.MAX_SNAPSHOT_BYTES:
        raise ValueError("Official server table exceeds the size limit")
    parser = ServerTable()
    parser.feed(html)
    nodes = []
    seen = set()
    for row in parser.rows:
        try:
            link = urlsplit(urljoin(SOURCE_URL, row["links"][0]))
            if (link.scheme != "https" or link.netloc != OFFICIAL_HOST
                    or link.path not in ("/en/do_openvpn.aspx", "/cn/do_openvpn.aspx")):
                continue
            query = parse_qs(link.query, strict_parsing=True)
            if any(len(values) != 1 for values in query.values()):
                continue
            ip = str(ipaddress.ip_address(query["ip"][0]))
            if not ipaddress.ip_address(ip).is_global or ip in seen:
                continue
            tcp, udp = int(query["tcp"][0]), int(query["udp"][0])
            if not (0 <= tcp <= 65535 and 0 <= udp <= 65535 and (tcp or udp)):
                continue
            sid, hid = query["sid"][0], query["hid"][0]
            if not all(re.fullmatch(r"[0-9]{1,24}", value) for value in (sid, hid)):
                continue
            hostname = query["fqdn"][0]
            if not re.fullmatch(r"[A-Za-z0-9.-]{1,253}", hostname):
                continue
            text = " ".join(row["text"])
            ping = re.search(r"Ping:\s*([0-9]+)\s*ms", text)
            speed = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*Mbps", text)
            sessions = re.search(r"([0-9,]+)\s*sessions", text)
            score = row["text"][-1].replace(",", "")
            nodes.append({
                "ip": ip, "hostname": hostname, "tcp": tcp, "udp": udp,
                "sid": sid, "hid": hid, "country_short": row["flags"][0],
                "country_long": row["text"][0],
                "score": int(score) if score.isdigit() else 0,
                "ping": int(ping[1]) if ping else 0,
                "speed": int(float(speed[1]) * 1000000) if speed else 0,
                "sessions": int(sessions[1].replace(",", "")) if sessions else 0,
            })
            seen.add(ip)
        except (ValueError, KeyError, IndexError):
            continue
    return nodes


def profile_url(node: dict, proto: str) -> str:
    if proto not in ("tcp", "udp"):
        raise ValueError("Unsupported OpenVPN transport")
    # All fields come from parse_servers, never a relay-supplied URL.
    query = urlencode({"sid": node["sid"], proto: 1, "host": node["ip"],
                       "port": node[proto], "hid": node["hid"]})
    return f"https://{OFFICIAL_HOST}/common/openvpn_download.aspx?{query}"


def validate_profile(text: str, node: dict, proto: str) -> None:
    snapshot_utils.validate_openvpn_config(text)
    remotes = []
    protocols = []
    block = False
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("<"):
            block = not line.startswith("</")
            continue
        if block or not line or line.startswith(("#", ";")):
            continue
        args = shlex.split(line, comments=True)
        directive = args[0].lstrip("-").lower()
        if directive == "remote":
            remotes.append(args[1:])
        elif directive == "proto":
            protocols.append(args[1:])
    allowed = {"tcp": {"tcp", "tcp-client", "tcp4-client", "tcp6-client"},
               "udp": {"udp", "udp4", "udp6"}}[proto]
    if len(remotes) != 1 or len(protocols) != 1 or len(protocols[0]) != 1:
        raise ValueError("Official profile must have one explicit remote and protocol")
    remote = remotes[0]
    if (len(remote) not in (2, 3) or str(ipaddress.ip_address(remote[0])) != node["ip"]
            or int(remote[1]) != node[proto] or protocols[0][0] not in allowed
            or (len(remote) == 3 and remote[2] not in allowed)):
        raise ValueError("Downloaded profile does not match its advertised endpoint")


def fetch_snapshot(fetch_text: Callable[[str], str], *, max_nodes: int = 100,
                   preferred_countries=()) -> str:
    nodes = {}
    errors = []
    for page in PAGE_URLS:
        try:
            for node in parse_servers(fetch_text(page)):
                nodes.setdefault(node["ip"], node)
        except Exception as exc:
            errors.append(str(exc))
    preferred = {"CA", "US", *preferred_countries}
    ordered = sorted(nodes.values(), key=lambda n: (n["country_short"] not in preferred,
                                                   -n["score"], n["ip"]))
    # Keep a mix of countries when a large country dominates the partial table.
    first_per_country = {}
    for node in ordered:
        first_per_country.setdefault(node["country_short"], node)
    first_ips = {node["ip"] for node in first_per_country.values()}
    ordered = list(first_per_country.values()) + [n for n in ordered if n["ip"] not in first_ips]
    ordered = ordered[:max(1, min(300, max_nodes))]

    def download(node):
        for proto in ("tcp", "udp"):
            if not node[proto]:
                continue
            try:
                text = fetch_text(profile_url(node, proto))
                validate_profile(text, node, proto)
                return {
                    "HostName": node["hostname"], "IP": node["ip"], "Score": node["score"],
                    "Ping": node["ping"], "Speed": node["speed"],
                    "CountryLong": node["country_long"], "CountryShort": node["country_short"],
                    "NumVpnSessions": node["sessions"],
                    "OpenVPN_ConfigData_Base64": base64.b64encode(text.encode()).decode("ascii"),
                }
            except Exception:
                continue
        return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = [row for row in pool.map(download, ordered) if row is not None]
    if not rows:
        raise ValueError("Official HTTPS pages supplied no valid OpenVPN candidates"
                         + (": " + "; ".join(errors) if errors else ""))
    output = io.StringIO()
    fields = ["HostName", "IP", "Score", "Ping", "Speed", "CountryLong", "CountryShort",
              "NumVpnSessions", "OpenVPN_ConfigData_Base64"]
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    result = output.getvalue()
    snapshot_utils.parse_and_validate_snapshot(result)
    return result
