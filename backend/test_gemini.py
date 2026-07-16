"""Standalone Gemini connectivity + key test.

Run this from a NORMAL PowerShell window (not through any sandbox) so it uses
your machine's real network + TLS stack:

    cd backend
    .\.venv\Scripts\python.exe test_gemini.py

It checks, in order:
  1. Basic HTTPS reachability (can we do TLS to Google at all?)
  2. Reachability to the Gemini host
  3. A real chat/completions call with your configured key + model

Each step prints PASS/FAIL with the exact error, so you can tell whether the
problem is TLS/network (steps 1-2) or the key/model (step 3).

Reads LLM_API_KEY / LLM_API_BASE / LLM_MODEL from backend/.env.
"""

from __future__ import annotations

import sys

try:
    import httpx
except ImportError:
    sys.exit("httpx not installed in this venv — run from backend/.venv")

try:
    from dotenv import load_dotenv
except ImportError:
    sys.exit("python-dotenv not installed in this venv — run from backend/.venv")

import os

load_dotenv(".env", override=True)

KEY = os.getenv("LLM_API_KEY") or ""
BASE = (os.getenv("LLM_API_BASE") or "https://generativelanguage.googleapis.com/v1beta/openai").rstrip("/")
MODEL = os.getenv("LLM_MODEL") or "gemini-2.0-flash"

# Try to prefer the certifi CA bundle if present (helps on some Windows setups).
VERIFY: object = True
try:
    import certifi

    VERIFY = certifi.where()
except ImportError:
    pass


def _line() -> None:
    print("-" * 60)


def hr(title: str) -> None:
    _line()
    print(title)
    _line()


def step1_basic_https() -> bool:
    hr("STEP 1  Basic HTTPS reachability (https://www.google.com)")
    for label, verify in (("verify=certifi/default", VERIFY), ("verify=False (INSECURE)", False)):
        try:
            r = httpx.get("https://www.google.com", timeout=15, verify=verify)  # type: ignore[arg-type]
            print(f"  PASS [{label}] HTTP {r.status_code}")
            if verify is not False:
                return True
            print("  ^ Only works with verification OFF => a TLS interceptor "
                  "(AV/VPN/proxy) is replacing certs. Fix that, then re-run.")
            return False
        except Exception as exc:  # noqa: BLE001
            print(f"  FAIL [{label}] {type(exc).__name__}: {str(exc)[:160]}")
    return False


def step2_host() -> bool:
    hr(f"STEP 2  Reach Gemini host ({BASE})")
    try:
        r = httpx.get(BASE + "/models", timeout=20, verify=VERIFY,  # type: ignore[arg-type]
                      headers={"Authorization": f"Bearer {KEY}"} if KEY else {})
        print(f"  PASS  HTTP {r.status_code}")
        print("  body:", r.text[:300])
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"  FAIL  {type(exc).__name__}: {str(exc)[:200]}")
        return False


def step3_chat() -> bool:
    hr(f"STEP 3  Real chat call (model={MODEL})")
    if not KEY:
        print("  SKIP  LLM_API_KEY is empty in backend/.env")
        return False
    print(f"  key prefix: {KEY[:6]}...  (standard Gemini keys start with 'AIza')")
    try:
        r = httpx.post(
            BASE + "/chat/completions",
            headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
            json={
                "model": MODEL,
                "max_tokens": 20,
                "messages": [{"role": "user", "content": "Reply with the single word: OK"}],
            },
            timeout=30,
            verify=VERIFY,  # type: ignore[arg-type]
        )
    except Exception as exc:  # noqa: BLE001
        print(f"  FAIL  transport error: {type(exc).__name__}: {str(exc)[:200]}")
        return False

    print(f"  HTTP {r.status_code}")
    if r.status_code == 200:
        try:
            content = r.json()["choices"][0]["message"]["content"]
            print(f"  PASS  model replied: {content!r}")
            return True
        except Exception:  # noqa: BLE001
            print("  WARN  200 but unexpected body:", r.text[:300])
            return False
    print("  FAIL  body:", r.text[:400])
    if r.status_code in (401, 403):
        print("  => Auth rejected: the API key is invalid/expired or lacks access.")
    elif r.status_code == 404:
        print(f"  => Model '{MODEL}' not found for this key. Try gemini-2.5-flash or gemini-1.5-flash.")
    return False


def main() -> None:
    print(f"config: base={BASE}  model={MODEL}  key_set={bool(KEY)}  verify={VERIFY!r}")
    s1 = step1_basic_https()
    s2 = step2_host()
    s3 = step3_chat()
    hr("RESULT")
    print(f"  1. basic HTTPS : {'PASS' if s1 else 'FAIL'}")
    print(f"  2. gemini host : {'PASS' if s2 else 'FAIL'}")
    print(f"  3. chat + key  : {'PASS' if s3 else 'FAIL'}")
    if s3:
        print("\n  All good. Restart the API + workers and Gemini summaries/triage will work.")
    elif not s1:
        print("\n  TLS/network is broken on this machine (not the app, not the key).")
        print("  Disable AV HTTPS-scanning / VPN / proxy, then re-run. See step 1 detail above.")
    elif not s3:
        print("\n  Network is fine but the key/model failed — see STEP 3 detail above.")


if __name__ == "__main__":
    main()
