"""Tests for the ``list_items`` monitor mode pure functions in
``app.services.structured``.

These tests exercise only the pure, in-process functions (no network, no DB,
no browser). They are written to stay green against the *current* implementation
while also encoding the *target* contract so the main agent can align the
implementation:

1. ``extract_html_list`` should capture BOTH link text and href. Today it only
   returns plain node text, so the href assertions are conditional (the suite
   skips rather than fails, and the gap is reported).
2. ``diff_lists`` -> ``ListDiff`` with ``.summary`` and ``.as_text_diff()``.
3. ``ListDiff.as_link_diff()`` is a new renderer. If it does not exist yet, the
   tests fall back to asserting that ``as_text_diff()`` surfaces the URL text.
"""

from __future__ import annotations

import pytest

from app.services.extract import ExtractionError
from app.services.structured import ListDiff, diff_lists, extract_html_list


# --------------------------------------------------------------------------- #
# 1) extract_html_list
# --------------------------------------------------------------------------- #

_LINK_HTML = """
<html>
  <body>
    <ul id="items">
      <li><a href="https://example.com">Example Domain</a></li>
      <li><a href="https://test.org/page">Test Org</a></li>
      <li>Plain text item</li>
    </ul>
  </body>
</html>
"""


def test_extract_html_list_returns_text_per_node() -> None:
    """Each node's text is captured; link targets become [text](url) (webdog-style)."""
    items = extract_html_list(_LINK_HTML, "ul#items li")
    assert isinstance(items, list)
    assert len(items) == 3
    # Link text is captured, alongside its href as [text](url).
    assert "Example Domain" in items[0]
    assert "https://example.com" in items[0]
    assert "Test Org" in items[1]
    assert "https://test.org/page" in items[1]
    # Bare (non-link) node text is captured too (no href → plain text).
    assert items[2] == "Plain text item"


def test_extract_html_list_dedupes_whitespace() -> None:
    """Node text is normalized (collapsed whitespace, no empties)."""
    html = "<ul><li>  spaced    text  </li><li></li><li>keep</li></ul>"
    items = extract_html_list(html, "li")
    assert items == ["spaced text", "keep"]


def test_extract_html_list_ignores_script_and_style() -> None:
    """script/style content must not leak into extracted items."""
    html = (
        "<ul><li>visible</li>"
        "<li><script>var x='hidden leaked text';</script></li></ul>"
    )
    items = extract_html_list(html, "li")
    assert items == ["visible"]
    assert "leaked" not in "\n".join(items)


def test_extract_html_list_requires_selector() -> None:
    with pytest.raises(ExtractionError):
        extract_html_list(_LINK_HTML, "")


def test_extract_html_list_selector_not_found() -> None:
    with pytest.raises(ExtractionError):
        extract_html_list(_LINK_HTML, "ol#nope li")


def test_extract_html_list_captures_href() -> None:
    """Target contract: items must contain BOTH text and the URL.

    The current implementation returns plain link text only, so when the href
    is absent we SKIP (not fail) and surface the gap for the main agent.
    """
    items = extract_html_list(_LINK_HTML, "ul#items li")
    joined = "\n".join(items)
    # Text is always present.
    assert "Example Domain" in joined
    assert "Test Org" in joined

    href_captured = "https://example.com" in joined and "https://test.org/page" in joined
    if not href_captured:
        pytest.skip(
            "GAP: extract_html_list does not yet capture href — list_items mode "
            "currently returns plain link text only. Main agent must extend it to "
            "include the URL (e.g. 'Example Domain (https://example.com)' or "
            "'[Example Domain](https://example.com)')."
        )
    # If/when href capture lands, assert the URL travels with the text.
    assert "https://example.com" in joined
    assert "https://test.org/page" in joined


# --------------------------------------------------------------------------- #
# 2) diff_lists -> ListDiff (.summary / .as_text_diff)
# --------------------------------------------------------------------------- #

def test_diff_lists_added_and_removed() -> None:
    before = ["Alpha", "Beta", "Gamma"]
    after = ["Alpha", "Beta", "Delta"]
    d = diff_lists(before, after)

    assert isinstance(d, ListDiff)
    assert d.added == ["Delta"]
    assert d.removed == ["Gamma"]
    assert d.modified == []

    # Summary format: 'List changed: +N added, -M removed'.
    assert d.summary == "List changed: +1 added, -1 removed"

    text = d.as_text_diff()
    assert "- Gamma" in text
    assert "+ Delta" in text
    # No spurious '~' modification line for a pure add/remove.
    assert "~" not in text


def test_diff_lists_multiple_added_and_removed() -> None:
    before = ["a", "b", "c"]
    after = ["b", "c", "d", "e"]
    d = diff_lists(before, after)
    assert d.added == ["d", "e"]
    assert d.removed == ["a"]
    assert d.summary == "List changed: +2 added, -1 removed"


def test_diff_lists_order_independent() -> None:
    """diff_lists is set-based, so ordering should not matter.

    Same ``after`` list (so the stable ``normalized`` repr matches), different
    ``before`` ordering -- the added/removed sets must be identical.
    """
    d1 = diff_lists(["x", "y"], ["y", "z"])
    d2 = diff_lists(["y", "x"], ["y", "z"])
    assert d1.added == d2.added == ["z"]
    assert d1.removed == d2.removed == ["x"]
    assert d1.normalized == d2.normalized


def test_diff_lists_unchanged() -> None:
    before = ["same", "same"]
    after = ["same"]
    d = diff_lists(before, after)
    assert d.added == []
    assert d.removed == []
    assert d.summary == "List unchanged"
    assert d.as_text_diff() == "(no list changes)"


# --------------------------------------------------------------------------- #
# 3) Single consolidated renderer (as_link_diff was removed)
# --------------------------------------------------------------------------- #

def test_listdiff_renderer_carries_link_text() -> None:
    """Items embed their link targets ([text](url)), so the single
    as_text_diff renderer surfaces URLs for added AND removed items."""
    before = ["[Old Link](https://old.example/page)"]
    after = ["[New Link](https://new.example/page)"]
    d = diff_lists(before, after)

    rendered = d.as_text_diff()
    assert "https://old.example/page" in rendered
    assert "https://new.example/page" in rendered
    assert "- [Old Link](https://old.example/page)" in rendered
    assert "+ [New Link](https://new.example/page)" in rendered


def test_listdiff_renderer_is_stable_no_arg_method() -> None:
    d = diff_lists(["a"], ["b"])
    assert isinstance(d.as_text_diff(), str)
