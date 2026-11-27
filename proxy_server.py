#!/usr/bin/env python3
from __future__ import annotations
import base64
import ipaddress
import re
import os
import secrets
import select
import errno
import socket
import threading
import urllib.parse
import time

from snapshot_utils import valid_remote_host

def parse_positive_int(value: str | None, default: int) -> int:
    try:
        return max(1, int(value or default))
    except (TypeError, ValueError):
        return default

MAX_PROXY_CONNECTIONS = parse_positive_int(os.environ.get("LOCAL_PROXY_MAX_CONNECTIONS"), 256)
proxy_connection_sem = threading.BoundedSemaphore(MAX_PROXY_CONNECTIONS)

def recv_exact(sock: socket.socket, size: int) -> bytes:
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise ConnectionError("Unexpected disconnect.")
        data += chunk
    return data

def parse_host_port(authority: str, default_port: int) -> tuple[str, int]:
    authority = authority.strip()
    port = default_port
    if authority.startswith("["):
        host, sep, suffix = authority[1:].partition("]")
        if not sep or (suffix and not suffix.startswith(":")):
            raise ValueError("Invalid IPv6 authority")
        ipaddress.IPv6Address(host)
        port_text = suffix[1:] if suffix else None
    elif authority.count(":") == 1:
        host, _, port_text = authority.partition(":")
    else:
        host, port_text = authority, None
    if port_text is not None:
        if not re.fullmatch(r"[0-9]{1,5}", port_text, re.ASCII):
            raise ValueError("Invalid destination port")
        port = int(port_text)
    if not 1 <= port <= 65535 or not valid_remote_host(host):
        raise ValueError("Invalid destination address")
    return host, port

def get_proxy_credentials() -> tuple[str | None, str | None]:
    user = os.environ.get("LOCAL_PROXY_USER") or os.environ.get("LOCAL_PROXY_USERNAME")
    password = os.environ.get("LOCAL_PROXY_PASS") or os.environ.get("LOCAL_PROXY_PASSWORD")
    if user is None and password is None:
        return None, None
    if not user or not password:
        raise ValueError("Configure both LOCAL_PROXY_USER and LOCAL_PROXY_PASS")
    return user, password

def proxy_auth_enabled() -> bool:
    user, password = get_proxy_credentials()
    return user is not None and password is not None

def parse_http_basic_auth(lines: list[str]) -> tuple[str | None, str | None]:
    for line in lines:
        name, sep, value = line.partition(":")
        if not sep or name.strip().lower() != "proxy-authorization":
            continue
        scheme, _, token = value.strip().partition(" ")
        if scheme.lower() != "basic" or not token:
            return None, None
        try:
            decoded = base64.b64decode(token, validate=True).decode("utf-8", errors="replace")
        except Exception:
            return None, None
        username, sep, password = decoded.partition(":")
        if not sep:
            return None, None
        return username, password
    return None, None

def check_credentials(username: str | None, password: str | None) -> bool:
    expected_user, expected_pass = get_proxy_credentials()
    if expected_user is None or expected_pass is None:
        return True
    if username is None or password is None:
        return False
    return secrets.compare_digest(username.encode(), expected_user.encode()) and secrets.compare_digest(password.encode(), expected_pass.encode())

def dns_read_name(packet: bytes, offset: int) -> tuple[bytes, int]:
    labels = []
    resume = None
    for _ in range(128):
        length = packet[offset]
        if length == 0:
            return b".".join(labels).lower(), resume if resume is not None else offset + 1
        if length & 0xC0 == 0xC0:
            pointer = ((length & 0x3F) << 8) | packet[offset + 1]
            if pointer >= offset:
                raise ValueError("Invalid DNS compression pointer")
            if resume is None:
                resume = offset + 2
            offset = pointer
            continue
        if length > 63 or offset + length + 1 > len(packet):
            raise ValueError("Invalid DNS label")
        offset += 1
        labels.append(packet[offset:offset + length])
        offset += length
    raise ValueError("DNS name is too long")


