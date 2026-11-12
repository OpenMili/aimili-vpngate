"""Resolve manual targets from the existing node registry, never arbitrary URLs."""
from __future__ import annotations

import ipaddress
import re
from typing import Any


class TargetError(ValueError):
    def __init__(self, message: str, status: int = 400, candidates: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.status = status
        self.candidates = candidates or []


def public_node(node: dict[str, Any]) -> dict[str, Any]:
    return {key: node.get(key) for key in (
        "id", "ip", "country", "country_short", "remote_port", "proto",
        "probe_status", "latency_ms",
    )}


def numeric_ip(value: Any) -> str:
    if not isinstance(value, str) or "%" in value:
        raise TargetError("IP 必须是 IPv4 或 IPv6 地址，不能使用域名或 URL")
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError as exc:
        raise TargetError("IP 必须是 IPv4 或 IPv6 地址，不能使用域名或 URL") from exc


def node_ip_matches(node: dict[str, Any], target: str) -> bool:
    try:
        return numeric_ip(node.get("ip")) == target
    except TargetError:
        return False


def priority(node: dict[str, Any]) -> tuple[int, int, int, str]:
    def number(key: str, default: int) -> int:
        try:
            return int(node.get(key) or default)
        except (ValueError, TypeError):
            return default

    latency = number("latency_ms", 0)
    return (
        0 if node.get("probe_status") == "available" else 1,
        latency if latency > 0 else 2**31,
        -number("score", 0),
        str(node.get("id") or ""),
    )


def country_codes(value: Any, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or len(value) > 250:
        raise TargetError("countries 必须为国家代码列表，例如 [\"US\", \"CA\"]")
    if any(not isinstance(code, str) or not re.fullmatch(r"[A-Za-z]{2}", code.strip())
           for code in value):
        raise TargetError("每个国家必须使用两位代码，例如 US 或 CA")
    countries = sorted({code.strip().upper() for code in value})
    if not countries and not allow_empty:
        raise TargetError("请至少选择一个出口国家")
    return countries


def routing_countries(config: dict[str, Any]) -> list[str]:
    """Read the country set, retaining old code/name-based single-country files."""
    value = config.get("force_countries", [])
    if value:
        try:
            return country_codes(value)
        except TargetError:
            return []  # An invalid restriction must never allow every country.
    legacy = config.get("force_country")
    return [legacy.strip()] if isinstance(legacy, str) and legacy.strip() else []


def resolve_target(nodes: list[dict[str, Any]], payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    if not isinstance(payload, dict):
        raise TargetError("请求 JSON 必须是对象")
    mode = payload.get("mode")
    allowed = {"mode", "ip", "node_id"} if mode == "ip" else {"mode", "country", "countries"}
    if mode not in ("ip", "country") or set(payload) - allowed:
        raise TargetError("仅支持 mode=ip 或 country，请勿混合字段或传入未知字段")
    if mode == "ip":
        target_ip = numeric_ip(payload.get("ip"))
        candidates = [node for node in nodes if node.get("id") and node_ip_matches(node, target_ip)]
        node_id = payload.get("node_id")
        if "node_id" in payload:
            if not isinstance(node_id, str) or not node_id.strip():
                raise TargetError("node_id 必须为非空字符串")
            candidates = [node for node in candidates if node["id"] == node_id]
        if not candidates:
            raise TargetError("节点列表中没有匹配的 IP / node_id；请先更新节点", 404)
        if len(candidates) > 1:
            raise TargetError("同一 IP 对应多个节点，请使用候选 node_id 明确选择", 409,
                              [public_node(node) for node in candidates])
        selected = candidates[0]
        return str(selected["id"]), {
            "routing_mode": "fixed_ip", "fixed_node_id": selected["id"],
            "force_country": "", "force_countries": [], "routing_ip_type": "all", "fav_fail_fallback": False,
        }

    if "country" in payload and "countries" in payload:
        raise TargetError("country 与 countries 不能同时使用")
    countries = country_codes(payload.get("countries") if "countries" in payload else [payload.get("country")])
    candidates = [node for node in nodes if node.get("id")
                  and str(node.get("country_short") or "").upper() in countries
                  and node.get("probe_status") != "unavailable"]
    if not candidates:
        raise TargetError("所选国家没有可用或待检测节点；当前连接保持不变，请先更新/测试节点", 503)
    selected = min(candidates, key=priority)
    return str(selected["id"]), {
        "routing_mode": "fixed_region", "force_country": countries[0] if len(countries) == 1 else "",
        "force_countries": countries, "fixed_node_id": "",
        "routing_ip_type": "all", "fav_fail_fallback": False,
    }


def routing_signature(config: dict[str, Any]) -> tuple[Any, ...]:
    """Detect policy edits during preflight/verification without locking the UI."""
    return (tuple(sorted(routing_countries(config))),) + tuple(config.get(key) for key in (
        "routing_mode", "force_country", "routing_ip_type", "fixed_node_id",
        "connection_enabled", "favorite_node_ids", "fav_fail_fallback",
    ))
