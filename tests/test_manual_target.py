from __future__ import annotations

import contextlib
import http.client
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import threading
import time
import unittest
import urllib.request
from unittest import mock

import manual_target
import proxy_server
import proxyctl
from test_manager_logic import FakeProcess, manager
import test_manager_logic as fixtures


def registry() -> list[dict]:
    return [
        {"id": "jp-a", "ip": "198.51.100.1", "country_short": "JP", "proto": "udp",
         "remote_port": 1194, "latency_ms": 40, "probe_status": "available", "score": 100},
        {"id": "jp-b", "ip": "198.51.100.2", "country_short": "JP", "proto": "tcp",
         "remote_port": 443, "latency_ms": 10, "probe_status": "available", "score": 20},
        {"id": "us-a", "ip": "198.51.100.3", "country_short": "US", "latency_ms": 1,
         "probe_status": "available", "score": 1000},
    ]


class TargetResolutionTests(unittest.TestCase):
    def test_ip_locks_registered_node_and_clears_previous_country(self):
        node_id, policy = manual_target.resolve_target(registry(), {"mode": "ip", "ip": "198.51.100.1"})
        self.assertEqual("jp-a", node_id)
        self.assertEqual("fixed_ip", policy["routing_mode"])
        self.assertEqual(node_id, policy["fixed_node_id"])
        self.assertEqual("", policy["force_country"])
        self.assertEqual([], policy["force_countries"])

    def test_ambiguous_ip_requires_id_and_returns_only_public_metadata(self):
        nodes = registry()
        nodes.append({**nodes[0], "id": "jp-a-tcp", "proto": "tcp", "config_text": "private-key", "config_file": "/private/path"})
        with self.assertRaises(manual_target.TargetError) as error:
            manual_target.resolve_target(nodes, {"mode": "ip", "ip": "198.51.100.1"})
        self.assertEqual(409, error.exception.status)
        self.assertEqual(2, len(error.exception.candidates))
        self.assertNotIn("private", json.dumps(error.exception.candidates))
        node_id, _ = manual_target.resolve_target(nodes, {"mode": "ip", "ip": "198.51.100.1", "node_id": "jp-a-tcp"})
        self.assertEqual("jp-a-tcp", node_id)

    def test_country_never_chooses_faster_node_in_another_country(self):
        node_id, policy = manual_target.resolve_target(registry(), {"mode": "country", "country": "jp"})
        self.assertEqual("jp-b", node_id)
        self.assertEqual("fixed_region", policy["routing_mode"])
        self.assertEqual("JP", policy["force_country"])

    def test_country_rejects_absent_or_all_unavailable_candidates(self):
        for nodes in (registry(), [{**node, "probe_status": "unavailable"} for node in registry()]):
            with self.assertRaises(manual_target.TargetError) as error:
                manual_target.resolve_target(nodes, {"mode": "country", "country": "DE" if nodes[0]["probe_status"] == "available" else "JP"})
            self.assertEqual(503, error.exception.status)

    def test_unprobed_node_does_not_beat_an_available_node(self):
        nodes = registry()
        nodes[1].update(probe_status="not_checked", latency_ms=1)
        self.assertEqual("jp-a", manual_target.resolve_target(nodes, {"mode": "country", "country": "JP"})[0])

    def test_multiple_countries_choose_only_within_the_union(self):
        nodes = [
            {"id": "us", "country_short": "US", "probe_status": "unavailable", "latency_ms": 5},
            {"id": "ca", "country_short": "CA", "probe_status": "available", "latency_ms": 50},
            {"id": "jp", "country_short": "JP", "probe_status": "available", "latency_ms": 1},
        ]
        node_id, policy = manual_target.resolve_target(nodes, {"mode": "country", "countries": ["us", "CA", "US"]})
        self.assertEqual("ca", node_id)
        self.assertEqual(["CA", "US"], policy["force_countries"])
        self.assertEqual("", policy["force_country"])
        for invalid in ([], "US,CA", ["US", "Canada"], [None], ["US"] * 251):
            with self.subTest(invalid=invalid), self.assertRaises(manual_target.TargetError):
                manual_target.resolve_target(nodes, {"mode": "country", "countries": invalid})
        with self.assertRaises(manual_target.TargetError):
            manual_target.resolve_target(nodes, {"mode": "country", "country": "US", "countries": ["CA"]})

    def test_multiple_country_policy_edits_invalidate_an_inflight_switch(self):
        config = {"routing_mode": "fixed_region", "force_countries": ["US", "CA"]}
        before = manual_target.routing_signature(config)
        config["force_countries"] = ["CA", "US"]
        self.assertEqual(before, manual_target.routing_signature(config))
        config["force_countries"] = ["US", "JP"]
        self.assertNotEqual(before, manual_target.routing_signature(config))

    def test_invalid_or_mixed_selectors_cannot_become_arbitrary_endpoints(self):
        for payload in (
            {"mode": "ip", "ip": "https://example.com"},
            {"mode": "ip", "ip": "example.com"},
            {"mode": "ip", "ip": "198.51.100.1", "country": "JP"},
            {"mode": "country", "country": "Japan"},
            {"mode": "country", "country": "JP", "node_id": "jp-a"},
            {"mode": "ip", "ip": "198.51.100.1", "node_id": ""},
            {"mode": "other"}, [],
        ):
            with self.subTest(payload=payload), self.assertRaises(manual_target.TargetError):
                manual_target.resolve_target(registry(), payload)

    def test_ipv6_matching_is_canonical_and_unknown_ip_is_rejected(self):
        nodes = [{"id": "ipv6", "ip": "2001:db8::1"}]
        self.assertEqual("ipv6", manual_target.resolve_target(nodes, {"mode": "ip", "ip": "2001:0db8:0:0:0:0:0:1"})[0])
        with self.assertRaises(manual_target.TargetError) as error:
            manual_target.resolve_target(nodes, {"mode": "ip", "ip": "198.51.100.99"})
        self.assertEqual(404, error.exception.status)


