"""Isolated Playwright CLI jobs.

Run as a fresh process so Dramatiq/Windows cannot share broken pipes with
the Playwright driver (common cause of ``[Errno 9] Bad file descriptor``).
"""

from __future__ import annotations

import argparse
import json
import os
import sys


def _cmd_screenshot(args: argparse.Namespace) -> int:
    # Mark child so visual.capture_screenshot runs inline (no nested subprocess).
    os.environ["WEB_OBSERVER_PLAYWRIGHT_CHILD"] = "1"
    from app.services.visual import capture_screenshot

    try:
        capture = capture_screenshot(
            args.url,
            timeout_seconds=args.timeout,
            full_page=args.full_page,
            clip_selector=args.clip_selector or None,
        )
    except Exception as exc:  # noqa: BLE001
        # FetchError and others: surface message for parent parsing
        from app.services.fetcher import FetchError

        if isinstance(exc, FetchError):
            payload = {"ok": False, "error_code": exc.code, "error": str(exc)}
        else:
            payload = {"ok": False, "error_code": "internal_error", "error": str(exc)}
        sys.stderr.write(json.dumps(payload) + "\n")
        return 1

    with open(args.out, "wb") as f:
        f.write(capture.png_bytes)
    meta = {
        "ok": True,
        "ahash": capture.ahash,
        "sha256": capture.sha256,
        "width": capture.width,
        "height": capture.height,
        "png_path": args.out,
    }
    with open(args.meta, "w", encoding="utf-8") as f:
        json.dump(meta, f)
    return 0


def _cmd_fetch(args: argparse.Namespace) -> int:
    os.environ["WEB_OBSERVER_PLAYWRIGHT_CHILD"] = "1"
    from app.services.browser_fetch import fetch_url_browser
    from app.services.fetcher import FetchError

    try:
        result = fetch_url_browser(
            args.url,
            timeout_seconds=args.timeout,
            max_response_bytes=args.max_bytes,
            wait_selector=args.wait_selector or None,
        )
    except Exception as exc:  # noqa: BLE001
        if isinstance(exc, FetchError):
            payload = {"ok": False, "error_code": exc.code, "error": str(exc)}
        else:
            payload = {"ok": False, "error_code": "internal_error", "error": str(exc)}
        sys.stderr.write(json.dumps(payload) + "\n")
        return 1

    with open(args.out, "wb") as f:
        f.write(result.content)
    meta = {
        "ok": True,
        "final_url": result.final_url,
        "status_code": result.status_code,
        "content_type": result.content_type,
        "latency_ms": result.latency_ms,
        "text_encoding": "utf-8",
    }
    with open(args.meta, "w", encoding="utf-8") as f:
        json.dump(meta, f)
    # HTML text is in content bytes; parent re-decodes
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="playwright_job")
    sub = parser.add_subparsers(dest="command", required=True)

    shot = sub.add_parser("screenshot", help="Capture a page screenshot")
    shot.add_argument("--url", required=True)
    shot.add_argument("--out", required=True, help="PNG output path")
    shot.add_argument("--meta", required=True, help="JSON metadata path")
    shot.add_argument("--timeout", type=int, default=45)
    shot.add_argument("--full-page", action=argparse.BooleanOptionalAction, default=True)
    shot.add_argument("--clip-selector", default="")
    shot.set_defaults(func=_cmd_screenshot)

    fetch = sub.add_parser("fetch", help="JS-rendered page fetch")
    fetch.add_argument("--url", required=True)
    fetch.add_argument("--out", required=True, help="Body output path")
    fetch.add_argument("--meta", required=True, help="JSON metadata path")
    fetch.add_argument("--timeout", type=int, default=45)
    fetch.add_argument("--max-bytes", type=int, default=5_000_000)
    fetch.add_argument("--wait-selector", default="")
    fetch.set_defaults(func=_cmd_fetch)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
