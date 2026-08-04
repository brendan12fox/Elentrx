"""Dispatch favorability alerts via email."""

from __future__ import annotations

from datetime import datetime, timezone

from src.alert.email import build_alert_email, email_configured, send_email
from src.db.schema import get_connection


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

    subject, body, html = build_alert_email(
        ticker, nct_id, old_phase, new_phase, probability, summary
    )
    sent = send_email(subject, body, html_body=html) if email_configured() else False
    log_message = f"{subject}\n\n{body}" if sent else f"[DRY RUN — email]\n{subject}\n\n{body}"

    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM alerts WHERE dedupe_key = ?",
            (dedupe_key,),
        ).fetchone()
        if existing:
            return False

        conn.execute(
            """
            INSERT INTO alerts (
                phase_change_id, ticker, nct_id, message, sent_at, dedupe_key
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (phase_change_id, ticker, nct_id, log_message, now, dedupe_key),
        )
        return sent
