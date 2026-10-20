import io

from app.services.visual import (
    average_hash,
    hamming_distance_hex,
    perceptual_hash,
    visual_diff_summary,
)


def _gradient_png(horizontal: bool = True) -> bytes:
    from PIL import Image

    img = Image.new("RGB", (64, 64))
    pixels = img.load()
    assert pixels is not None
    for y in range(64):
        for x in range(64):
            v = x if horizontal else y
            pixels[x, y] = (v * 4, v * 4, v * 4)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _news_page_png(extra_headline: bool = False) -> bytes:
    """A text-heavy page like the ones web monitoring actually targets."""
    from PIL import Image, ImageDraw

    img = Image.new("L", (1280, 1246), 255)
    draw = ImageDraw.Draw(img)
    y = 40
    headlines = [f"Story headline number {i}" for i in range(25)]
    if extra_headline:
        headlines.insert(0, "A brand new headline")
    for text in headlines:
        draw.rectangle([60, y, 60 + len(text) * 8, y + 20], fill=0)
        y += 36
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_same_image_same_hash() -> None:
    png = _gradient_png(True)
    a = average_hash(png)
    b = average_hash(png)
    assert a == b


def test_different_patterns_distant() -> None:
    a = average_hash(_gradient_png(True))
    b = average_hash(_gradient_png(False))
    assert hamming_distance_hex(a, b) > 5


# ---------------------------------------------------------------------------
# Perceptual hash (pHash) — the digest the visual mode compares
# ---------------------------------------------------------------------------


def test_phash_stable_for_identical_image() -> None:
    png = _news_page_png()
    assert perceptual_hash(png) == perceptual_hash(png)


def test_phash_reacts_to_a_single_added_headline() -> None:
    """The aHash blind spot this replaces.

    aHash compares every pixel against the image mean. On a text-heavy page
    (mostly white) the digest barely moves: adding a headline shifted it by
    0 bits out of 64, so every genuine edit stayed under the "similar"
    threshold and was reported as "no change". pHash must react.
    """
    base = _news_page_png()
    changed = _news_page_png(extra_headline=True)

    assert hamming_distance_hex(average_hash(base), average_hash(changed)) <= 5
    assert hamming_distance_hex(perceptual_hash(base), perceptual_hash(changed)) > 8


def test_visual_diff_summary_prefers_phash() -> None:
    prev = "ahash:ffe7c3e7e7e7e7e7\nphash:" + "aa" * 32 + "\nsha256:aa\nsize:1280x775"
    new = "ahash:ffe7c3e7e7e7e7e7\nphash:" + "ab" * 32 + "\nsha256:bb\nsize:1280x775"
    summary, diff = visual_diff_summary(prev, new, threshold=5, phash_threshold=8)
    assert "Visual change detected" in summary
    assert "phash" in diff


def test_visual_diff_summary_unchanged_is_similar() -> None:
    prev = "ahash:ffe7c3e7e7e7e7e7\nphash:" + "aa" * 32 + "\nsha256:aa\nsize:1280x775"
    summary, _ = visual_diff_summary(prev, prev, threshold=5, phash_threshold=8)
    assert "Visual similar" in summary


def test_visual_diff_summary_falls_back_to_ahash() -> None:
    """Snapshots taken before pHash existed still compare on the aHash."""
    prev = "ahash:ffe7c3e7e7e7e7e7\nsha256:aa\nsize:1280x775"
    new = "ahash:ffe7c3e7e7e7e7e7\nsha256:bb\nsize:1280x775"
    summary, diff = visual_diff_summary(prev, new, threshold=5, phash_threshold=8)
    assert "Visual similar" in summary
    assert "ahash" in diff


def test_visual_diff_summary_never_silently_drops_a_change() -> None:
    """A corrupt digest must be reported as a change, not as 'similar'."""
    prev = "ahash:not-a-hex-digest\nsha256:aa"
    new = "ahash:ffe7c3e7e7e7e7e7\nsha256:bb"
    summary, _ = visual_diff_summary(prev, new, threshold=5, phash_threshold=8)
    assert "Visual similar" not in summary