class ManualConnectionTests(unittest.TestCase):
    setUp = fixtures.ManagerLogicTests.setUp
    tearDown = fixtures.ManagerLogicTests.tearDown
    write_nodes = fixtures.ManagerLogicTests.write_nodes

    def prepare(self, active=False):
        nodes = self.write_nodes(2)
        nodes[0]["country_short"] = "US"
        nodes[1]["country_short"] = "JP"
        if active:
            nodes[0]["active"] = True
            manager.active_openvpn_process = FakeProcess()
            manager.active_openvpn_node_id = nodes[0]["id"]
            manager.set_state(tunnel_ready=True, proxy_ready=True, proxy_ok=True, active_node_latency="10 ms")
        manager.write_json(manager.NODES_FILE, nodes)
        config = manager.load_ui_config()
        config.update(routing_mode="fixed_region", force_country="US")
        manager.write_json(manager.DATA_DIR / "ui_auth.json", config)
        return nodes

    def connection_mocks(self, health=None, startup=None):
        stack = contextlib.ExitStack()
        stack.enter_context(mock.patch.object(manager, "cleanup_policy_routing"))
        stack.enter_context(mock.patch.object(manager, "setup_policy_routing", return_value=True))
        stack.enter_context(mock.patch.object(manager.vpn_utils, "ping_latency_ms", return_value=10))
        stack.enter_context(mock.patch.object(manager, "log_to_json"))
        stack.enter_context(mock.patch.object(manager, "check_proxy_health", side_effect=health or (lambda: {"ok": True, "ip": "203.0.113.1", "latency_ms": 10})))
        stack.enter_context(mock.patch.object(manager, "run_openvpn_until_ready", side_effect=startup or (lambda *a, **kw: (True, "ready", FakeProcess()))))
        self.addCleanup(stack.close)

    def test_success_switches_and_persists_fixed_target_in_one_operation(self):
        nodes = self.prepare()
        self.connection_mocks()
        manager.connect_node("", target={"mode": "ip", "ip": nodes[1]["ip"]})
        config = manager.load_ui_config()
        self.assertEqual("fixed_ip", config["routing_mode"])
        self.assertEqual(nodes[1]["id"], config["fixed_node_id"])
        self.assertEqual(nodes[1]["id"], manager.active_openvpn_node_id)
        self.assertTrue(manager.get_state()["proxy_ready"])

    def test_preflight_failure_keeps_previous_policy_connection_and_readiness(self):
        nodes = self.prepare(active=True)
        original = manager.active_openvpn_process
        self.connection_mocks(startup=lambda *a, **kw: (False, "offline", None))
        with self.assertRaisesRegex(RuntimeError, "预检失败"):
            manager.connect_node("", target={"mode": "ip", "ip": nodes[1]["ip"]})
        self.assertIs(original, manager.active_openvpn_process)
        self.assertTrue(original.running)
        self.assertEqual("US", manager.load_ui_config()["force_country"])
        self.assertTrue(manager.get_state()["proxy_ready"])
        self.assertTrue(manager.get_state()["proxy_ok"])

    def test_failure_after_switch_keeps_requested_pin_without_fallback(self):
        nodes = self.prepare(active=True)
        self.connection_mocks(health=lambda: {"ok": False, "error": "bad exit"})
        with mock.patch.object(manager, "auto_switch_node") as fallback:
            with self.assertRaisesRegex(RuntimeError, "代理出口不可用"):
                manager.connect_node("", target={"mode": "ip", "ip": nodes[1]["ip"]})
        fallback.assert_not_called()
        config = manager.load_ui_config()
        self.assertEqual(nodes[1]["id"], config["fixed_node_id"])
        self.assertEqual("", manager.active_openvpn_node_id)
        self.assertFalse(manager.get_state()["proxy_ready"])

    def test_config_edit_during_preflight_is_not_overwritten(self):
        nodes = self.prepare(active=True)
        original = manager.active_openvpn_process

        def startup(*args, **kwargs):
            config = manager.load_ui_config()
            config["force_country"] = "KR"
            manager.write_json(manager.DATA_DIR / "ui_auth.json", config)
            return True, "ready", None

        self.connection_mocks(startup=startup)
        with self.assertRaises(manager.ConnectionCancelled):
            manager.connect_node("", target={"mode": "country", "country": "JP"})
        self.assertEqual("KR", manager.load_ui_config()["force_country"])
        self.assertIs(original, manager.active_openvpn_process)

    def test_config_edit_during_verification_cannot_commit_old_target(self):
        self.prepare()

        def health():
            config = manager.load_ui_config()
            config.update(routing_mode="fixed_region", force_country="US")
            manager.write_json(manager.DATA_DIR / "ui_auth.json", config)
            return {"ok": True, "ip": "203.0.113.1", "latency_ms": 10}

        self.connection_mocks(health=health)
        with self.assertRaises(manager.ConnectionCancelled):
            manager.connect_node("", target={"mode": "country", "country": "JP"})
        self.assertEqual("US", manager.load_ui_config()["force_country"])
        self.assertFalse(manager.get_state()["proxy_ready"])
        self.assertEqual("", manager.active_openvpn_node_id)

    def test_second_request_is_rejected_while_first_switch_is_running(self):
        nodes = self.prepare()
        entered, resume = threading.Event(), threading.Event()
        errors = []

        def startup(*args, **kwargs):
            entered.set()
            if not resume.wait(2):
                raise AssertionError("test switch was not released")
            return True, "ready", FakeProcess()

        self.connection_mocks(startup=startup)

        def first():
            try:
                manager.connect_node("", target={"mode": "country", "country": "JP"})
            except Exception as exc:
                errors.append(exc)

        thread = threading.Thread(target=first)
        thread.start()
        try:
            self.assertTrue(entered.wait(2))
            with self.assertRaisesRegex(RuntimeError, "当前已有"):
                manager.connect_node("", target={"mode": "ip", "ip": nodes[0]["ip"]})
        finally:
            resume.set()
            thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual([], errors)
        self.assertEqual(nodes[1]["id"], manager.active_openvpn_node_id)

    def test_reselecting_active_node_keeps_config_available_for_restart(self):
        nodes = self.prepare(active=True)
        nodes[0]["probed_at"] = time.time()
        manager.write_json(manager.NODES_FILE, nodes)

        def startup(config_file, **kwargs):
            self.assertTrue(Path(config_file).is_file())
            self.assertEqual(nodes[0]["config_text"], Path(config_file).read_text())
            return True, "ready", FakeProcess()

        self.connection_mocks(startup=startup)
        manager.connect_node("", target={"mode": "ip", "ip": nodes[0]["ip"]})
        self.assertTrue(manager.get_state()["proxy_ready"])

    def test_fresh_auth_uses_random_path_and_saved_config_is_stable(self):
        first = manager.load_ui_config()
        self.assertEqual(first["secret_path"], manager.load_ui_config()["secret_path"])
        self.assertNotEqual("EJsW2EeBo9lY", first["secret_path"])
        (manager.DATA_DIR / "ui_auth.json").unlink()
        second = manager.load_ui_config()
        self.assertNotEqual(first["secret_path"], second["secret_path"])


