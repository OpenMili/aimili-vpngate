"""Bind the actual service ports and report verified local panel access."""
from __future__ import annotations

import argparse
import errno
import http.client
import ipaddress
import json
from itertools import chain
import os
from pathlib import Path
import re
import socket
import time
import urllib.error
import urllib.request


def bind_available(factory, host, preferred, exclude=()):
    """Keep the selected listener open. Only a port collision merits a retry."""
    for port in chain(range(preferred, 65536), range(1024, preferred)):
        if port in exclude:
            continue
        try:
            return factory(host, port), port
        except OSError as exc:
            if exc.errno != errno.EADDRINUSE and getattr(exc, "winerror", None) not in (10013, 10048):
                raise
    raise OSError(errno.EADDRINUSE, f"从 {preferred} 开始未找到空闲端口")


def local_host(host):
    return {"0.0.0.0": "127.0.0.1", "::": "::1", "": "127.0.0.1"}.get(host, host)


def read_config(data_dir):
    return json.loads((data_dir / "ui_auth.json").read_text(encoding="utf-8"))


def login_page_ready(config):
    path = config["secret_path"]
    if not path:
        return False
    conn = http.client.HTTPConnection(local_host(config["host"]), int(config["port"]), timeout=2)
    try:
        conn.request("GET", f"/{path}/")
        response = conn.getresponse()
        return response.status == 200 and b'id="login_form"' in response.read(131072)
    finally:
        conn.close()


def public_host(bind_host):
    if bind_host not in ("0.0.0.0", "::", ""):
        return bind_host
    override = os.environ.get("AIMILIVPN_PUBLIC_HOST", "").strip()
    if override:
        try:
            return str(ipaddress.ip_address(override.strip("[]")))
        except ValueError:
            if not re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?", override):
                raise ValueError("AIMILIVPN_PUBLIC_HOST 需要 IP 地址或主机名")
            return override
    ssh = os.environ.get("SSH_CONNECTION", "").split()
    candidate = None
    if len(ssh) == 4:
        try:
            ip = ipaddress.ip_address(ssh[2])
            if bind_host == "::" or ip.version == 4:
                candidate = str(ip)
                if ip.is_global:
                    return candidate
        except ValueError:
            pass
    # Ask directly, not through a subscription proxy with a different public IP.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        url = "https://api64.ipify.org" if bind_host == "::" else "https://api.ipify.org"
        with opener.open(url, timeout=3) as response:
            ip = ipaddress.ip_address(response.read(65).decode("ascii").strip())
            if ip.is_global and (bind_host == "::" or ip.version == 4):
                return str(ip)
    except (OSError, ValueError, urllib.error.URLError):
        pass
    if candidate:
        return candidate
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.0.2.1", 9))
            return sock.getsockname()[0]
    except OSError:
        return socket.gethostname()


def print_access(data_dir, cfg):
    host = public_host(cfg["host"])
    address = f"[{host}]" if ":" in host else host
    bootstrap_file = data_dir / "ui_bootstrap.json"
    try:
        bootstrap = json.loads(bootstrap_file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        bootstrap = {}
    password = bootstrap.get("password") if bootstrap.get("username") == cfg["username"] else None
    print(f"登录地址  http://{address}:{cfg['port']}/{cfg['secret_path']}/")
    print(f"管理账号  {cfg['username']}")
    print(f"管理密码  {password or '沿用已有密码'}")
    print(f"本机代理  127.0.0.1:{cfg['proxy_port']}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("health", "summary"))
    parser.add_argument("--data-dir", type=Path, default=Path(os.environ.get("VPNGATE_DATA_DIR", "/data")))
    parser.add_argument("--wait", type=float, default=0)
    args = parser.parse_args()
    deadline = time.monotonic() + args.wait
    while True:
        try:
            cfg = read_config(args.data_dir)
            if login_page_ready(cfg):
                break
        except (OSError, ValueError, KeyError, http.client.HTTPException):
            pass
        if time.monotonic() >= deadline:
            raise SystemExit("AimiliVPN 登录页未就绪，请检查服务日志。")
        time.sleep(.4)
    if args.action == "summary":
        print_access(args.data_dir, cfg)


if __name__ == "__main__":
    main()
