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
