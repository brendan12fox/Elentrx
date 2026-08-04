"""SMTP email alerts (Gmail, SendGrid SMTP, Amazon SES, etc.)."""

from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def email_configured() -> bool:
    return bool(
        os.getenv("SMTP_HOST")
        and os.getenv("SMTP_USER")
        and os.getenv("SMTP_PASSWORD")
        and (os.getenv("ALERT_EMAIL") or os.getenv("SMTP_FROM"))
    )


def _default_recipients() -> list[str]:
    from src.auth.users import list_alert_recipients

    return list_alert_recipients()


def send_email(
    subject: str,
    body: str,
    to_addresses: list[str] | None = None,
    html_body: str | None = None,
) -> bool:
    host = os.getenv("SMTP_HOST")
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    from_addr = os.getenv("SMTP_FROM") or user
    port = int(os.getenv("SMTP_PORT", "587"))
    use_tls = os.getenv("SMTP_USE_TLS", "true").lower() in ("1", "true", "yes")

    if not all([host, user, password, from_addr]):
        return False

    recipients = to_addresses or _default_recipients()
    if not recipients:
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(body, "plain", "utf-8"))
    if html_body:
        msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(host, port, timeout=30) as server:
            if use_tls:
                server.starttls()
            server.login(user, password)
            server.sendmail(from_addr, recipients, msg.as_string())
        return True
    except OSError:
        return False


def build_alert_email(
    ticker: str,
    nct_id: str,
    old_phase: str | None,
    new_phase: str | None,
    probability: float,
    summary: str,
) -> tuple[str, str, str]:
    phase_text = f"{old_phase or 'NA'} → {new_phase or 'NA'}"
    subject = f"[Elentrx] {ticker} trial update — score {probability:.0%}"
    thesis = (summary or "No summary available.").strip()
    body = (
        f"Elentrx trial alert\n\n"
        f"Ticker: {ticker}\n"
        f"NCT ID: {nct_id}\n"
        f"Phase: {phase_text}\n"
        f"Favorability score: {probability:.2f}\n\n"
        f"Summary:\n{thesis}\n\n"
        f"---\n"
        f"Not financial advice. See dashboard for full brief.\n"
    )
    html = (
        f"<h2>Elentrx trial alert</h2>"
        f"<p><b>{ticker}</b> · {nct_id}<br>"
        f"Phase: {phase_text}<br>"
        f"Score: {probability:.2f}</p>"
        f"<p>{thesis}</p>"
        f"<p><small>Not financial advice.</small></p>"
    )
    return subject, body, html
