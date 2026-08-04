"""SMTP/API email alerts (Gmail, SendGrid, Resend, etc.)."""

from __future__ import annotations

import json
import os
import re
import smtplib
import ssl
import urllib.error
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def normalize_app_password(password: str | None) -> str:
    """Strip spaces/quotes/newlines from a password field."""
    if not password:
        return ""
    cleaned = password.strip().strip('"').strip("'")
    cleaned = re.sub(r"\s+", "", cleaned)
    return cleaned


def _is_gmail_host(host: str | None) -> bool:
    return bool(host and "gmail" in host.lower())


def resend_configured() -> bool:
    return bool(os.getenv("RESEND_API_KEY") and (os.getenv("ALERT_EMAIL") or os.getenv("SMTP_FROM")))


def _resend_from_address() -> str:
    explicit = os.getenv("RESEND_FROM") or os.getenv("SMTP_FROM")
    if explicit:
        return explicit
    alert = os.getenv("ALERT_EMAIL", "alerts@example.com")
    return f"Elentrx <{alert}>"


def _send_via_resend(
    subject: str,
    body: str,
    recipients: list[str],
    html_body: str | None = None,
) -> tuple[bool, str]:
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    if not api_key:
        return False, "RESEND_API_KEY is not set."

    payload = {
        "from": _resend_from_address(),
        "to": recipients,
        "subject": subject,
        "text": body,
    }
    if html_body:
        payload["html"] = html_body

    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Elentrx/1.0 (clinical-trial-alerts)",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
        return True, f"Sent to {', '.join(recipients)} via Resend"
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return False, f"Resend error ({exc.code}): {detail}"
    except Exception as exc:
        return False, f"Resend error: {exc}"


def _smtp_login(host: str, port: int, user: str, password: str, use_tls: bool) -> None:
    if port == 465:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, context=context, timeout=30) as server:
            server.login(user, password)
        return
    with smtplib.SMTP(host, port, timeout=30) as server:
        if use_tls:
            server.starttls()
        server.login(user, password)


def verify_smtp_login(smtp_password: str | None = None) -> tuple[bool, str]:
    """Test SMTP credentials without sending mail."""
    if resend_configured():
        return True, "Resend API key configured — SMTP login not required."

    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    user = (os.getenv("SMTP_USER") or "").strip()
    password = normalize_app_password(smtp_password or os.getenv("SMTP_PASSWORD"))

    if not user:
        return False, "SMTP_USER is not set."
    if not password:
        return False, "No SMTP password set."

    if _is_gmail_host(host) and ("@" in password or len(password) != 16):
        return False, (
            f"Gmail app password should be exactly 16 letters (got {len(password)}). "
            "Not your login password — create one at https://myaccount.google.com/apppasswords"
        )

    port = int(os.getenv("SMTP_PORT", "587"))
    use_tls = os.getenv("SMTP_USE_TLS", "true").lower() in ("1", "true", "yes")
    errors: list[str] = []

    for try_port, try_tls in ((port, use_tls), (465, False)):
        try:
            _smtp_login(host, try_port, user, password, try_tls)
            return True, f"Login OK for {user} on port {try_port}."
        except smtplib.SMTPAuthenticationError as exc:
            errors.append(f"port {try_port}: {exc.smtp_code}")
        except Exception as exc:
            errors.append(f"port {try_port}: {exc}")

    return False, (
        f"Gmail rejected login for {user} ({', '.join(errors)}). "
        "Fix: incognito → sign in as eletrx.trials@gmail.com → enable 2FA → "
        "new App Password at https://myaccount.google.com/apppasswords\n\n"
        "Or skip Gmail: sign up at https://resend.com (free), add RESEND_API_KEY to .env "
        "and RESEND_FROM=Elentrx <onboarding@resend.dev> for testing."
    )


def email_configured(smtp_password: str | None = None) -> bool:
    if resend_configured():
        return True
    password = normalize_app_password(smtp_password or os.getenv("SMTP_PASSWORD"))
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
    password = normalize_app_password(os.getenv("SMTP_PASSWORD"))
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
    recipients = to_addresses or _default_recipients()
    if not recipients:
        return False, "No recipient — set ALERT_EMAIL or your account alert email."

    if resend_configured() and not smtp_password:
        return _send_via_resend(subject, body, recipients, html_body)

    host = os.getenv("SMTP_HOST")
    user = os.getenv("SMTP_USER")
    password = normalize_app_password(smtp_password or os.getenv("SMTP_PASSWORD"))
    from_addr = os.getenv("SMTP_FROM") or user
    port = int(os.getenv("SMTP_PORT", "587"))
    use_tls = os.getenv("SMTP_USE_TLS", "true").lower() in ("1", "true", "yes")

    if not all([host, user, password, from_addr]):
        if resend_configured():
            return _send_via_resend(subject, body, recipients, html_body)
        return False, "SMTP not configured (check SMTP_HOST, SMTP_USER, SMTP_PASSWORD)."

    if _is_gmail_host(host or "") and "@" in password:
        return False, "That looks like your login password. Use a 16-character Gmail App Password instead."

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(body, "plain", "utf-8"))
    if html_body:
        msg.attach(MIMEText(html_body, "html", "utf-8"))

    envelope_from = user
    match = re.search(r"<([^>]+)>", from_addr)
    if match:
        envelope_from = match.group(1)

    try:
        if port == 465:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, context=context, timeout=30) as server:
                server.login(user, password)
                server.sendmail(envelope_from, recipients, msg.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=30) as server:
                if use_tls:
                    server.starttls()
                server.login(user, password)
                server.sendmail(envelope_from, recipients, msg.as_string())
        return True, f"Sent to {', '.join(recipients)}"
    except smtplib.SMTPAuthenticationError:
        ok, detail = verify_smtp_login(smtp_password)
        if ok:
            return False, "Login succeeded but send failed — check SMTP_FROM matches SMTP_USER."
        return False, detail
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
