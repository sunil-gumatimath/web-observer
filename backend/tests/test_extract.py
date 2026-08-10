from app.services.extract import ExtractionError, content_hash, extract_price, extract_text, normalize_text


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
    html = "<html><body><span>19.99 EUR</span></body></html>"
    assert extract_price(html) == "19.99"


def test_extract_price_missing() -> None:
    try:
        extract_price("<html><body><p>no price here</p></body></html>")
        raise AssertionError("expected ExtractionError")
    except ExtractionError as exc:
        assert exc.code == "extraction_failed"


def test_content_hash_stable() -> None:
    a = content_hash("hello")
    b = content_hash("hello")
    c = content_hash("hello!")
    assert a == b
    assert a != c