class SaferDefaultsTests(unittest.TestCase):
    def test_dns_failure_never_calls_system_resolver_or_opens_socket(self):
        with (mock.patch.object(proxy_server, "resolve_dns_over_tun0", return_value=None),
              mock.patch.object(proxy_server.socket, "getaddrinfo") as resolver,
              mock.patch.object(proxy_server.socket, "socket") as factory):
            with self.assertRaises(socket.gaierror):
                proxy_server.create_connection(("audit.invalid", 443))
        resolver.assert_not_called()
        factory.assert_not_called()

    def test_successful_resolution_uses_numeric_address_flag_and_tunnel_binding(self):
        upstream = mock.Mock()
        address = (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("198.51.100.1", 443))
        with (mock.patch.object(proxy_server, "resolve_dns_over_tun0", return_value="198.51.100.1"),
              mock.patch.object(proxy_server.socket, "getaddrinfo", return_value=[address]) as resolver,
              mock.patch.object(proxy_server.socket, "socket", return_value=upstream)):
            self.assertIs(upstream, proxy_server.create_connection(("audit.invalid", 443)))
        resolver.assert_called_once_with("198.51.100.1", 443, 0, socket.SOCK_STREAM, flags=socket.AI_NUMERICHOST)
        upstream.setsockopt.assert_called_once_with(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, b"tun0")

    def test_incomplete_or_explicitly_empty_credentials_are_rejected(self):
        for env in ({"LOCAL_PROXY_USER": "user"}, {"LOCAL_PROXY_PASS": "password"},
                    {"LOCAL_PROXY_USER": "", "LOCAL_PROXY_PASS": ""}):
            with self.subTest(env=env), mock.patch.dict(os.environ, env, clear=True):
                with self.assertRaises(ValueError):
                    proxy_server.get_proxy_credentials()
        with mock.patch.dict(os.environ, {"LOCAL_PROXY_USER": "user", "LOCAL_PROXY_PASS": "password"}, clear=True):
            self.assertTrue(proxy_server.check_credentials("user", "password"))

    def test_http_sources_require_explicit_opt_in(self):
        with mock.patch.object(manager, "ALLOW_INSECURE_NODE_SOURCES", False):
            self.assertTrue(all(url.startswith("https://") for _, url in manager.api_network_sources()))
        with mock.patch.object(manager, "ALLOW_INSECURE_NODE_SOURCES", True):
            self.assertIn(manager.API_HTTP_URL, [url for _, url in manager.api_network_sources()])

    def test_https_fetch_refuses_redirect_to_plain_http(self):
        opener = mock.Mock()
        opener.open.return_value = io.BytesIO(b"snapshot")
        with (mock.patch.object(manager.vpn_utils, "get_upstream_proxy", return_value=(None, None, None)),
              mock.patch.object(manager.urllib.request, "build_opener", return_value=opener) as build):
            self.assertEqual("snapshot", manager.fetch_api_text("https://audit.invalid/"))
        handler = build.call_args.args[0]
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            handler.redirect_request(urllib.request.Request("https://audit.invalid/"), None, 302, "", {}, "http://audit.invalid/")


