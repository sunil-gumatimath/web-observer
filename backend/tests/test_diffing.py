from app.services.diffing import short_summary, unified_diff


def test_unified_diff_contains_change() -> None:
    diff = unified_diff("hello\n", "hello world\n")
    assert "hello" in diff
    assert "+" in diff or "-" in diff


def test_short_summary_baseline() -> None:
    s = short_summary("", "abc")
    assert "Baseline" in s or "baseline" in s.lower() or "chars" in s


def test_short_summary_change() -> None:
    s = short_summary("aaa", "bbb")
    assert "changed" in s.lower() or "similarity" in s.lower()
