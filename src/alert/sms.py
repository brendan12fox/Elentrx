"""Twilio SMS alerting."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from src.db.schema import get_connection


def _build_message(
    ticker: str,
    nct_id: str,
    old_phase: str | None,
    new_phase: str | None,
    probability: float,
    summary: str,
) -> str:
    phase_text = f"{old_phase or 'NA'}->{new_phase or 'NA'}"
    thesis = (summary or "No summary").strip()
    if len(thesis) > 140:
        thesis = thesis[:137] + "..."
    return (
        f"[Elentrx] {ticker} {nct_id} {phase_text} "
        f"score={probability:.2f} | {thesis} "
        f"| Not financial advice."
    )


def send_sms(message: str, to_number: str | None = None) -> bool:
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_FROM_NUMBER")
    recipient = to_number or os.getenv("ALERT_PHONE")

    if not all([account_sid, auth_token, from_number, recipient]):
        return False

    from twilio.rest import Client

    client = Client(account_sid, auth_token)
    client.messages.create(body=message, from_=from_number, to=recipient)
    return True


def alert_if_new(
    phase_change_id: int,
    ticker: str,
    nct_id: str,
    old_phase: str | None,
    new_phase: str | None,
    probability: float,
    summary: str,
) -> bool:
    dedupe_key = f"{nct_id}:{old_phase}:{new_phase}"
    now = datetime.now(timezone.utc).isoformat()
    message = _build_message(ticker, nct_id, old_phase, new_phase, probability, summary)

    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM alerts WHERE dedupe_key = ?",
            (dedupe_key,),
        ).fetchone()
        if existing:
            return False

        sent = send_sms(message)
        if not sent:
            # Still log alert intent for dashboard when Twilio is not configured
            message = f"[DRY RUN] {message}"

        conn.execute(
            """
            INSERT INTO alerts (
                phase_change_id, ticker, nct_id, message, sent_at, dedupe_key
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (phase_change_id, ticker, nct_id, message, now, dedupe_key),
        )
        return sent