class HealthProbeTests(unittest.TestCase):
    def test_health_requires_valid_ip_and_uses_https_without_no_proxy_bypass(self):
        results = [subprocess.CompletedProcess([], 0, "not-an-ip\n0.01 200\n"),
                   subprocess.CompletedProcess([], 0, "203.0.113.42\n0.02 200\n")]
        with (mock.patch.object(manager.socket, "socket", return_value=mock.Mock()),
              mock.patch.object(manager.sys, "platform", "test"),
              mock.patch.object(manager, "LOCAL_PROXY_HOST", "127.0.0.1"),
              mock.patch.object(proxy_server, "get_proxy_credentials", return_value=(None, None)),
              mock.patch.object(manager.subprocess, "run", side_effect=results) as run):
            result = manager.check_proxy_health()
        self.assertEqual("203.0.113.42", result["ip"])
        self.assertEqual(2, run.call_count)
        for call in run.call_args_list:
            command = call.args[0]
            self.assertIn("=https", command)
            self.assertEqual("", command[command.index("--noproxy") + 1])
            self.assertTrue(any(part.startswith("https://") for part in command))


class ManualTargetFormTests(unittest.TestCase):
    def test_country_choices_and_drafts_survive_filtered_and_empty_node_lists(self):
        if not shutil.which("node"):
            self.skipTest("Node.js is not installed")
        discovery = manager.INDEX_HTML.split("function syncDiscoveryCountriesFromState() {", 1)[1].split("function getFilteredNodes()", 1)[0]
        routing = manager.INDEX_HTML.split("function renderManualTargetControls() {", 1)[1].split("function resetManualTargetChoices()", 1)[0]
        functions = "function syncDiscoveryCountriesFromState() {" + discovery + "\nfunction renderManualTargetControls() {" + routing
        harness = r'''
const assert = require('node:assert/strict');
const vm = require('node:vm');
function element() {
 const result = {value:'', textContent:'', dataset:{}, inputs:[], labels:[],
   querySelectorAll(selector) {
     if (selector === 'label') return this.labels;
     return selector.includes(':checked') ? this.inputs.filter(input => input.checked) : this.inputs;
   }};
 Object.defineProperty(result, 'innerHTML', {set(html) {
   this.labels = Array.from(html.matchAll(/<label\b[^>]*>([\s\S]*?)<\/label>/g), match => {
     const tag = match[1].match(/<input\b[^>]*>/)[0];
     const input = {value:tag.match(/value="([^"]*)"/)[1], checked:/\bchecked\b/.test(tag)};
     return {hidden:false, textContent:match[1].replace(/<[^>]*>/g, ''),
       querySelector(){return input;}, input};
   });
   this.inputs = this.labels.map(label => label.input);
 }});
 return result;
}
const ids = ['manual_target_country', 'net_force_country', 'country_filter_options',
 'manual_target_country_search', 'net_force_country_search', 'country_filter_options_search',
 'manual_target_ip_submit', 'manual_target_country_submit', 'country_filter_label',
 'manual_target_country_summary'];
const elements = Object.fromEntries(ids.map(id => [id, element()]));
const ctx = {
 nodes:[{country_short:'US', country:'United States'}],
 state:{force_countries:['US','CA'], discovery_countries:['US','CA']},
 $:id=>elements[id], esc:s=>String(s), translateCountry:s=>s, countryFlag:s=>s,
 document:{querySelectorAll(){return elements.country_filter_options.inputs;}},
 render(){ctx.renderManualTargetControls();}
};
vm.createContext(ctx);
vm.runInContext(`let manualTargetInFlight=false, manualCountriesDirty=false;
 let selectedDiscoveryCountries=new Set(), discoveryCountriesInitialized=false,
 discoveryCountriesDirty=false, countryFilterSignature='', currentPage=1;\n` + FUNCTIONS, ctx);
const checked = id => elements[id].inputs.filter(input=>input.checked).map(input=>input.value).sort();
const input = (id, code) => elements[id].inputs.find(input=>input.value===code);
ctx.updateCountryFilter(); ctx.renderManualTargetControls();
assert.match(elements.manual_target_country_summary.textContent, /美国 \(US\).*加拿大 \(CA\)/);
ctx.renderRoutingCountryCheckboxes('net_force_country', ['US','CA']);
for (const id of ['manual_target_country','net_force_country','country_filter_options']) {
 assert.equal(elements[id].inputs.length, 249);
 for (const code of ['US','CA','JP','DE','GB','SG']) assert.ok(input(id, code));
}
// Edit after a prior selection, then receive the old persisted state again.
input('manual_target_country','US').checked=false;
input('manual_target_country','JP').checked=true;
vm.runInContext('manualCountriesDirty=true', ctx);
input('country_filter_options','US').checked=false;
ctx.toggleDiscoveryCountry(input('country_filter_options','US'));
input('country_filter_options','JP').checked=true;
ctx.toggleDiscoveryCountry(input('country_filter_options','JP'));
ctx.updateCountryFilter(); ctx.renderManualTargetControls();
assert.deepEqual(checked('manual_target_country'), ['CA','JP']);
assert.match(elements.manual_target_country_summary.textContent, /加拿大 \(CA\).*日本 \(JP\)/);
assert.deepEqual(checked('country_filter_options'), ['CA','JP']);
// Even an empty result must allow searching for a different country.
ctx.nodes=[];
ctx.updateCountryFilter(); ctx.renderManualTargetControls();
assert.equal(elements.country_filter_options.inputs.length, 249);
assert.equal(elements.manual_target_country.inputs.length, 249);
assert.deepEqual(checked('manual_target_country'), ['CA','JP']);
assert.deepEqual(checked('country_filter_options'), ['CA','JP']);
for (const id of ['manual_target_country','net_force_country','country_filter_options']) {
 elements[id+'_search'].value='DE';
 ctx.filterCountryOptions(id, 'DE');
 assert.deepEqual(elements[id].labels.filter(label=>!label.hidden).map(label=>label.input.value), ['DE']);
}
// Node updates retain the search, including in a rebuilt routing control.
ctx.state.force_countries=['CA'];
ctx.renderRoutingCountryCheckboxes('net_force_country', ['CA']);
ctx.updateCountryFilter();
assert.deepEqual(elements.net_force_country.labels.filter(label=>!label.hidden).map(label=>label.input.value), ['DE']);
assert.deepEqual(checked('country_filter_options'), ['CA','JP']);
ctx.filterCountryOptions('country_filter_options', '');
assert.equal(elements.country_filter_options.labels.filter(label=>!label.hidden).length, 249);
ctx.clearDiscoveryCountries(); ctx.updateCountryFilter();
assert.deepEqual(checked('country_filter_options'), []);
// Legacy browsers without DisplayNames still offer codes and common names.
vm.runInContext('countryChoices.catalog=null; Intl.DisplayNames=undefined;', ctx);
assert.equal(ctx.countryChoices().size, 249);
assert.equal(ctx.countryChoices().get('JP'), '日本');
'''
        result = subprocess.run(["node", "-e", "const FUNCTIONS = " + json.dumps(functions) + ";\n" + harness],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_form_disambiguates_ip_and_submits_country_without_node_id(self):
        if not shutil.which("node"):
            self.skipTest("Node.js is not installed")
        functions = manager.INDEX_HTML.split("function renderManualTargetControls() {", 1)[1].split("async function connectNode(id){", 1)[0]
        functions = "function renderManualTargetControls() {" + functions
        harness = r'''
const assert = require('node:assert/strict');
const vm = require('node:vm');
const ids = ['manual_target_country', 'manual_target_ip', 'manual_target_connection',
 'manual_target_connection_label', 'manual_target_ip_submit', 'manual_target_country_submit', 'manual_target_status'];
const elements = Object.fromEntries(ids.map(id => {
 const element = {value:'', hidden:true, textContent:'', dataset:{}, inputs:[], focus(){},
   querySelectorAll(){return this.inputs.filter(input => input.checked);}};
 let html = '';
 Object.defineProperty(element, 'innerHTML', {
   get(){return html;},
   set(value){
     html = value;
     this.inputs = Array.from(value.matchAll(/<input\b[^>]*>/g), match => ({
       value: (match[0].match(/value="([^"]*)"/) || [,''])[1],
       checked: /\bchecked\b/.test(match[0])
     }));
   }
 });
 return [id, element];
}));
elements.manual_target_ip.value = '198.51.100.1';
const payloads = [];
const replies = [
 {status:409, ok:false, data:{candidates:[{id:'a', proto:'tcp', remote_port:443}, {id:'b', proto:'udp', remote_port:1194}]}},
 {status:200, ok:true, data:{ok:true}},
 {status:200, ok:true, data:{ok:true}}
];
const ctx = {
 nodes:[{country_short:'JP', country:'Japan'}], state:{force_countries:['US','CA']},
 $: id => elements[id], esc: s => String(s || '').replace(/</g,'&lt;'),
 setHtmlIfChanged: (element, html) => {element.innerHTML = html;},
 fetchWithTimeout: async (url, options) => {
   assert.equal(url, './api/select_target'); payloads.push(JSON.parse(options.body));
   const next = replies.shift(); return {...next, json: async () => next.data};
 }, load: async () => {}
};
vm.createContext(ctx);
vm.runInContext('let manualTargetInFlight = false; let manualCountriesDirty = false;\n' + FUNCTIONS, ctx);
(async () => {
 ctx.renderManualTargetControls();
 assert.deepEqual(Array.from(ctx.selectedRoutingCountries('manual_target_country')), ['US','CA']);
 const checkboxes = elements.manual_target_country.inputs;
 checkboxes.find(input => input.value === 'CA').checked = false;
 checkboxes.find(input => input.value === 'JP').checked = true;
 vm.runInContext('manualCountriesDirty = true', ctx);
 ctx.renderManualTargetControls();
 assert.deepEqual(Array.from(ctx.selectedRoutingCountries('manual_target_country')), ['US','JP']);
 elements.manual_target_country.inputs.forEach(input => {input.checked = ['US','CA'].includes(input.value);});
 await ctx.selectManualTarget({preventDefault(){}}, 'ip');
 assert.equal(elements.manual_target_connection.hidden, false);
 assert.match(elements.manual_target_connection.innerHTML, /tcp/);
 elements.manual_target_connection.value = 'b';
 await ctx.selectManualTarget({preventDefault(){}}, 'ip');
 assert.equal(elements.manual_target_connection.hidden, true);
 await ctx.selectManualTarget({preventDefault(){}}, 'country');
 assert.deepEqual(payloads, [
   {mode:'ip', ip:'198.51.100.1'},
   {mode:'ip', ip:'198.51.100.1', node_id:'b'},
   {mode:'country', countries:['US','CA']}
 ]);
 assert.match(elements.manual_target_status.textContent, /限定所选国家/);
 elements.manual_target_country.inputs.forEach(input => {input.checked = false;});
 vm.runInContext('manualCountriesDirty = true', ctx);
 await ctx.selectManualTarget({preventDefault(){}}, 'country');
 assert.equal(payloads.length, 3);
 assert.match(elements.manual_target_status.textContent, /至少选择一个/);
})().catch(error => {process.stderr.write(String(error)); process.exitCode = 1;});
'''
        script = "const FUNCTIONS = " + json.dumps(functions) + ";\n" + harness
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=10)
        self.assertEqual(0, result.returncode, result.stderr)


