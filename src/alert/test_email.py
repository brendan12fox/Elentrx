"""Send a trial Elentrx email alert."""

from __future__ import annotations

import argparse

import src.config  # noqa: F401 — loads .env
from src.alert.email import email_configured, send_trial_alert


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a test Elentrx email alert")
    parser.add_argument("--to", default=None, help="Recipient (default: ALERT_EMAIL)")
    parser.add_argument(
        "--app-password",
        default=None,
        help="Gmail App Password (overrides SMTP_PASSWORD; spaces ok)",
    )
    args = parser.parse_args()

    if not email_configured(args.app_password):
        raise SystemExit("SMTP not configured. Set ALERT_EMAIL, SMTP_HOST, SMTP_USER, SMTP_PASSWORD in .env")

    pw = (args.app_password or "").replace(" ", "") or None
    ok, message = send_trial_alert(args.to, smtp_password=pw)
    if ok:
        print(f"Test alert sent: {message}")
    else:
        raise SystemExit(f"Failed: {message}")


if __name__ == "__main__":
    main()
