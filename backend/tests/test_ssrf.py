import ipaddress

import pytest

from app.security.ssrf import (
    SSRFError,
    ValidatedURL,
    browser_host_resolver_arg,
    is_same_browser_host,
    validate_ip_address,
    validate_url_for_fetch,
)


def test_rejects_non_http_schemes() -> None:
    with pytest.raises(SSRFError) as exc:
        validate_url_for_fetch("ftp://example.com/file", resolve_dns=False)
    assert exc.value.code == "invalid_url"


def test_rejects_embedded_credentials() -> None:
    with pytest.raises(SSRFError) as exc:
        validate_url_for_fetch("https://user:pass@example.com/", resolve_dns=False)
    assert exc.value.code == "invalid_url"


def test_rejects_localhost_hostname() -> None:
    with pytest.raises(SSRFError) as exc:
        validate_url_for_fetch("http://localhost/admin", resolve_dns=False)
    assert exc.value.code == "blocked_address"


def test_rejects_loopback_literal() -> None:
    with pytest.raises(SSRFError) as exc:
        validate_url_for_fetch("http://127.0.0.1/", resolve_dns=False)
    assert exc.value.code == "blocked_address"


def test_rejects_metadata_ip() -> None:
    with pytest.raises(SSRFError) as exc:
        validate_url_for_fetch("http://169.254.169.254/latest/meta-data/", resolve_dns=False)
    assert exc.value.code == "blocked_address"


def test_rejects_private_literal() -> None:
    for url in (
        "http://10.0.0.1/",
        "http://192.168.1.1/",
        "http://172.16.0.5/",
    ):
        with pytest.raises(SSRFError) as exc:
            validate_url_for_fetch(url, resolve_dns=False)
        assert exc.value.code == "blocked_address"


def test_rejects_ipv6_loopback() -> None:
    with pytest.raises(SSRFError) as exc:
        validate_url_for_fetch("http://[::1]/", resolve_dns=False)
    assert exc.value.code == "blocked_address"


def test_allows_public_literal() -> None:
    # 1.1.1.1 is public Cloudflare DNS
    result = validate_url_for_fetch("https://1.1.1.1/", resolve_dns=False)
    assert result.resolved_ips == ["1.1.1.1"]


def test_browser_host_resolver_pins_validated_address_and_denies_other_hosts() -> None:
    validated = ValidatedURL(
        url="https://example.com/",
        hostname="example.com",
        resolved_ips=["93.184.216.34"],
    )

    assert browser_host_resolver_arg(validated) == (
        "--host-resolver-rules=MAP example.com 93.184.216.34,MAP * ~NOTFOUND"
    )
    assert is_same_browser_host("https://EXAMPLE.com./asset.js", "example.com")
    assert not is_same_browser_host("http://169.254.169.254/latest", "example.com")
    assert not is_same_browser_host("https://attacker.example/", "example.com")


def test_browser_host_resolver_requires_validated_ip() -> None:
    with pytest.raises(SSRFError) as exc:
        browser_host_resolver_arg(ValidatedURL("https://example.com", "example.com", []))
    assert exc.value.code == "dns_error"


def test_validate_ip_blocks_link_local() -> None:
    with pytest.raises(SSRFError):
        validate_ip_address("169.254.1.1")


def test_blocked_networks_cover_cgnat() -> None:
    ip = ipaddress.ip_address("100.64.0.10")
    with pytest.raises(SSRFError):
        validate_ip_address(str(ip))
