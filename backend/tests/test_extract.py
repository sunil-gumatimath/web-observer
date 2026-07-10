from app.services.extract import ExtractionError, content_hash, extract_text, normalize_text


def test_normalize_collapses_whitespace() -> None:
    assert normalize_text("a  b\r\n\r\nc") == "a b\nc"


def test_whole_page_strips_script() -> None:
    html = """
    <html><body>
      <script>secret()</script>
      <p>Hello</p>
      <style>.x{}</style>
    </body></html>
    """
    text = extract_text(html, mode="whole_page")
    assert "Hello" in text
    assert "secret" not in text


def test_css_selector_extract() -> None:
    html = "<html><body><div class='price'>$9</div><div>noise</div></body></html>"
    text = extract_text(html, mode="css_selector", css_selector=".price")
    assert "$9" in text
    assert "noise" not in text


def test_selector_not_found() -> None:
    try:
        extract_text("<html><body><p>x</p></body></html>", mode="css_selector", css_selector=".missing")
        raise AssertionError("expected ExtractionError")
    except ExtractionError as exc:
        assert exc.code == "selector_not_found"


def test_content_hash_stable() -> None:
    a = content_hash("hello")
    b = content_hash("hello")
    c = content_hash("hello!")
    assert a == b
    assert a != c
