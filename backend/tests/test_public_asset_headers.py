from __future__ import annotations

from unittest.mock import patch

from starlette.requests import Request

from app.routers.sharing import get_public_brand_asset

_SVG_WITH_SCRIPT = (
    b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(document.domain)</script></svg>'
)


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/public/assets/brand-assets/x/logo.svg",
            "headers": [],
            "client": ("127.0.0.1", 1234),
            "server": ("test", 80),
            "scheme": "http",
            "query_string": b"",
        }
    )


def test_public_asset_serves_active_svg_as_inert_download():
    """A re-hosted SVG must not execute in the application origin."""
    with patch("app.routers.sharing.get_bytes", return_value=_SVG_WITH_SCRIPT):
        response = get_public_brand_asset(_request(), "brand-assets/x/logo.svg")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/svg+xml"
    assert response.headers["content-disposition"] == "attachment"
    assert "sandbox" in response.headers["content-security-policy"]
    assert "default-src 'none'" in response.headers["content-security-policy"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "public, max-age=86400"
