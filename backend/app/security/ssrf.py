"""SSRF protection for user-supplied URLs.

Phase 1 core control: validate scheme, credentials, and resolved IPs before fetch.
Full redirect re-validation lives in the fetcher.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse


class SSRFError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


_BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]

_BLOCKED_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
    "metadata",
}


@dataclass(frozen=True)
class ValidatedURL:
    url: str
    hostname: str
    resolved_ips: list[str]


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
        return True
    if ip.is_unspecified:
        return True
    for network in _BLOCKED_NETWORKS:
        try:
            if ip in network:
                return True
        except TypeError:
            continue
    # Cloud metadata IPv4
    if str(ip) == "169.254.169.254":
        return True
    return False


def validate_url_for_fetch(url: str, *, resolve_dns: bool = True) -> ValidatedURL:
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise SSRFError("invalid_url", "Only http and https URLs are allowed")

    if parsed.username is not None or parsed.password is not None:
        raise SSRFError("invalid_url", "URLs with embedded credentials are not allowed")

    hostname = parsed.hostname
    if not hostname:
        raise SSRFError("invalid_url", "URL must include a hostname")

    host_lower = hostname.lower().rstrip(".")
    if host_lower in _BLOCKED_HOSTNAMES or host_lower.endswith(".localhost"):
        raise SSRFError("blocked_address", f"Hostname not allowed: {hostname}")

    # Literal IP in hostname
    try:
        literal_ip = ipaddress.ip_address(hostname)
    except ValueError:
        literal_ip = None

    if literal_ip is not None:
        if _is_blocked_ip(literal_ip):
            raise SSRFError("blocked_address", f"IP address not allowed: {hostname}")
        return ValidatedURL(url=url, hostname=hostname, resolved_ips=[str(literal_ip)])

    resolved_ips: list[str] = []
    if resolve_dns:
        try:
            infos = socket.getaddrinfo(hostname, parsed.port or 0, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise SSRFError("dns_error", f"DNS resolution failed for {hostname}") from exc

        for info in infos:
            ip_str = info[4][0]
            try:
                ip = ipaddress.ip_address(ip_str)
            except ValueError as exc:
                raise SSRFError("dns_error", f"Invalid resolved IP: {ip_str}") from exc
            if _is_blocked_ip(ip):
                raise SSRFError("blocked_address", f"Resolved IP not allowed: {ip_str}")
            if ip_str not in resolved_ips:
                resolved_ips.append(ip_str)

        if not resolved_ips:
            raise SSRFError("dns_error", f"No addresses resolved for {hostname}")

    return ValidatedURL(url=url, hostname=hostname, resolved_ips=resolved_ips)


def validate_ip_address(ip_str: str) -> None:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError as exc:
        raise SSRFError("blocked_address", f"Invalid IP: {ip_str}") from exc
    if _is_blocked_ip(ip):
        raise SSRFError("blocked_address", f"IP address not allowed: {ip_str}")
