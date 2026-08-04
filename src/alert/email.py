"""SMTP email alerts (Gmail, SendGrid SMTP, Amazon SES, etc.)."""

from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def email_configured(smtp_password: str | None = None) -> bool:
    password = (smtp_password or os.getenv("SMTP_PASSWORD") or "").replace(" ", "")
    return bool(
        os.getenv("SMTP_HOST")
        and os.getenv("SMTP_USER")
        and password
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
    password = (os.getenv("SMTP_PASSWORD") or "").replace(" ", "")
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
    except (OSError, smtplib.SMTPException):
        return False


def send_email_with_error(
    subject: str,
    body: str,
    to_addresses: list[str] | None = None,
    html_body: str | None = None,
    smtp_password: str | None = None,
) -> tuple[bool, str]:
    """Like send_email but returns (success, error_message)."""
    host = os.getenv("SMTP_HOST")
    user = os.getenv("SMTP_USER")
    password = (smtp_password or os.getenv("SMTP_PASSWORD") or "").replace(" ", "")
    from_addr = os.getenv("SMTP_FROM") or user
    port = int(os.getenv("SMTP_PORT", "587"))
    use_tls = os.getenv("SMTP_USE_TLS", "true").lower() in ("1", "true", "yes")

    if not all([host, user, password, from_addr]):
        return False, "SMTP not configured (check SMTP_HOST, SMTP_USER, SMTP_PASSWORD)."

    recipients = to_addresses or _default_recipients()
    if not recipients:
        return False, "No recipient — set ALERT_EMAIL or your account alert email."

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
        return True, f"Sent to {', '.join(recipients)}"
    except smtplib.SMTPAuthenticationError as exc:
        return False, (
            f"Gmail auth failed ({exc.smtp_code} {exc.smtp_error!r}). "
            "Use a 16-character App Password from the same account as SMTP_USER "
            "(https://myaccount.google.com/apppasswords)."
        )
    except Exception as exc:
        return False, str(exc)


def send_trial_alert(
    to_address: str | None = None,
    smtp_password: str | None = None,
) -> tuple[bool, str]:
    """Send a sample favorable alert (same content as Alert demo)."""
    from src.ui.demo import get_demo_scenarios, preview_alerts

    scenario = get_demo_scenarios()[0]
    preview = preview_alerts(scenario)
    recipients = [to_address] if to_address else None
    subject = preview["subject"].replace("[Elentrx]", "[Elentrx TEST]")
    body = "This is a test alert from Elentrx — not a live signal.\n\n" + preview["body"]
    html = (
        "<p><b>TEST ALERT</b> — sample only, not a live trading signal.</p>"
        + preview["html"]
    )
    ok, msg = send_email_with_error(
        subject, body, to_addresses=recipients, html_body=html, smtp_password=smtp_password
    )
    if ok:
        return True, msg
    return False, msg


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
