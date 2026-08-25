from app.services.extract import (
    ExtractionError,
    content_hash,
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
