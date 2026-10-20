"""Screenshot capture helpers and perceptual hashing."""

from __future__ import annotations

import hashlib
import io
import json
import logging
import math
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.security.ssrf import validate_url_for_fetch
from app.services.fetcher import FetchError, FetchResult, detect_bot_challenge

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


# --- DCT perceptual hash (pHash) -------------------------------------------
#
# Why not aHash: the average hash compares every pixel against the image
# mean, so for a text-heavy page (mostly white background) nearly every bit
# is 1 and the digest barely moves. Measured on a real rendered page,
# rewriting a single headline changed the aHash by 1-2 bits out of 64 and
# removing a list item by 2 — i.e. every genuine edit stayed *below* the
# "similar" threshold and was silently reported as "no change".
#
# pHash compares the low-frequency 2D DCT spectrum instead, which reacts to
# localised layout/text changes. On the same real page the rewrite moved
# 12-36 bits, while two captures of an unchanged page are bit-identical
# (distance 0) even across separate browser launches.
_PHASH_INPUT_SIZE = 32
_PHASH_LOW_FREQ = 16  # 16x16 = 256 bits


def _dct_2d_low_freq(pixels: list[int], size: int, low_freq: int) -> list[list[float]]:
    """Low-frequency block of the 2D DCT-II of a square grayscale image.

    Pure Python on purpose: numpy is not a dependency of this project and a
    32x32 DCT is a few milliseconds of work per capture.
    """
    cos_table = [
        [math.cos(math.pi * (2 * i + 1) * k / (2 * size)) for i in range(size)] for k in range(size)
    ]
    # rows[r][k] = DCT along the row axis
    rows: list[list[float]] = []
    for r in range(size):
        row = pixels[r * size : (r + 1) * size]
        rows.append([sum(row[i] * cos_table[k][i] for i in range(size)) for k in range(size)])
    # cols[c][k] = DCT along the column axis of the row-transformed matrix
    cols: list[list[float]] = []
    for c in range(size):
        col = [rows[r][c] for r in range(size)]
        cols.append([sum(col[i] * cos_table[k][i] for i in range(size)) for k in range(size)])
    # cols[c][k_row] == D[k_row][k_col]
    return [[cols[c][k] for c in range(low_freq)] for k in range(low_freq)]


def perceptual_hash(
    image_bytes: bytes,
    *,
    input_size: int = _PHASH_INPUT_SIZE,
    low_freq: int = _PHASH_LOW_FREQ,
) -> str:
    """Compute a DCT perceptual hash (pHash) hex string using Pillow."""
    try:
        from PIL import Image
    except ImportError as exc:
        raise FetchError("internal_error", "Pillow is required for visual monitoring") from exc

    img = Image.open(io.BytesIO(image_bytes)).convert("L")
    img = img.resize((input_size, input_size), Image.Resampling.LANCZOS)
    pixels = list(img.getdata())
    low = _dct_2d_low_freq(pixels, input_size, low_freq)
    # Median of the AC coefficients decides which blocks are "darker" than
    # the average — the standard pHash construction.
    ac = [low[r][c] for r in range(low_freq) for c in range(low_freq) if (r or c)]
    med = sorted(ac)[len(ac) // 2]
    value = 0
    for r in range(low_freq):
        for c in range(low_freq):
            value = (value << 1) | (1 if low[r][c] > med else 0)
    width = (low_freq * low_freq + 3) // 4
    return f"{value:0{width}x}"


@dataclass
class VisualCapture:
    png_bytes: bytes
    ahash: str
    sha256: str
    width: int
    height: int
    # DCT perceptual hash (hex). Empty only for legacy captures produced
    # before pHash existed; the pipeline falls back to the aHash then.
    phash: str = ""


_DEFAULT_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

_LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-dev-shm-usage",
    "--no-sandbox",
    "--disable-gpu",
    "--disable-software-rasterizer",
    "--disable-extensions",
]


