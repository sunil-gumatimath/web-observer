"""README markdown fidelity tests.

A README monitor must keep the *document shape* of the markdown:
paragraph breaks, nested list indentation and fenced-code indentation are
meaningful. ``normalize_text`` (used for scraped page text) drops all of
them, which made READMEs render as one flat blob and produced noisy
diffs — so the readme path uses ``normalize_markdown_text`` instead.
"""

from __future__ import annotations

from app.services.extract import normalize_markdown_text
from app.services.pipeline import extract_normalized
from app.services.readme import normalize_readme_url

README = """# Title

Intro paragraph.

- item a
  - nested item
- item b

```bash
echo "hi"
  indented code line
```

| a | b |
|---|---|
| 1 | 2 |
"""


def test_normalize_markdown_keeps_blank_lines() -> None:
    out = normalize_markdown_text(README)
    assert "# Title\n\nIntro paragraph." in out


def test_normalize_markdown_keeps_list_nesting() -> None:
    out = normalize_markdown_text(README)
    assert "  - nested item" in out


def test_normalize_markdown_keeps_code_indentation() -> None:
    out = normalize_markdown_text(README)
    assert "  indented code line" in out


def test_normalize_markdown_does_not_unescape_entities() -> None:
    # `&lt;div&gt;` inside a code block must stay literal (normalize_text
    # would rewrite it to `<div>`).
    out = normalize_markdown_text("```html\n&lt;div&gt;hi&lt;/div&gt;\n```")
    assert "&lt;div&gt;" in out
    assert "<div>" not in out


def test_normalize_markdown_normalizes_line_endings() -> None:
    out = normalize_markdown_text("a\r\nb\r\n")
    assert out == "a\nb"


def test_normalize_markdown_collapses_blank_runs() -> None:
    out = normalize_markdown_text("a\n\n\n\n\nb")
    assert out == "a\n\nb"


def test_readme_extraction_keeps_markdown_structure() -> None:
    class _Monitor:
        mode = "readme"
        css_selector = None
        ignore_selectors: list[str] = []
        ignore_regexes: list[str] = []

    class _Result:
        text = README
        final_url = "https://github.com/owner/repo"

    normalized, items = extract_normalized(_Monitor(), _Result())  # type: ignore[arg-type]
    assert items is None
    assert normalized == README.rstrip("\n")


def test_readme_url_canonicalization_unchanged() -> None:
    assert normalize_readme_url("owner/repo") == "https://github.com/owner/repo"