def dns_query_over_tun0(host: str, qtype: int, dns_server: str, timeout: float) -> str | None:
    try:
        dns_ip = ipaddress.ip_address(dns_server)
        hostname = host.rstrip(".").encode("idna").lower()
        if not valid_remote_host(hostname.decode("ascii")):
            return None
        qname = b"".join(bytes([len(label)]) + label for label in hostname.split(b".")) + b"\x00"
        tx_id = secrets.token_bytes(2)
        question = qname + qtype.to_bytes(2, "big") + b"\x00\x01"
        packet = tx_id + b"\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00" + question
        family = socket.AF_INET if dns_ip.version == 4 else socket.AF_INET6
        with socket.socket(family, socket.SOCK_DGRAM) as sock:
            sock.settimeout(timeout)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, b"tun0")
            # A connected UDP socket only receives from the configured peer.
            sock.connect((str(dns_ip), 53))
            sock.send(packet)
            resp = sock.recv(4096)
        if len(resp) < 12 or resp[:2] != tx_id or resp[4:6] != b"\x00\x01":
            return None
        flags = int.from_bytes(resp[2:4], "big")
        if not flags & 0x8000 or flags & 0x7A0F:  # QR, standard response, untruncated, successful
            return None
        name, offset = dns_read_name(resp, 12)
        if name != hostname or resp[offset:offset + 4] != question[-4:]:
            return None
        offset += 4
        addresses = {}
        aliases = {}
        for _ in range(int.from_bytes(resp[6:8], "big")):
            name, offset = dns_read_name(resp, offset)
            header = resp[offset:offset + 10]
            if len(header) != 10:
                return None
            answer_type = int.from_bytes(header[:2], "big")
            length = int.from_bytes(header[8:], "big")
            offset += 10
            end = offset + length
            if end > len(resp):
                return None
            if header[2:4] == b"\x00\x01":
                if answer_type == qtype and length == (4 if qtype == 1 else 16):
                    addresses.setdefault(name, str(ipaddress.ip_address(resp[offset:end])))
                elif answer_type == 5:
                    alias, after_name = dns_read_name(resp, offset)
                    if after_name == end:
                        aliases[name] = alias
            offset = end
        name = hostname
        seen = set()
        while name not in seen:
            if name in addresses:
                return addresses[name]
            if name not in aliases:
                break
            seen.add(name)
            name = aliases[name]
    except (OSError, ValueError, IndexError, AttributeError):
        return None
    return None


def resolve_dns_over_tun0(host: str, dns_server: str | None = None, timeout: float = 1.5) -> str | None:
    try:
        return str(ipaddress.ip_address(host)) if "%" not in host else None
    except ValueError:
        pass
    servers = dns_server or os.environ.get("VPNGATE_TUN_DNS", "8.8.8.8,1.1.1.1")
    for server in servers.split(",")[:3]:
        for qtype in (1, 28):
            result = dns_query_over_tun0(host, qtype, server.strip(), timeout)
            if result:
                return result
    return None

def create_connection(address: tuple[str, int], timeout: float = 20) -> socket.socket:
    host, port = address
    if not 1 <= port <= 65535:
        raise ValueError("Invalid destination port")
    resolved_ip = resolve_dns_over_tun0(host)
    if not resolved_ip:
        raise OSError("DNS resolution through tun0 failed")

    err = None
    for res in socket.getaddrinfo(resolved_ip, port, 0, socket.SOCK_STREAM, 0, socket.AI_NUMERICHOST):
        af, socktype, proto, canonname, sa = res
        sock = None
        try:
            sock = socket.socket(af, socktype, proto)
            sock.settimeout(timeout)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, b"tun0")
            sock.connect(sa)
            return sock
        except OSError as e:
            err = e
            if "operation not permitted" in str(e).lower() or e.errno == 1:
                err = OSError(f"[错误代码 3006] [ERR_PROXY_BIND_TUN_PERM_DENIED] 绑定虚拟网卡 tun0 失败，权限不足！必须以 root 权限运行，或者进程缺少 CAP_NET_RAW 权限。")
            elif "no such device" in str(e).lower() or e.errno == 19:
                err = OSError(f"[错误代码 3004] [ERR_ROUTE_DEV_NOT_FOUND] 绑定虚拟网卡 tun0 失败，找不到设备！这通常是因为 OpenVPN 核心未能成功连接或已被异常终止。")
            if sock is not None:
                sock.close()
    if err is not None:
        raise err
    else:
        raise OSError("getaddrinfo returns empty list")

def relay(left: socket.socket, right: socket.socket) -> None:
    sockets = [left, right]
    while sockets:
        readable, _, errored = select.select(sockets, [], sockets, 120)
        if errored or not readable:
            return
        for source in readable:
            target = right if source is left else left
            data = source.recv(65536)
            if not data:
                sockets.remove(source)
                try:
                    target.shutdown(socket.SHUT_WR)
                except OSError:
                    pass
            else:
                target.sendall(data)

