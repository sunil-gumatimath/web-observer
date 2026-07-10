import io

from app.services.visual import average_hash, hamming_distance_hex, hashes_similar


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


def test_same_image_same_hash() -> None:
    png = _gradient_png(True)
    a = average_hash(png)
    b = average_hash(png)
    assert a == b
    assert hashes_similar(a, b, max_distance=0)


def test_different_patterns_distant() -> None:
    a = average_hash(_gradient_png(True))
    b = average_hash(_gradient_png(False))
    assert hamming_distance_hex(a, b) > 5
