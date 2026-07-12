"""Send a one-off Resend test email.

Usage (from backend/, with root .env configured):

  set RESEND_API_KEY=re_your_real_key_here
  set EMAIL_FROM=onboarding@resend.dev
  python scripts/send_test_email.py

Or:

  python scripts/send_test_email.py --to you@example.com
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Allow running from backend/ without installing package
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Load root .env if present
root_env = Path(__file__).resolve().parents[2] / ".env"
if root_env.exists():
    for line in root_env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

from app.config import get_settings  # noqa: E402
from app.services.email import send_email  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--to", default="clevertedz@gmail.com", help="Recipient email")
    parser.add_argument(
        "--from-addr",
        default=None,
        help="From address (default: EMAIL_FROM env or onboarding@resend.dev)",
    )
    args = parser.parse_args()

    settings = get_settings()
    if args.from_addr:
        # temporary override for this process
        object.__setattr__(settings, "email_from", args.from_addr)  # may fail if frozen
        os.environ["EMAIL_FROM"] = args.from_addr
        get_settings.cache_clear()

    if not get_settings().resend_api_key:
        print("ERROR: RESEND_API_KEY is not set.")
        print("Put your real key in the project root .env:")
        print("  RESEND_API_KEY=re_xxxxxxxx")
        print("  EMAIL_FROM=onboarding@resend.dev")
        sys.exit(1)

    msg_id = send_email(
        to=args.to,
        subject="Hello from Web Observer",
        text="Congrats on sending your first email with Resend + Web Observer.",
        html_body=(
            "<p>Congrats on sending your <strong>first email</strong> "
            "from <em>Web Observer</em> via Resend.</p>"
        ),
    )
    print(f"Sent OK. provider_id={msg_id}")


if __name__ == "__main__":
    main()