def socks5_client(client: socket.socket, first_byte: bytes) -> None:
    upstream = None
    try:
        methods_count = recv_exact(client, 1)[0]
        methods = recv_exact(client, methods_count)
        if proxy_auth_enabled():
            if 2 not in methods:
                client.sendall(b"\x05\xff")
                return
            client.sendall(b"\x05\x02")
            auth_version = recv_exact(client, 1)[0]
            if auth_version != 1:
                client.sendall(b"\x01\x01")
                return
            username = recv_exact(client, recv_exact(client, 1)[0]).decode("utf-8", errors="replace")
            password = recv_exact(client, recv_exact(client, 1)[0]).decode("utf-8", errors="replace")
            if not check_credentials(username, password):
                client.sendall(b"\x01\x01")
                return
            client.sendall(b"\x01\x00")
        else:
            if 0 not in methods:
                client.sendall(b"\x05\xff")
                return
            client.sendall(b"\x05\x00")
        version, command, _, address_type = recv_exact(client, 4)
        if version != 5 or command != 1:
            client.sendall(b"\x05\x07\x00\x01\x00\x00\x00\x00\x00\x00")
            return
        if address_type == 1:
            host = socket.inet_ntoa(recv_exact(client, 4))
        elif address_type == 3:
            host = recv_exact(client, recv_exact(client, 1)[0]).decode("idna")
        elif address_type == 4:
            host = socket.inet_ntop(socket.AF_INET6, recv_exact(client, 16))
        else:
            client.sendall(b"\x05\x08\x00\x01\x00\x00\x00\x00\x00\x00")
            return
        port = int.from_bytes(recv_exact(client, 2), "big")
        try:
            upstream = create_connection((host, port), timeout=20)
        except Exception as e:
            print(f"[SOCKS5 代理失败] 目标 {host}:{port} 连接失败: {e}", flush=True)
            try:
                client.sendall(b"\x05\x04\x00\x01\x00\x00\x00\x00\x00\x00")
            except OSError:
                pass
            raise
        client.sendall(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")
        relay(client, upstream)
    finally:
        client.close()
        if upstream:
            upstream.close()

def read_http_header(client: socket.socket, first_byte: bytes) -> bytes:
    data = first_byte
    while b"\r\n\r\n" not in data and len(data) < 65536:
        chunk = client.recv(4096)
        if not chunk:
            break
        data += chunk
    return data

HTTP_TOKEN = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+\Z", re.ASCII)
_HTTP_BAD_REQUEST = b"HTTP/1.1 400 Bad Request\r\nConnection: close\r\nContent-Length: 0\r\n\r\n"


def http_client(client: socket.socket, first_byte: bytes) -> None:
    upstream = None
    try:
        raw = read_http_header(client, first_byte)
        head, delimiter, rest = raw.partition(b"\r\n\r\n")
        if not delimiter or len(head) > 65536:
            raise ValueError("Incomplete HTTP headers")
        lines = head.decode("iso-8859-1").split("\r\n")
        method, target, version = lines[0].split(" ")
        if not HTTP_TOKEN.fullmatch(method) or not target or re.search(r"[\x00-\x20\x7f]", target):
            raise ValueError("Invalid HTTP request line")
        if version not in {"HTTP/1.0", "HTTP/1.1"}:
            raise ValueError("Unsupported HTTP version")
        headers: dict[str, list[str]] = {}
        for line in lines[1:]:
            key, sep, value = line.partition(":")
            if not sep or not HTTP_TOKEN.fullmatch(key) or re.search(r"[\x00-\x08\x0a-\x1f\x7f]", value):
                raise ValueError("Invalid HTTP header")
            headers.setdefault(key.lower(), []).append(value.strip(" \t"))

        if proxy_auth_enabled() and not check_credentials(*parse_http_basic_auth(lines[1:])):
            client.sendall(
                b"HTTP/1.1 407 Proxy Authentication Required\r\n"
                b'Proxy-Authenticate: Basic realm="AimiliVPN Proxy"\r\n'
                b"Content-Length: 0\r\n\r\n"
            )
            return
        if method == "CONNECT":
            host, port = parse_host_port(target, 443)
            upstream = create_connection((host, port), timeout=20)
            client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            if rest:
                upstream.sendall(rest)
            relay(client, upstream)
            return

        parsed = urllib.parse.urlsplit(target)
        if parsed.scheme == "http" and parsed.netloc and parsed.username is None:
            host, port = parse_host_port(parsed.netloc, 80)
        elif target.startswith("/") and not parsed.netloc and len(headers.get("host", [])) == 1:
            host, port = parse_host_port(headers["host"][0], 80)
        else:
            raise ValueError("Invalid HTTP destination")
        if parsed.fragment or "transfer-encoding" in headers:
            raise ValueError("Unsupported HTTP framing")
        lengths = headers.get("content-length", ["0"])
        if len(lengths) != 1 or not re.fullmatch(r"[0-9]{1,12}", lengths[0], re.ASCII):
            raise ValueError("Invalid HTTP content length")
        length = int(lengths[0])
        if len(rest) > length:
            raise ValueError("Unexpected HTTP request data")

        connection_options = {
            item.strip().lower()
            for value in headers.get("connection", [])
            for item in value.split(",")
        }
        skip = connection_options | {
            "host", "connection", "proxy-connection", "proxy-authorization", "proxy-authenticate",
            "keep-alive", "te", "trailer", "upgrade", "expect", "content-length",
        }
        path = urllib.parse.urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
        authority = f"[{host}]" if ":" in host else host
        if port != 80:
            authority += f":{port}"
        forwarded = [f"{method} {path} {version}", f"Host: {authority}", "Connection: close"]
        forwarded.extend(f"{key}: {value}" for key, values in headers.items() if key not in skip for value in values)
        if "content-length" in headers:
            forwarded.append(f"Content-Length: {length}")
        upstream = create_connection((host, port), timeout=20)
        upstream.sendall(("\r\n".join(forwarded) + "\r\n\r\n").encode("iso-8859-1") + rest)
        if length and headers.get("expect") == ["100-continue"]:
            client.sendall(b"HTTP/1.1 100 Continue\r\n\r\n")
        remaining = length - len(rest)
        while remaining:
            chunk = client.recv(min(65536, remaining))
            if not chunk:
                raise ConnectionError("Incomplete HTTP request body")
            upstream.sendall(chunk)
            remaining -= len(chunk)
        while chunk := upstream.recv(65536):
            client.sendall(chunk)
    except ValueError:
        client.sendall(_HTTP_BAD_REQUEST)
    except OSError as exc:
        print(f"[HTTP 代理失败] {exc}", flush=True)
        try:
            client.sendall(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
        except OSError:
            pass
    finally:
        client.close()
        if upstream:
            upstream.close()

def proxy_client(client: socket.socket, address: tuple[str, int]) -> None:
    try:
        client.settimeout(30)
        first = recv_exact(client, 1)
        if first == b"\x05":
            socks5_client(client, first)
        else:
            http_client(client, first)
    except Exception as e:
        err_msg = str(e)
        if "[错误代码" in err_msg:
            print(f"[代理客户端连接失败] 客户端 {address} 遭遇系统性阻碍: {err_msg}", flush=True)
        try:
            client.close()
        except OSError:
            pass

def bind_proxy(host: str, port: int) -> socket.socket:
    family = socket.AF_INET6 if ":" in host or host == "" else socket.AF_INET
    server = socket.socket(family, socket.SOCK_STREAM)
    try:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if family == socket.AF_INET6:
            try:
                server.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
            except OSError:
                pass
        server.bind((host, port))
        server.listen(256)
        return server
    except OSError:
        server.close()
        raise


def open_proxy_listener(host: str, port: int) -> socket.socket:
    try:
        return bind_proxy(host, port)
    except OSError as exc:
        if exc.errno not in (errno.EAFNOSUPPORT, errno.EADDRNOTAVAIL) or host not in ("::", "::1", ""):
            raise
        return bind_proxy("127.0.0.1" if host == "::1" else "0.0.0.0", port)


def start_proxy_server(host: str, port: int, server: socket.socket | None = None) -> None:
    get_proxy_credentials()
    if server is None:
        server = open_proxy_listener(host, port)
    print(f"HTTP/SOCKS5 proxy listening on {host}:{port}", flush=True)
    while True:
        try:
            client, address = server.accept()
            if not proxy_connection_sem.acquire(blocking=False):
                print(f"[代理限流] 当前连接数已达到上限 {MAX_PROXY_CONNECTIONS}，拒绝客户端 {address}", flush=True)
                try:
                    client.close()
                except OSError:
                    pass
                continue

            def run_client(client_socket: socket.socket = client, client_address: tuple[str, int] = address) -> None:
                try:
                    proxy_client(client_socket, client_address)
                finally:
                    proxy_connection_sem.release()

            try:
                threading.Thread(target=run_client, daemon=True).start()
            except Exception:
                proxy_connection_sem.release()
                client.close()
                raise
        except Exception as e:
            print(f"[ERROR] Proxy accept failed: {e}", flush=True)
            time.sleep(0.5)
