#!/usr/bin/env python3
"""Control one gateway using its existing private auth file and HTTP API."""
from __future__ import annotations

import argparse
import http.cookiejar
import ipaddress
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from manual_target import node_ip_matches, numeric_ip, public_node

STATUS_FIELDS = (
    "routing_mode", "force_country", "force_countries", "fixed_node_id", "connection_enabled",
    "active_openvpn_node_id", "is_connecting", "pending_node_id", "tunnel_ready",
    "proxy_ready", "proxy_ok", "proxy_ip", "proxy_latency_ms", "proxy_error",
)


class GatewayError(RuntimeError):
    def __init__(self, message: str, status: int = 0, candidates: list | None = None):
        super().__init__(message)
        self.status = status
        self.candidates = candidates or []


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise GatewayError("管理接口返回重定向，已拒绝转发凭据", code)


class GatewayClient:
    def __init__(self, auth: dict[str, Any], url: str | None = None, timeout: float = 120):
        if not isinstance(auth.get("username"), str) or not auth["username"]:
            raise ValueError("认证文件缺少用户名")
        if not isinstance(auth.get("password"), str) or not auth["password"]:
            raise ValueError("认证文件缺少密码")
        secret = auth.get("secret_path")
        if not isinstance(secret, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", secret):
            raise ValueError("认证文件缺少有效的管理路径")
        if not 0 < timeout <= 300:
            raise ValueError("timeout 必须大于 0 且不超过 300 秒")
        parsed = urllib.parse.urlsplit(url or f"http://127.0.0.1:{int(auth.get('port', 8787))}")
        if (parsed.scheme not in ("http", "https") or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.query or parsed.fragment or parsed.path not in ("", "/")):
            raise ValueError("url 必须是无凭据、路径或查询参数的 HTTP(S) 服务地址")
        if parsed.scheme == "http":
            try:
                local = ipaddress.ip_address(parsed.hostname).is_loopback
            except ValueError:
                local = parsed.hostname == "localhost"
            if not local:
                raise ValueError("明文 HTTP 仅允许回环地址；远程请使用 HTTPS 或 SSH 隧道")
        _ = parsed.port  # Validate a supplied port before sending credentials.
        self.base = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, f"/{secret}/", "", ""))
        self.timeout = timeout
        self.credentials = {"username": auth["username"], "password": auth["password"]}
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), NoRedirect(),
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
        )

    def request(self, path: str, payload: dict | None = None) -> dict:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.base + path, data=body,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                data = json.loads(response.read(4 * 1024 * 1024).decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                error = json.loads(exc.read(65536).decode("utf-8"))
            except (ValueError, UnicodeError):
                error = {}
            finally:
                exc.close()
            if not isinstance(error, dict):
                error = {}
            raise GatewayError(error.get("error", "管理接口请求失败"), exc.code, error.get("candidates")) from None
        if not isinstance(data, dict):
            raise GatewayError("管理接口返回的 JSON 不是对象")
        if data.get("ok") is False:
            raise GatewayError(str(data.get("error") or "操作失败"))
        return data

    def login(self) -> None:
        self.request("api/login", self.credentials)

    def logout(self) -> None:
        self.request("api/logout", {})


def main(argv: list[str] | None = None) -> int:
    default_data = Path(os.environ.get("VPNGATE_DATA_DIR", Path(__file__).resolve().parent / "vpngate_data"))
    parser = argparse.ArgumentParser(description="按节点 IP 或国家切换 AimiliVPN 出口；切换可能中断已有连接")
    parser.add_argument("--auth-file", type=Path, default=default_data / "ui_auth.json", help="服务生成的私有认证文件")
    parser.add_argument("--url", help="服务地址；默认 http://127.0.0.1:<配置端口>，不含管理路径")
    parser.add_argument("--timeout", type=float, default=120, help="单次请求超时秒数，超时不代表服务端取消")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="当前节点、策略和观测出口")
    nodes_parser = commands.add_parser("nodes", help="列出节点，不显示私钥或内部路径")
    nodes_parser.add_argument("--country", help="按两位国家代码过滤")
    nodes_parser.add_argument("--ip", help="按节点入口 IP 过滤")
    select_parser = commands.add_parser("select", help="切换目标并保存对应策略")
    selector = select_parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--ip", help="锁定节点入口 IP")
    selector.add_argument("--country", action="append", help="限定出口国家，可重复，例如 --country US --country CA")
    select_parser.add_argument("--node-id", help="同一 IP 多个节点时明确指定；只能与 --ip 一起使用")
    args = parser.parse_args(argv)
    if getattr(args, "node_id", None) and not getattr(args, "ip", None):
        parser.error("--node-id 必须与 --ip 一起使用")

    client = None
    logged_in = False
    try:
        auth = json.loads(args.auth_file.read_text(encoding="utf-8"))
        if not isinstance(auth, dict):
            raise ValueError("认证文件必须是 JSON 对象")
        client = GatewayClient(auth, args.url, args.timeout)
        client.login()
        logged_in = True
        if args.command == "select":
            payload = {"mode": "ip", "ip": numeric_ip(args.ip)} if args.ip else {"mode": "country", "countries": args.country}
            if args.node_id:
                payload["node_id"] = args.node_id
            data = client.request("api/select_target", payload)
            state = data["state"]
            output = {"ok": True, "state": {key: state.get(key) for key in STATUS_FIELDS}}
        else:
            data = client.request("api/nodes")
            if args.command == "status":
                output = {key: data["state"].get(key) for key in STATUS_FIELDS}
            else:
                nodes = data["nodes"]
                if args.country:
                    nodes = [node for node in nodes if node.get("country_short") == args.country.upper()]
                if args.ip:
                    target = numeric_ip(args.ip)
                    nodes = [node for node in nodes if node_ip_matches(node, target)]
                output = {"nodes": [public_node(node) for node in nodes]}
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    except GatewayError as exc:
        print(json.dumps({"ok": False, "status": exc.status, "error": str(exc), "candidates": exc.candidates}, ensure_ascii=False), file=sys.stderr)
    except (OSError, ValueError, KeyError, urllib.error.URLError) as exc:
        print(f"操作失败：{exc}", file=sys.stderr)
    finally:
        if client is not None and logged_in:
            try:
                client.logout()
            except (OSError, ValueError, GatewayError, urllib.error.URLError):
                pass
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