class GatewayHTTPTests(unittest.TestCase):
    setUp_paths = fixtures.ManagerLogicTests.setUp
    tearDown_paths = fixtures.ManagerLogicTests.tearDown

    def setUp(self):
        self.setUp_paths()

        class QuietHandler(manager.Handler):
            def log_message(self, *args):
                pass

        self.server = manager.DualStackHTTPServer(("127.0.0.1", 0), QuietHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()
        self.auth = manager.load_ui_config()
        self.auth["port"] = self.server.server_port
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.client = proxyctl.GatewayClient(self.auth, self.url, timeout=2)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        self.tearDown_paths()

    def test_target_endpoint_requires_login_and_cli_completes_session(self):
        with mock.patch.object(manager, "connect_node", return_value="Connected test") as connect:
            with self.assertRaises(proxyctl.GatewayError) as error:
                self.client.request("api/select_target", {"mode": "country", "country": "JP"})
            self.assertEqual(401, error.exception.status)
            connect.assert_not_called()
            self.client.login()
            self.assertTrue(self.client.request("api/select_target", {"mode": "country", "country": "JP"})["ok"])
            connect.assert_called_once_with("", target={"mode": "country", "country": "JP"})
            self.client.logout()
            with self.assertRaises(proxyctl.GatewayError):
                self.client.request("api/select_target", {"mode": "country", "country": "JP"})

    def test_cross_origin_and_non_json_requests_are_rejected(self):
        token = "test-session"
        manager.active_sessions[token] = time.time() + 60
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        self.addCleanup(connection.close)
        path = f"/{self.auth['secret_path']}/api/select_target"
        with mock.patch.object(manager, "connect_node") as connect:
            connection.request("POST", path, '{}', {"Cookie": f"session={token}", "Content-Type": "application/json", "Origin": "https://foreign.invalid"})
            response = connection.getresponse()
            self.assertEqual(403, response.status)
            response.read()
            connection.request("POST", path, '{}', {"Cookie": f"session={token}", "Content-Type": "text/plain"})
            response = connection.getresponse()
            self.assertEqual(415, response.status)
            response.read()
        connect.assert_not_called()

    def test_ambiguous_selection_returns_structured_409(self):
        self.client.login()
        with mock.patch.object(manager, "connect_node", side_effect=manual_target.TargetError("ambiguous", 409, [{"id": "a"}])):
            with self.assertRaises(proxyctl.GatewayError) as error:
                self.client.request("api/select_target", {"mode": "ip", "ip": "198.51.100.1"})
        self.assertEqual(409, error.exception.status)
        self.assertEqual([{"id": "a"}], error.exception.candidates)

    def test_cli_prints_status_without_credentials_and_logs_out(self):
        path = manager.DATA_DIR / "cli-auth.json"
        path.write_text(json.dumps(self.auth))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = proxyctl.main(["--auth-file", str(path), "--url", self.url, "status"])
        self.assertEqual(0, status)
        self.assertNotIn(self.auth["password"], output.getvalue())
        self.assertNotIn(self.auth["secret_path"], output.getvalue())
        self.assertEqual({}, manager.active_sessions)

    def test_cli_http_selection_updates_real_manager_policy_and_state(self):
        nodes = fixtures.ManagerLogicTests.write_nodes(self, 2)
        nodes[0]["country_short"] = "US"
        nodes[1]["country_short"] = "JP"
        manager.write_json(manager.NODES_FILE, nodes)
        path = manager.DATA_DIR / "cli-auth.json"
        path.write_text(json.dumps(self.auth))
        ManualConnectionTests.connection_mocks(self)
        for selector in (["--country", "JP"], ["--ip", nodes[0]["ip"]]):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = proxyctl.main(["--auth-file", str(path), "--url", self.url, "select", *selector])
            self.assertEqual(0, result)
            data = json.loads(output.getvalue())
            self.assertTrue(data["state"]["proxy_ready"])
        config = manager.load_ui_config()
        self.assertEqual("fixed_ip", config["routing_mode"])
        self.assertEqual(nodes[0]["id"], config["fixed_node_id"])
        self.assertEqual(nodes[0]["id"], manager.active_openvpn_node_id)
        self.assertEqual({}, manager.active_sessions)

    def test_cli_refuses_remote_cleartext_and_redirects(self):
        with self.assertRaises(ValueError):
            proxyctl.GatewayClient(self.auth, "http://198.51.100.10:8787")
        with self.assertRaises(proxyctl.GatewayError):
            proxyctl.NoRedirect().redirect_request(None, None, 302, "", {}, "https://foreign.invalid")

    def test_multi_country_settings_persist_and_invalid_requests_keep_policy(self):
        self.client.login()
        for endpoint in ("api/update_routing", "api/update_settings"):
            payload = {"routing_mode": "fixed_region", "force_countries": ["US", "CA"],
                       "routing_ip_type": "all", "proxy_port": self.auth["proxy_port"]}
            self.assertTrue(self.client.request(endpoint, payload)["ok"])
            config = manager.load_ui_config()
            self.assertEqual(["CA", "US"], config["force_countries"])
            self.assertEqual(["CA", "US"], self.client.request("api/nodes")["state"]["force_countries"])
            self.assertEqual("", config["force_country"])
            for invalid in ([], "US,CA", ["US", "Japan"]):
                with self.subTest(endpoint=endpoint, invalid=invalid), self.assertRaises(proxyctl.GatewayError) as error:
                    self.client.request(endpoint, {**payload, "force_countries": invalid})
                self.assertEqual(400, error.exception.status)
                self.assertEqual(config, manager.load_ui_config())

    def test_cli_repeated_country_arguments_use_real_multi_country_policy(self):
        nodes = fixtures.ManagerLogicTests.write_nodes(self, 2)
        nodes[0]["country_short"], nodes[1]["country_short"] = "US", "CA"
        manager.write_json(manager.NODES_FILE, nodes)
        path = manager.DATA_DIR / "cli-auth.json"
        path.write_text(json.dumps(self.auth))
        ManualConnectionTests.connection_mocks(self)
        with contextlib.redirect_stdout(io.StringIO()):
            result = proxyctl.main(["--auth-file", str(path), "--url", self.url,
                                    "select", "--country", "US", "--country", "CA"])
        self.assertEqual(0, result)
        self.assertEqual(["CA", "US"], manager.load_ui_config()["force_countries"])
        self.assertEqual({}, manager.active_sessions)


class MultiCountryRoutingTests(unittest.TestCase):
    setUp = fixtures.ManagerLogicTests.setUp
    tearDown = fixtures.ManagerLogicTests.tearDown

    def test_filter_and_connection_guard_allow_both_countries_and_reject_others(self):
        nodes = [{"id": code, "country_short": code} for code in ["US", "CA", "JP"]]
        config = {"routing_mode": "fixed_region", "force_countries": ["US", "CA"]}
        self.assertEqual(["US", "CA"], [n["id"] for n in manager.apply_routing_filters(nodes, config)])
        for node in nodes[:2]:
            manager.validate_node_allowed_by_routing(node, config)
        with self.assertRaises(RuntimeError):
            manager.validate_node_allowed_by_routing(nodes[2], config)
        for invalid in ([], ["US", "bad"]):
            restricted = {"routing_mode": "fixed_region", "force_countries": invalid}
            self.assertEqual([], manager.apply_routing_filters(nodes, restricted))
            with self.assertRaises(RuntimeError):
                manager.validate_node_allowed_by_routing(nodes[0], restricted)

    def test_legacy_single_country_code_and_name_remain_restricted(self):
        nodes = [{"id": "us", "country_short": "US", "country": "美国"},
                 {"id": "ca", "country_short": "CA", "country": "加拿大"}]
        for legacy in ("US", "United States", "美国"):
            self.assertEqual(["us"], [n["id"] for n in manager.apply_routing_filters(
                nodes, {"routing_mode": "fixed_region", "force_country": legacy})])

    def test_automatic_failover_can_cross_between_selected_countries(self):
        nodes = [
            {"id": "us", "country_short": "US", "probe_status": "unavailable"},
            {"id": "ca", "country_short": "CA", "probe_status": "available", "latency_ms": 50},
            {"id": "jp", "country_short": "JP", "probe_status": "available", "latency_ms": 1},
        ]
        config = {"routing_mode": "fixed_region", "force_countries": ["US", "CA"]}
        with (mock.patch.object(manager, "load_ui_config", return_value=config),
              mock.patch.object(manager, "read_nodes", return_value=nodes),
              mock.patch.object(manager, "connect_node") as connect):
            manager.auto_switch_node()
        connect.assert_called_once_with("ca")

    def test_no_selected_country_candidate_never_falls_back_to_another_country(self):
        nodes = [{"id": "jp", "country_short": "JP", "probe_status": "available", "latency_ms": 1}]
        config = {"routing_mode": "fixed_region", "force_countries": ["US", "CA"]}
        with (mock.patch.object(manager, "load_ui_config", return_value=config),
              mock.patch.object(manager, "read_nodes", return_value=nodes),
              mock.patch.object(manager, "connect_node") as connect,
              mock.patch.object(manager, "stop_active_openvpn"),
              mock.patch.object(manager, "schedule_background_refill", return_value=False)):
            manager.auto_switch_node()
        connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
