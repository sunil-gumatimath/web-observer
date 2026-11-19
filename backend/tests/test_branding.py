from app.services import branding
from app.services.branding import fetch_brand_info, parse_brand_meta
from app.services.fetcher import FetchError


def test_parse_brand_meta_og_image():
    html = '<html><head><meta property="og:image" content="/img/cover.jpg"></head></html>'
    meta = parse_brand_meta(html, "https://example.com/item")
    assert "https://example.com/img/cover.jpg" in meta.hero_candidates


def test_parse_brand_meta_json_ld_product():
    html = """
    <html>
      <head>
        <script type="application/ld+json">
        {
          "@context": "https://schema.org/",
          "@type": "Product",
          "name": "Wireless Earbuds",
          "image": "https://example.com/product.png"
        }
        </script>
      </head>
    </html>
    """
    meta = parse_brand_meta(html, "https://example.com/p/123")
    assert "https://example.com/product.png" in meta.hero_candidates


def test_parse_brand_meta_json_ld_array():
    html = """
    <html>
      <head>
        <script type="application/ld+json">
        {
          "@context": "https://schema.org/",
          "@type": "Product",
          "image": ["https://example.com/p1.png", "https://example.com/p2.png"]
        }
        </script>
      </head>
    </html>
    """
    meta = parse_brand_meta(html, "https://example.com/p/123")
    assert "https://example.com/p1.png" in meta.hero_candidates
    assert "https://example.com/p2.png" in meta.hero_candidates


def test_parse_brand_meta_product_meta_tags():
    html = '<html><head><meta property="product:image" content="https://example.com/prod.jpg"></head></html>'
    meta = parse_brand_meta(html, "https://example.com")
    assert "https://example.com/prod.jpg" in meta.hero_candidates


def test_parse_brand_meta_link_image_src():
    html = '<html><head><link rel="image_src" href="https://example.com/preview.png"></head></html>'
    meta = parse_brand_meta(html, "https://example.com")
    assert "https://example.com/preview.png" in meta.hero_candidates


def test_parse_brand_meta_img_fallback():
    html = '<html><body><img id="landingImage" src="https://example.com/landing.jpg"></body></html>'
    meta = parse_brand_meta(html, "https://example.com")
    assert "https://example.com/landing.jpg" in meta.hero_candidates


def test_fetch_brand_info_uses_logo_fallbacks_when_page_fetch_fails(monkeypatch):
    """Sites that block the HTML fetch must still get a favicon/logo preview."""

    def blocked(*_args, **_kwargs):
        raise FetchError("blocked", "blocked")

    monkeypatch.setattr(branding, "fetch_url", blocked)
    meta = fetch_brand_info("https://openai.com/news/")

    assert "https://logo.clearbit.com/openai.com?size=256" in meta.logo_candidates
    assert "https://www.google.com/s2/favicons?domain=openai.com&sz=256" in meta.logo_candidates
    assert "https://openai.com/favicon.ico" in meta.logo_candidates


def test_store_brand_assets_keeps_live_preview(monkeypatch):
    """Re-scraping logo/hero must not drop the captured live page preview."""
    from types import SimpleNamespace
    from uuid import uuid4

    monkeypatch.setattr(branding, "_download_image", lambda *_a, **_k: None)
    monitor = SimpleNamespace(
        id=uuid4(),
        brand={"preview_path": "brand-assets/x/preview.png", "preview_at": "2026-01-01T00:00:00+00:00"},
    )

    brand = branding.store_brand_assets(monitor, branding.BrandMeta(title="Example"))

    assert brand["preview_path"] == "brand-assets/x/preview.png"
    assert brand["preview_at"] == "2026-01-01T00:00:00+00:00"


def test_store_live_preview_stores_viewport_screenshot(monkeypatch):
    from types import SimpleNamespace
    from uuid import uuid4

    from app.services import visual

    calls: dict = {}

    def fake_capture(url, **kwargs):
        calls["capture"] = (url, kwargs)
        return SimpleNamespace(png_bytes=b"png-bytes")

    def fake_put(*, key, data, content_type):
        calls["put"] = (key, data, content_type)

    monkeypatch.setattr(visual, "capture_screenshot", fake_capture)
    monkeypatch.setattr(branding, "put_bytes", fake_put)
    monitor_id = uuid4()

    key = branding.store_live_preview(monitor_id, "https://blog.cloudflare.com")

    assert key == f"brand-assets/{monitor_id}/preview.png"
    assert calls["capture"][0] == "https://blog.cloudflare.com"
    assert calls["capture"][1]["full_page"] is False
    assert calls["put"] == (key, b"png-bytes", "image/png")
