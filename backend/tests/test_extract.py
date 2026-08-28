import pytest

from app.services.extract import (
    ExtractionError,
    content_hash,
    extract_main_markdown,
    extract_markdown,
    extract_price,
    extract_text,
    normalize_text,
)


def test_normalize_collapses_whitespace() -> None:
    assert normalize_text("a  b\r\n\r\nc") == "a b\nc"


def test_page_content_strips_script() -> None:
    html = """
    <html><body>
      <script>secret()</script>
      <p>Hello</p>
      <style>.x{}</style>
    </body></html>
    """
    text = extract_text(html)
    assert "Hello" in text
    assert "secret" not in text


def test_extract_price_symbol() -> None:
    html = "<html><body><div class='price'>$9.99</div></body></html>"
    assert extract_price(html) == "USD 9.99"


def test_extract_price_code() -> None:
    # Code-led matches normalize to the same "CODE amount" shape as
    # symbol-led matches so hashes stay comparable across formats.
    html = "<html><body><span>19.99 EUR</span></body></html>"
    assert extract_price(html) == "EUR 19.99"


def test_extract_price_missing() -> None:
    try:
        extract_price("<html><body><p>no price here</p></body></html>")
        raise AssertionError("expected ExtractionError")
    except ExtractionError as exc:
        # Distinct code lets the pipeline treat a vanished price as a change.
        assert exc.code == "price_not_found"


# ---------------------------------------------------------------------------
# product_price hardening: script exclusion, EU formats, selector scoping
# ---------------------------------------------------------------------------


def test_extract_price_ignores_scripts_and_json_blobs() -> None:
    """A price inside <script> (JSON-LD / dataLayer) must not shadow the
    rendered price — scripts are decomposed before scanning."""
    html = """
    <html><head>
      <script type="application/ld+json">
        {"price": "999.00", "currency": "USD"}
      </script>
    </head><body>
      <span class="price">$19.99</span>
    </body></html>
    """
    assert extract_price(html) == "USD 19.99"


def test_extract_price_european_decimal_comma() -> None:
    html = "<html><body><span>19,99 \u20ac</span></body></html>"
    assert extract_price(html) == "EUR 19.99"


def test_extract_price_european_leading_symbol_grouping() -> None:
    html = "<html><body><span>\u20ac 1.299,00</span></body></html>"
    assert extract_price(html) == "EUR 1299.00"


def test_extract_price_symbol_after_number() -> None:
    html = "<html><body><span>1.200 \u00a5</span></body></html>"
    assert extract_price(html) == "JPY 1200"


def test_extract_price_css_selector_scopes_search() -> None:
    """An optional css_selector restricts the scan to the matching subtree."""
    html = (
        "<html><body>"
        "<span class='related'>$4.50</span>"
        "<div id='main'><span>$24.90</span></div>"
        "</body></html>"
    )
    assert extract_price(html, css_selector="#main") == "USD 24.90"
    # Without a selector the first match in DOM order wins.
    assert extract_price(html) == "USD 4.50"


def test_extract_price_ignore_selectors_remove_noise() -> None:
    html = (
        "<html><body><nav><span>$1.00</span></nav><span class='price'>$12.34</span></body></html>"
    )
    assert extract_price(html, ignore_selectors=["nav"]) == "USD 12.34"


def test_content_hash_stable() -> None:
    assert content_hash("hello") == content_hash("hello")
    assert content_hash("hello") != content_hash("world")
    assert len(content_hash("hello")) == 64


# ---------------------------------------------------------------------------
# page_content markdown: images survive extraction
# ---------------------------------------------------------------------------


def test_markdown_keeps_top_level_images() -> None:
    pytest.importorskip("markdownify")
    html = '<html><body><p>intro</p><img src="https://x.test/a.png" alt="A"></body></html>'
    md = extract_markdown(html)
    assert "![A](https://x.test/a.png)" in md


def test_markdown_keeps_images_inside_links_and_spans() -> None:
    """markdownify drops <img> nested in inline elements unless
    keep_inline_images_in includes those parents (linked logos/thumbnails)."""
    pytest.importorskip("markdownify")
    html = (
        "<html><body>"
        '<a href="/home"><img src="/logo.png" alt="Logo"></a>'
        "<span><img src='/icon.svg' alt='Icon'></span>"
        "</body></html>"
    )
    md = extract_markdown(html)
    assert "![Logo](/logo.png)" in md
    assert "![Icon](/icon.svg)" in md


# ---------------------------------------------------------------------------
# page_content main-content extraction (webdog useMainContentOnly parity)
# ---------------------------------------------------------------------------

_NAV_ARTICLE_HTML = """
<html><body>
  <nav>
    <a href="/">Home</a> | <a href="/about">About</a> | <a href="/login">Login</a>
  </nav>
  <header><img src="/logo.png" alt="Site logo"></header>
  <article>
    <h1>Why the moon is made of cheese</h1>
    <p>Astronomers have long suspected it. Recent lunar missions confirmed a
    high dairy content across every regolith sample collected since 1969,
    with brie dominating the southern craters and a hard aged cheddar
    near the north pole.</p>
    <p>The implications for pizza supply chains are profound. Scientists
    now believe mozzarella deposits may exist beneath the Tycho crater,
    though melting temperatures on the sunlit side remain a challenge.</p>
    <img src="/moon.jpg" alt="The moon">
  </article>
  <footer>© 2026 Example Corp · Privacy · Terms · Cookie preferences</footer>
</body></html>
"""


def test_main_markdown_strips_nav_and_boilerplate() -> None:
    trafilatura = pytest.importorskip("trafilatura")
    md = extract_main_markdown(_NAV_ARTICLE_HTML, base_url="https://example.test/")
    assert md is not None
    assert "cheese" in md.lower()
    # boilerplate gone
    assert "Privacy" not in md
    assert "Login" not in md


def test_main_markdown_keeps_article_images_and_resolves_relative_urls() -> None:
    pytest.importorskip("trafilatura")
    md = extract_main_markdown(_NAV_ARTICLE_HTML, base_url="https://example.test/a")
    assert md is not None
    assert "](https://example.test/moon.jpg)" in md


def test_main_markdown_falls_back_to_none_on_shell_page() -> None:
    """A page with no detectable article returns None so callers fall back."""
    trafilatura = pytest.importorskip("trafilatura")
    shell = "<html><body><div>hi</div><span>loading…</span></body></html>"
    assert extract_main_markdown(shell) is None
