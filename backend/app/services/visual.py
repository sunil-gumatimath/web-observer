"""Screenshot capture helpers and perceptual hashing."""

from __future__ import annotations

import hashlib
import io
import json
import logging
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


def hashes_similar(a: str, b: str, *, max_distance: int = 5) -> bool:
    return hamming_distance_hex(a, b) <= max_distance


@dataclass
class VisualCapture:
    png_bytes: bytes
    ahash: str
    sha256: str
    width: int
    height: int


_LAUNCH_ARGS = [
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
        if "Executable doesn't exist" in msg or "playwright install" in msg.lower():
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
                    viewport={"width": 1280, "height": 720},
                    ignore_https_errors=False,
                )
                page = context.new_page()
                page.goto(validated.url, wait_until="domcontentloaded", timeout=timeout_ms)
                try:
                    page.wait_for_load_state("networkidle", timeout=min(20_000, timeout_ms))
                except PlaywrightTimeout:
                    pass

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
                        logger.warning("full_page_screenshot_failed error=%s; using viewport", shot_exc)
                        png = page.screenshot(type="png", full_page=False)
            finally:
                if context is not None:
                    try:
                        context.close()
                    except Exception:  # noqa: BLE001
                        pass
                try:
                    browser.close()
                except Exception:  # noqa: BLE001
                    pass
    except PlaywrightTimeout as exc:
        raise FetchError("read_timeout", f"Visual capture timeout: {exc}") from exc
    except FetchError:
        raise
    except Exception as exc:  # noqa: BLE001
        err = str(exc)
        if "Bad file descriptor" in err or "errno 9" in err.lower():
            raise FetchError(
                "internal_error",
                "Screenshot failed (Playwright process error / bad file descriptor). "
                "If this persists, restart the browser worker: "
                "dramatiq app.workers --queues browser_checks --processes 1 --threads 1",
            ) from exc
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
        env["PYTHONPATH"] = (
            backend_root if not prev_pp else f"{backend_root}{os.pathsep}{prev_pp}"
        )

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

        png = Path(out_png).read_bytes()
        meta = json.loads(Path(meta_path).read_text(encoding="utf-8"))
        return VisualCapture(
            png_bytes=png,
            ahash=str(meta.get("ahash") or average_hash(png)),
            sha256=str(meta.get("sha256") or hashlib.sha256(png).hexdigest()),
            width=int(meta.get("width") or 0),
            height=int(meta.get("height") or 0),
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
