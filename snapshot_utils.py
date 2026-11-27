from __future__ import annotations

import base64
import csv
import hashlib
import ipaddress
import io
import re
from typing import Any


MAX_SNAPSHOT_BYTES = 12 * 1024 * 1024
MAX_CONFIG_BYTES = 128 * 1024
MAX_CONFIG_LINE_BYTES = 240
# The current public VPN Gate feed ships this shared CA and uses this TLS name.
VPNGATE_SHARED_CA_SHA256 = "96bcec06264976f37460779acf28c5a7cfe8a3c0aae11a8ffcee05c0bddf08c6"
VPNGATE_TLS_NAME = "opengw.net"

REQUIRED_COLUMNS = {
    "HostName",
    "IP",
    "Score",
    "Ping",
    "Speed",
    "CountryLong",
    "CountryShort",
    "NumVpnSessions",
    "OpenVPN_ConfigData_Base64",
}

# VPNGate profiles are data, but OpenVPN profiles can also launch programs.
# Keep the accepted surface limited to connection and TLS settings.
SAFE_DIRECTIVES = {
    "auth",
    "cipher",
    "client",
    "connect-retry",
    "connect-retry-max",
    "connect-timeout",
    "data-ciphers",
    "data-ciphers-fallback",
    "dev",
    "dev-type",
    "dhcp-option",
    "explicit-exit-notify",
    "keepalive",
    "key-direction",
    "mute",
    "nobind",
    "persist-key",
    "persist-tun",
    "ping",
    "ping-restart",
    "ping-timer-rem",
    "proto",
    "pull",
    "rcvbuf",
    "remote",
    "remote-cert-tls",
    "remote-random",
    "remote-random-hostname",
    "reneg-sec",
    "resolv-retry",
    "route-delay",
    "sndbuf",
    "tls-cipher",
    "tls-ciphersuites",
    "tls-client",
    "tls-version-min",
    "verb",
    "verify-x509-name",
}
SAFE_INLINE_BLOCKS = {"ca", "cert", "key", "tls-auth", "tls-crypt"}


def decode_config(encoded: str) -> str:
    compact = "".join(str(encoded or "").split())
    if not compact:
        raise ValueError("OpenVPN configuration is empty")
    raw = base64.b64decode(compact.encode("ascii"), validate=True)
    if not raw or len(raw) > MAX_CONFIG_BYTES:
        raise ValueError("OpenVPN configuration size is invalid")
    return raw.decode("utf-8", errors="strict")


_INLINE_LABELS = {
    "ca": {"CERTIFICATE"},
    "cert": {"CERTIFICATE"},
    "key": {"PRIVATE KEY", "RSA PRIVATE KEY", "EC PRIVATE KEY", "ENCRYPTED PRIVATE KEY"},
    "tls-auth": {"OpenVPN Static key V1"},
    "tls-crypt": {"OpenVPN Static key V1"},
}
_PROTOCOLS = {"udp", "udp4", "udp6", "tcp", "tcp4", "tcp6", "tcp-client", "tcp4-client", "tcp6-client"}
_OPTION_TOKEN = re.compile(r"[A-Za-z0-9_.,:%+=!@*-]+\Z", re.ASCII)
_HOST_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\Z", re.ASCII)


