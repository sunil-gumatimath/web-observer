from app.services.extract import extract_text


def test_ignore_selector_removes_noise() -> None:
    html = """
    <html><body>
      <div class="cookie">Accept cookies</div>
      <main><p>Price $10</p></main>
    </body></html>
    """
    text = extract_text(
        html,
        ignore_selectors=[".cookie"],
    )
    assert "Price $10" in text
    assert "cookies" not in text.lower()


def test_ignore_regex_strips_timestamps() -> None:
    html = "<html><body><p>Hello</p><p>Updated 2026-07-10 12:00</p></body></html>"
    text = extract_text(
        html,
        ignore_regexes=[r"Updated .*"],
    )
    assert "Hello" in text
    assert "2026" not in text
