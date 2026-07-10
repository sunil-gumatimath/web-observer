"""Screenshot capture helpers and perceptual hashing."""

from __future__ import annotations

import hashlib
import io
import logging
from dataclasses import dataclass

from app.security.ssrf import validate_url_for_fetch
from app.services.fetcher import FetchError, FetchResult

logger = logging.getLogger(__name__)


def average_hash(image_bytes: bytes, *, hash_size: int = 8) -> str:
    """Compute a simple average hash (aHash) hex string using Pillow."""
    try:
        from PIL import Image
    except ImportError as exc:
        raise FetchError("internal_error", "Pillow is required for visual monitoring") from exc

    img = Image.open(io.BytesIO(image_bytes)).convert("L")
    img = img.resize((hash_size, hash_size), Image.Resampling.LANCZOS)
    pixels = list(img.getdata())
    avg = sum(pixels) / len(pixels)
    bits = "".join("1" if p >= avg else "0" for p in pixels)
    # pack to hex
    value = int(bits, 2)
    width = (hash_size * hash_size + 3) // 4
    return f"{value:0{width}x}"


def hamming_distance_hex(a: str, b: str) -> int:
    if len(a) != len(b):
        # pad shorter
        m = max(len(a), len(b))
        a = a.zfill(m)
        b = b.zfill(m)
    ai = int(a, 16)
    bi = int(b, 16)
    return (ai ^ bi).bit_count()


def hashes_similar(a: str, b: str, *, max_distance: int = 5) -> bool:
    return hamming_distance_hex(a, b) <= max_distance


@dataclass
class VisualCapture:
    png_bytes: bytes
    ahash: str
    sha256: str
    width: int
    height: int


def capture_screenshot(
    url: str,
    *,
    timeout_seconds: int = 45,
    full_page: bool = True,
    clip_selector: str | None = None,
) -> VisualCapture:
    """Capture page screenshot via Playwright."""
    validated = validate_url_for_fetch(url, resolve_dns=True)
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeout
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise FetchError("internal_error", "Playwright required for visual monitoring") from exc

    timeout_ms = max(10_000, timeout_seconds * 1000)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-dev-shm-usage", "--no-sandbox"],
            )
            try:
                page = browser.new_page(viewport={"width": 1280, "height": 720})
                page.goto(validated.url, wait_until="domcontentloaded", timeout=timeout_ms)
                try:
                    page.wait_for_load_state("networkidle", timeout=min(15_000, timeout_ms))
                except PlaywrightTimeout:
                    pass

                if clip_selector:
                    loc = page.locator(clip_selector).first
                    loc.wait_for(timeout=min(15_000, timeout_ms))
                    png = loc.screenshot(type="png")
                else:
                    png = page.screenshot(type="png", full_page=full_page)
            finally:
                browser.close()
    except PlaywrightTimeout as exc:
        raise FetchError("read_timeout", f"Visual capture timeout: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise FetchError("internal_error", f"Screenshot failed: {exc}") from exc

    ahash = average_hash(png)
    sha = hashlib.sha256(png).hexdigest()

    width, height = 0, 0
    try:
        from PIL import Image

        with Image.open(io.BytesIO(png)) as im:
            width, height = im.size
    except Exception:  # noqa: BLE001
        pass

    return VisualCapture(png_bytes=png, ahash=ahash, sha256=sha, width=width, height=height)


def visual_to_fetch_result(capture: VisualCapture, *, url: str) -> FetchResult:
    """Represent visual capture as FetchResult for pipeline (normalized = ahash line)."""
    normalized = f"ahash:{capture.ahash}\nsha256:{capture.sha256}\nsize:{capture.width}x{capture.height}"
    return FetchResult(
        final_url=url,
        status_code=200,
        content=capture.png_bytes,
        text=normalized,
        content_type="image/png",
        latency_ms=0,
    )


def visual_diff_summary(prev_text: str, new_text: str, *, threshold: int = 5) -> tuple[str, str]:
    """Return (summary, text_diff) for visual hashes stored in normalized_text."""
    def _parse_ahash(t: str) -> str:
        for line in t.splitlines():
            if line.startswith("ahash:"):
                return line.split(":", 1)[1].strip()
        return t.strip()

    pa, na = _parse_ahash(prev_text), _parse_ahash(new_text)
    dist = hamming_distance_hex(pa, na) if pa and na else 64
    similar = dist <= threshold
    if similar:
        summary = f"Visual similar (ahash distance={dist})"
    else:
        summary = f"Visual change detected (ahash distance={dist}, threshold={threshold})"
    diff = f"previous ahash: {pa}\nnew ahash:      {na}\ndistance:       {dist}\n"
    return summary, diff