def valid_remote_host(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return "%" not in host
    except ValueError:
        name = host.removesuffix(".")
        return 0 < len(name) <= 253 and all(_HOST_LABEL.fullmatch(label) for label in name.split("."))


def _validate_inline_block(tag: str, lines: list[str]) -> list[bytes]:
    certificates = []
    label = None
    data: list[str] = []
    for line in lines:
        if label is None:
            opening = re.fullmatch(r"-----BEGIN (.+)-----", line)
            if not opening or opening[1] not in _INLINE_LABELS[tag]:
                raise ValueError(f"Invalid OpenVPN {tag} header")
            label = opening[1]
        elif line == f"-----END {label}-----":
            joined = "".join(data)
            if not joined:
                raise ValueError(f"Empty OpenVPN {tag} data")
            if tag in {"tls-auth", "tls-crypt"}:
                bytes.fromhex(joined)
            else:
                decoded = base64.b64decode(joined, validate=True)
                if tag == "ca":
                    certificates.append(decoded)
            label = None
            data.clear()
        elif re.fullmatch(r"[A-Za-z0-9+/=]+", line, re.ASCII):
            data.append(line)
        else:
            raise ValueError(f"Invalid OpenVPN {tag} data")
    if label is not None or not lines:
        raise ValueError(f"Incomplete OpenVPN {tag} block")
    return certificates


def validate_openvpn_config(config_text: str) -> str:
    """Return the canonical profile that may be passed to OpenVPN."""
    if not config_text or len(config_text.encode("utf-8")) > MAX_CONFIG_BYTES:
        raise ValueError("OpenVPN configuration size is invalid")
    config_text = config_text.replace("\r\n", "\n")
    if re.search(r"[\x00-\x08\x0b-\x1f\x7f-\x9f\u2028\u2029]", config_text):
        raise ValueError("OpenVPN configuration contains a noncanonical control character")

    canonical: list[str] = []
    directives: set[str] = set()
    blocks: set[str] = set()
    current_block = None
    block_data: list[str] = []
    shared_ca = False
    for raw_line in config_text.split("\n"):
        if len(raw_line.encode("utf-8")) > MAX_CONFIG_LINE_BYTES:
            raise ValueError("OpenVPN configuration line is too long")
        line = raw_line.strip(" \t")
        if not line or line.startswith(("#", ";")):
            continue
        if current_block is not None:
            if line == f"</{current_block}>":
                certificates = _validate_inline_block(current_block, block_data)
                shared_ca |= any(hashlib.sha256(cert).hexdigest() == VPNGATE_SHARED_CA_SHA256 for cert in certificates)
                canonical.extend([f"<{current_block}>", *block_data, line])
                blocks.add(current_block)
                current_block = None
                block_data = []
            else:
                block_data.append(line)
            continue
        if line.startswith("<"):
            tag = line[1:-1]
            if not line.endswith(">") or tag not in SAFE_INLINE_BLOCKS or tag in blocks:
                raise ValueError("Unexpected or duplicate OpenVPN inline block")
            current_block = tag
            continue

        parts = re.split(r"[ \t]+", line)
        directive = parts[0].removeprefix("--")
        args = parts[1:]
        if directive not in SAFE_DIRECTIVES or any(not _OPTION_TOKEN.fullmatch(arg) for arg in args):
            raise ValueError("Unsafe OpenVPN directive or arguments")
        if directive == "remote":
            valid = (
                len(args) in {2, 3} and valid_remote_host(args[0])
                and re.fullmatch(r"[0-9]{1,5}", args[1], re.ASCII)
                and 1 <= int(args[1]) <= 65535
                and (len(args) == 2 or args[2] in _PROTOCOLS)
            )
            if not valid:
                raise ValueError("Invalid OpenVPN remote endpoint")
        elif directive == "dev" and (len(args) != 1 or not re.fullmatch(r"tun[0-9]*", args[0])):
            raise ValueError("Only TUN OpenVPN devices are accepted")
        elif directive == "dev-type" and args != ["tun"]:
            raise ValueError("Only the TUN OpenVPN device type is accepted")
        elif directive == "proto" and (len(args) != 1 or args[0] not in _PROTOCOLS):
            raise ValueError("Invalid OpenVPN client protocol")
        elif directive in {"auth", "cipher", "data-ciphers", "data-ciphers-fallback"}:
            if len(args) != 1 or {"none", "null"}.intersection(args[0].lower().split(":")):
                raise ValueError("Invalid OpenVPN cipher or authentication algorithm")
        directives.add(directive)
        canonical.append(" ".join([directive, *args]))

    if current_block is not None:
        raise ValueError("Unclosed OpenVPN inline block")
    if not {"client", "remote"}.issubset(directives):
        raise ValueError("OpenVPN client or remote directive is missing")
    if not {"ca", "cert", "key"}.issubset(blocks):
        raise ValueError("OpenVPN certificate blocks are incomplete")
    if shared_ca:
        canonical = [line for line in canonical if line.split(" ", 1)[0] != "verify-x509-name"]
        canonical.append(f"verify-x509-name {VPNGATE_TLS_NAME} name")
    return "\n".join(canonical) + "\n"


def parse_and_validate_snapshot(text: str, max_rows: int | None = None) -> list[dict[str, str]]:
    raw_size = len(text.encode("utf-8"))
    if raw_size <= 0 or raw_size > MAX_SNAPSHOT_BYTES:
        raise ValueError("VPNGate snapshot size is invalid")

    lines = [line for line in text.splitlines() if line and not line.startswith("*")]
    if not lines:
        raise ValueError("VPNGate snapshot is empty")
    if lines[0].startswith("#"):
        lines[0] = lines[0][1:]

    reader = csv.DictReader(io.StringIO("\n".join(lines)))
    fieldnames = set(reader.fieldnames or [])
    if not REQUIRED_COLUMNS.issubset(fieldnames):
        raise ValueError("VPNGate snapshot columns are incomplete")

    rows: list[dict[str, str]] = []
    for row in reader:
        normalized = {str(key): str(value or "") for key, value in row.items() if key is not None}
        if not valid_remote_host(normalized.get("IP", "")) or not normalized.get("OpenVPN_ConfigData_Base64"):
            continue
        try:
            config_text = decode_config(normalized["OpenVPN_ConfigData_Base64"])
            validate_openvpn_config(config_text)
        except (UnicodeError, ValueError):
            continue
        rows.append(normalized)
        if max_rows is not None and len(rows) >= max_rows:
            break
    if not rows:
        raise ValueError("VPNGate snapshot contains no valid nodes")
    return rows


def snapshot_summary(text: str) -> dict[str, Any]:
    rows = parse_and_validate_snapshot(text)
    return {"row_count": len(rows), "byte_count": len(text.encode("utf-8"))}