def _launch_chromium(p):  # type: ignore[no-untyped-def]
    """Launch Chromium with Windows-friendly options and a clear install error."""
    try:
        return p.chromium.launch(headless=True, args=_LAUNCH_ARGS)
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        # NOTE: no boolean operators in this handler (no-boolean-in-except).
        if "Executable doesn't exist" in msg:
            raise FetchError(
                "internal_error",
                "Playwright browsers are missing or outdated. "
                "Run: python -m playwright install chromium",
            ) from exc
        if "playwright install" in msg.lower():
            raise FetchError(
                "internal_error",
                "Playwright browsers are missing or outdated. "
                "Run: python -m playwright install chromium",
            ) from exc
        raise


def _capture_screenshot_inline(
    url: str,
    *,
    timeout_seconds: int = 45,
    full_page: bool = True,
    clip_selector: str | None = None,
) -> VisualCapture:
    """In-process Playwright capture. Prefer capture_screenshot() which isolates via subprocess."""
    validated = validate_url_for_fetch(url, resolve_dns=True)
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeout
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise FetchError("internal_error", "Playwright required for visual monitoring") from exc

    timeout_ms = max(10_000, timeout_seconds * 1000)
    png: bytes
    try:
        with sync_playwright() as p:
            browser = _launch_chromium(p)
            context = None
            try:
                context = browser.new_context(
                    user_agent=_DEFAULT_BROWSER_UA,
                    viewport={"width": 1280, "height": 720},
                    ignore_https_errors=False,
                )
                page = context.new_page()
                page.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    window.navigator.chrome = { runtime: {} };
                """)

                def _route_handler(route, request):  # type: ignore[no-untyped-def]
                    try:
                        validate_url_for_fetch(request.url, resolve_dns=True)
                    except Exception:
                        return route.abort()
                    return route.continue_()

                page.route("**/*", _route_handler)
                page.goto(validated.url, wait_until="domcontentloaded", timeout=timeout_ms)
                try:
                    page.wait_for_load_state("networkidle", timeout=min(20_000, timeout_ms))
                except PlaywrightTimeout:
                    # Best-effort: sites with long-lived connections never
                    # reach networkidle, so a timeout here is not an error.
                    logger.debug("networkidle_timeout url=%s", validated.url)

                # Sites with long-lived connections never reach networkidle.
                page.wait_for_timeout(1500)

                challenge = detect_bot_challenge(status_code=None, text=page.content())
                if challenge:
                    raise FetchError(
                        "bot_challenge",
                        f"Blocked while capturing {validated.url}: {challenge}. "
                        "The site requires a real browser session.",
                    )

                if clip_selector:
                    loc = page.locator(clip_selector).first
                    loc.wait_for(timeout=min(15_000, timeout_ms))
                    png = loc.screenshot(type="png")
                else:
                    try:
                        png = page.screenshot(type="png", full_page=full_page)
                    except Exception as shot_exc:  # noqa: BLE001
                        logger.warning(
                            "full_page_screenshot_failed error=%s; using viewport",
                            shot_exc,
                        )
                        png = page.screenshot(type="png", full_page=False)
            finally:
                if context is not None:
                    try:
                        context.close()
                    except Exception as close_exc:  # noqa: BLE001
                        logger.debug("context_close_failed error=%s", close_exc)
                try:
                    browser.close()
                except Exception as close_exc:  # noqa: BLE001
                    logger.debug("browser_close_failed error=%s", close_exc)
    # pi-lens-ignore: unreachable-except - sibling exceptions
    except PlaywrightTimeout as exc:
        raise FetchError("read_timeout", f"Visual capture timeout: {exc}") from exc
    except FetchError:
        raise
    except Exception as exc:  # noqa: BLE001
        err = str(exc)
        # NOTE: no boolean operators in this handler (no-boolean-in-except).
        if "Bad file descriptor" in err:
            raise FetchError(
                "internal_error",
                "Screenshot failed (Playwright process error / bad file descriptor). "
                "If this persists, restart the browser worker: "
                "dramatiq app.workers --queues browser_checks --processes 1 --threads 1",
            ) from exc
        if "errno 9" in err.lower():
            raise FetchError(
                "internal_error",
                "Screenshot failed (Playwright process error / bad file descriptor). "
                "If this persists, restart the browser worker: "
                "dramatiq app.workers --queues browser_checks --processes 1 --threads 1",
            ) from exc
        raise FetchError("internal_error", f"Screenshot failed: {exc}") from exc

    ahash = average_hash(png)
    sha = hashlib.sha256(png).hexdigest()

    try:
        phash = perceptual_hash(png)
    except Exception as phash_exc:  # noqa: BLE001 - degrade to the legacy aHash
        logger.warning("phash_failed error=%s", phash_exc)
        phash = ""

    width, height = 0, 0
    try:
        from PIL import Image

        with Image.open(io.BytesIO(png)) as im:
            width, height = im.size
    except Exception as dim_exc:  # noqa: BLE001 - dimensions are metadata
        logger.debug("image_dimensions_unavailable error=%s", dim_exc)

    return VisualCapture(
        png_bytes=png,
        ahash=ahash,
        sha256=sha,
        width=width,
        height=height,
        phash=phash,
    )


def _capture_screenshot_subprocess(
    url: str,
    *,
    timeout_seconds: int = 45,
    full_page: bool = True,
    clip_selector: str | None = None,
) -> VisualCapture:
    """Run capture in a fresh Python process (avoids Dramatiq/Windows FD issues)."""
    # SSRF before spawning
    validate_url_for_fetch(url, resolve_dns=True)

    with tempfile.TemporaryDirectory(prefix="wo-visual-") as tmp:
        out_png = str(Path(tmp) / "shot.png")
        meta_path = str(Path(tmp) / "meta.json")
        cmd = [
            sys.executable,
            "-m",
            "app.services.playwright_job",
            "screenshot",
            "--url",
            url,
            "--out",
            out_png,
            "--meta",
            meta_path,
            "--timeout",
            str(timeout_seconds),
            "--full-page" if full_page else "--no-full-page",
        ]
        if clip_selector:
            cmd.extend(["--clip-selector", clip_selector])

        env = os.environ.copy()
        env["WEB_OBSERVER_PLAYWRIGHT_CHILD"] = "1"
        # Ensure backend package root is on path when workers spawn children
        backend_root = str(Path(__file__).resolve().parents[2])
        prev_pp = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = backend_root if not prev_pp else f"{backend_root}{os.pathsep}{prev_pp}"

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                timeout=max(60, timeout_seconds + 30),
                env=env,
                cwd=backend_root,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise FetchError("read_timeout", "Visual capture subprocess timed out") from exc

        if proc.returncode != 0:
            err_payload: dict = {}
            stderr = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
            stdout = (proc.stdout or b"").decode("utf-8", errors="replace").strip()
            for blob in (stderr, stdout):
                if not blob:
                    continue
                # last line may be JSON error from playwright_job
                for line in reversed(blob.splitlines()):
                    line = line.strip()
                    if line.startswith("{") and "error" in line:
                        try:
                            err_payload = json.loads(line)
                            break
                        except json.JSONDecodeError:
                            continue
                if err_payload:
                    break
            code = err_payload.get("error_code") or "internal_error"
            msg = err_payload.get("error") or stderr or stdout or f"exit {proc.returncode}"
            raise FetchError(str(code), f"Screenshot failed: {msg}")

        if not Path(out_png).is_file() or not Path(meta_path).is_file():
            raise FetchError("internal_error", "Screenshot subprocess produced no output")

        try:
            png = Path(out_png).read_bytes()
            meta = json.loads(Path(meta_path).read_text(encoding="utf-8"))
            width = int(meta.get("width") or 0)
            height = int(meta.get("height") or 0)
        except (OSError, ValueError) as exc:
            # json.JSONDecodeError subclasses ValueError; OSError covers reads.
            raise FetchError(
                "internal_error", f"Invalid screenshot subprocess metadata: {exc}"
            ) from exc
        return VisualCapture(
            png_bytes=png,
            ahash=str(meta.get("ahash") or average_hash(png)),
            sha256=str(meta.get("sha256") or hashlib.sha256(png).hexdigest()),
            width=width,
            height=height,
            phash=str(meta.get("phash") or ""),
        )


def capture_screenshot(
    url: str,
    *,
    timeout_seconds: int = 45,
    full_page: bool = True,
    clip_selector: str | None = None,
) -> VisualCapture:
    """Capture page screenshot via Playwright.

    By default runs in a **subprocess** so Dramatiq worker threads/processes
    never share Playwright's driver pipes (Windows ``EBADF`` / errno 9).

    Set ``WEB_OBSERVER_PLAYWRIGHT_CHILD=1`` (or call from playwright_job) to run
    inline. Set ``WEB_OBSERVER_PLAYWRIGHT_INLINE=1`` to force inline always.
    """
    force_inline = os.environ.get("WEB_OBSERVER_PLAYWRIGHT_INLINE", "").strip() in {
        "1",
        "true",
        "yes",
    }
    is_child = os.environ.get("WEB_OBSERVER_PLAYWRIGHT_CHILD", "").strip() in {
        "1",
        "true",
        "yes",
    }
    if force_inline or is_child:
        return _capture_screenshot_inline(
            url,
            timeout_seconds=timeout_seconds,
            full_page=full_page,
            clip_selector=clip_selector,
        )
    return _capture_screenshot_subprocess(
        url,
        timeout_seconds=timeout_seconds,
        full_page=full_page,
        clip_selector=clip_selector,
    )


def visual_to_fetch_result(capture: VisualCapture, *, url: str) -> FetchResult:
    """Represent visual capture as FetchResult for pipeline (normalized = hashes)."""
    normalized = (
        f"ahash:{capture.ahash}\n"
        f"phash:{capture.phash}\n"
        f"sha256:{capture.sha256}\n"
        f"size:{capture.width}x{capture.height}"
    )
    return FetchResult(
        final_url=url,
        status_code=200,
        content=capture.png_bytes,
        text=normalized,
        content_type="image/png",
        latency_ms=0,
    )


def _parse_hash(text: str, key: str) -> str:
    """Extract a hash value from a normalized visual snapshot blob."""
    for line in (text or "").splitlines():
        if line.startswith(f"{key}:"):
            return line.split(":", 1)[1].strip()
    return ""


def visual_diff_summary(
    prev_text: str,
    new_text: str,
    *,
    threshold: int = 5,
    phash_threshold: int | None = None,
) -> tuple[str, str]:
    """Return (summary, text_diff) for visual hashes stored in normalized_text.

    The pHash (DCT) digest is compared when both snapshots carry one; the
    legacy aHash is only used as a fallback for snapshots taken before pHash
    existed.  ``threshold`` applies to the aHash path, ``phash_threshold`` to
    the pHash path (defaults to the configured value).
    """

    def _parse_ahash(t: str) -> str:
        return _parse_hash(t, "ahash") or (t or "").strip()

    pa, na = _parse_ahash(prev_text), _parse_ahash(new_text)
    pp, np_ = _parse_hash(prev_text, "phash"), _parse_hash(new_text, "phash")

    used = "ahash"
    if pp and np_:
        pa, na = pp, np_
        used = "phash"
        if phash_threshold is None:
            from app.config import get_settings

            # getattr with a default: a worker process still running an older
            # config module must not crash the check.
            phash_threshold = int(getattr(get_settings(), "visual_phash_threshold", 8))
        active_threshold = phash_threshold
    else:
        active_threshold = threshold

    try:
        dist = hamming_distance_hex(pa, na) if pa and na else None
    except ValueError:
        # Corrupt / non-hex digest: never silently call it "unchanged".
        dist = None

    if dist is None:
        summary = f"Visual change detected ({used} unreadable – treated as changed)"
        diff = (
            f"previous {used}: {pa or '(unreadable)'}\n"
            f"new {used}:      {na or '(unreadable)'}\n"
            "distance:       unknown\n"
        )
        return summary, diff

    similar = dist <= active_threshold
    if similar:
        summary = f"Visual similar ({used} distance={dist})"
    else:
        summary = f"Visual change detected ({used} distance={dist}, threshold={active_threshold})"
    diff = (
        f"previous {used}: {pa}\n"
        f"new {used}:      {na}\n"
        f"distance:       {dist}\n"
        f"threshold:      {active_threshold}\n"
    )
    return summary, diff
