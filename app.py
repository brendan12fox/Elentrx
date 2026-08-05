"""Streamlit dashboard for healthcare trial scraper."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import streamlit as st

from src.alert.email import email_configured, resend_configured, send_trial_alert
from src.ui.auth_page import render_auth_page
from src.auth.users import (
    authenticate,
    ensure_bootstrap_admin,
    get_user,
    update_alert_email,
    update_password,
)
from src.config import DATA_DIR, FAVORABILITY_THRESHOLD, get_sector_for_hour, hydrate_streamlit_secrets, load_sectors
from src.db.schema import init_db
from src.db.seed import seed_if_empty
from src.ml.historical import HISTORICAL_DATASET_PATH, load_dataset
from src.ml.progress import load_progress
from src.pipeline.run_hourly import run_hourly
from src.research.watchlist import (
    build_daily_digest,
    cache_is_fresh,
    load_digest_for_display,
)
from src.ui.trial_data import (
    enrich_trials_with_news,
    fetch_alerts,
    fetch_runs,
    fetch_sector_activity,
    fetch_trials_for_sector,
    get_favorable_picks,
    load_evaluation_report,
    load_historical_samples,
)
from src.ui.styles import (
    inject_styles,
    render_alert_timeline,
    render_empty_sector,
    render_history_browse,
    render_history_picks_gallery,
    render_history_scoreboard,
    render_home_hero,
    render_metric_grid,
    render_page_header,
    render_run_cards,
    render_rotation_schedule,
    render_section_label,
    render_sector_grid,
    render_sector_header,
    render_settings_rows,
    render_sidebar_brand,
    render_trial_cards_grid,
)
from src.market.quotes import fetch_quotes

st.set_page_config(
    page_title="Elentrx™ — Clinical Trial Alerter",
    page_icon="assets/elentrx-ui.png",
    layout="wide",
    initial_sidebar_state="expanded",
)

LEGAL_FILES = {
    "Disclaimer": DATA_DIR.parent / "DISCLAIMER.md",
    "Terms of Use": DATA_DIR.parent / "TERMS_OF_USE.md",
    "Privacy Policy": DATA_DIR.parent / "PRIVACY_POLICY.md",
    "Trademarks": DATA_DIR.parent / "TRADEMARKS.md",
}

_NAV_LABELS = {
    "Home": "Home",
    "History": "History",
    "Alerts": "Alerts",
    "Account": "Account",
}
NAV_PAGES = list(_NAV_LABELS.keys())


def _ensure_app_ready() -> None:
    if st.session_state.get("_app_ready"):
        return
    init_db()
    ensure_bootstrap_admin()
    seed_if_empty()
    hydrate_streamlit_secrets()
    st.session_state._app_ready = True


def _auth_disabled() -> bool:
    return os.getenv("AUTH_DISABLED", "").lower() in ("1", "true", "yes")


def _require_login() -> None:
    if _auth_disabled():
        if "user" not in st.session_state:
            st.session_state.user = {"username": "dev", "id": 0, "is_admin": True}
        return

    if st.session_state.get("authenticated") and st.session_state.get("user_id"):
        return

    render_auth_page()
    st.stop()


@st.cache_data(show_spinner=False, ttl=120)
def _cached_quotes(tickers: tuple[str, ...]) -> dict[str, object]:
    return fetch_quotes(list(tickers))


def _quotes_for(items: list[dict], key: str = "ticker") -> dict:
    tickers = tuple(sorted({(i.get(key) or "").upper() for i in items if i.get(key)}))
    if not tickers:
        return {}
    return _cached_quotes(tickers)


@st.cache_data(show_spinner=False, ttl=300)
def _cached_digest() -> tuple[dict | None, bool]:
    digest = load_digest_for_display()
    stale = bool(digest and not cache_is_fresh(digest))
    return digest, stale


@st.cache_data(show_spinner=False, ttl=60)
def _cached_sector_activity() -> list[dict]:
    return fetch_sector_activity()


@st.cache_data(show_spinner=False, ttl=300)
def _cached_sector_trials(sector_id: str) -> list[dict]:
    return fetch_trials_for_sector(sector_id, limit=80, active_first=True)


@st.cache_data(show_spinner=False, ttl=60)
def _cached_alerts() -> list[dict]:
    return fetch_alerts(limit=30)


@st.cache_data(show_spinner=False, ttl=60)
def _cached_runs() -> list[dict]:
    return fetch_runs(limit=15)


@st.cache_data(show_spinner=False, ttl=300)
def _cached_historical_samples() -> list[dict]:
    return load_historical_samples()


def _clear_data_caches() -> None:
    """Force Streamlit panels to re-read DB / digest after a manual scan."""
    for fn in (
        _cached_digest,
        _cached_sector_activity,
        _cached_sector_trials,
        _cached_alerts,
        _cached_runs,
        _cached_historical_samples,
        _cached_quotes,
    ):
        try:
            fn.clear()
        except Exception:
            pass


def render_manual_refresh(*, key_prefix: str = "manual") -> None:
    """Manual sector scan + view reload controls."""
    sectors = load_sectors()
    focus, _ = get_sector_for_hour()
    names = [s["name"] for s in sectors]
    try:
        default_idx = names.index(focus["name"])
    except ValueError:
        default_idx = 0

    result_key = f"{key_prefix}_last_result"
    if result_key in st.session_state:
        result = st.session_state.pop(result_key)
        if result.get("ok"):
            st.success(result["message"])
        else:
            st.error(result["message"])

    st.markdown(
        '<div style="background:#f5f8fa;border:1px solid #dce4ec;border-radius:14px;'
        'padding:1rem 1.15rem;margin-bottom:1rem;">'
        '<div style="font-weight:700;color:#001d3d;margin-bottom:0.25rem;">Manual sector refresh</div>'
        '<div style="font-size:0.82rem;color:#4a6278;">Scan ClinicalTrials.gov for a sector now, '
        "or reload the page data without scraping.</div></div>",
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns([2.2, 1.2])
    with c1:
        selected_name = st.selectbox(
            "Sector to scan",
            names,
            index=default_idx,
            key=f"{key_prefix}_sector",
            help=f"Current hourly rotation focus: {focus['name']}",
        )
    with c2:
        send_alerts = st.checkbox(
            "Send alerts",
            value=False,
            key=f"{key_prefix}_alerts",
            help="If checked, favorable hits can email. Off by default for manual scans.",
        )

    b1, b2 = st.columns(2)
    with b1:
        scan = st.button(
            "Scan sector now",
            type="primary",
            use_container_width=True,
            key=f"{key_prefix}_scan",
        )
    with b2:
        reload_view = st.button(
            "Reload view",
            use_container_width=True,
            key=f"{key_prefix}_reload",
        )

    if reload_view:
        _clear_data_caches()
        st.session_state[result_key] = {
            "ok": True,
            "message": "View reloaded from the latest saved data.",
        }
        st.rerun()

    if scan:
        sector = next(s for s in sectors if s["name"] == selected_name)
        with st.spinner(f"Scanning {sector['name']} on ClinicalTrials.gov… this can take a minute"):
            try:
                stats = run_hourly(sector_id=sector["id"], dry_run=not send_alerts)
            except Exception as exc:
                st.session_state[result_key] = {"ok": False, "message": f"Scan failed: {exc}"}
                st.rerun()
                return
        _clear_data_caches()
        if stats.get("status") == "error":
            st.session_state[result_key] = {
                "ok": False,
                "message": f"Scan error: {stats.get('error') or 'unknown error'}",
            }
        else:
            st.session_state[result_key] = {
                "ok": True,
                "message": (
                    f"{stats['sector_name']}: {stats['trials_fetched']} trials fetched · "
                    f"{stats['changes_detected']} changes · {stats['alerts_sent']} alerts"
                ),
            }
        st.rerun()


def sector_detail_panel(sector_id: str) -> None:
    sectors = load_sectors()
    sector = next((s for s in sectors if s["id"] == sector_id), None)
    if not sector:
        st.session_state.pop("selected_sector", None)
        st.rerun()
        return

    activity = next((a for a in _cached_sector_activity() if a["id"] == sector_id), {})

    if st.button("← Back to sectors", key="back_to_home"):
        st.session_state.pop("selected_sector", None)
        st.rerun()

    render_sector_header(sector, activity)

    raw_digest, _ = _cached_digest()
    trials = enrich_trials_with_news(
        _cached_sector_trials(sector_id),
        raw_digest,
        max_fetch=8,
    )

    if not trials:
        render_empty_sector(
            "No trials in this sector yet. The hourly scraper rotates through all areas — "
            "check back after the next scan, or trigger a manual refresh from Account."
        )
        return

    ticker_filter = st.text_input(
        "Filter by ticker or company",
        placeholder="e.g. LLY or Lilly",
        key=f"sector_filter_{sector_id}",
    )
    if ticker_filter.strip():
        q = ticker_filter.strip().lower()
        trials = [
            t
            for t in trials
            if q in t["ticker"].lower()
            or q in t["sponsor"].lower()
            or q in (t.get("drug") or "").lower()
        ]

    render_section_label(f"{len(trials)} active trials")
    render_trial_cards_grid(trials, quotes=_quotes_for(trials))


def home_panel() -> None:
    selected = st.session_state.get("selected_sector")
    if selected:
        sector_detail_panel(selected)
        return

    focus, _ = get_sector_for_hour()
    activity = _cached_sector_activity()
    render_home_hero(focus["name"])
    render_section_label("Sectors — activity at a glance")
    render_sector_grid(activity, key_prefix="home_sector")


def history_panel() -> None:
    report = load_evaluation_report()
    samples = _cached_historical_samples()

    render_history_scoreboard(report)

    if report:
        methodology = report.get("methodology", {})
        ds = report.get("dataset", {})
        st.caption(
            f"Labels use {methodology.get('label', '5-day forward return ≥ 2%')}. "
            f"{ds.get('total_samples', len(samples))} historical events · "
            f"news cut off at each event date."
        )

    picks = get_favorable_picks(samples, limit=12)
    render_history_picks_gallery(picks)

    ticker_filter = st.text_input(
        "Browse events",
        placeholder="Filter by ticker, sponsor, or drug",
        key="history_ticker_filter",
    )
    render_history_browse(samples, ticker_filter=ticker_filter)


def _default_alert_recipient() -> str:
    user = get_user(st.session_state.get("user_id", 0))
    return (user.alert_email if user else None) or os.getenv("ALERT_EMAIL", "")


def render_send_test_alert() -> None:
    """Send a sample trial alert email."""
    recipient_default = _default_alert_recipient()
    using_resend = resend_configured()
    ready = email_configured()

    status_class = "ok" if ready else "warn"
    status_label = "Ready to send" if ready else "Not configured"
    provider = "Resend" if using_resend else "SMTP"

    status_pill_style = (
        "display:inline-block;padding:0.3rem 0.7rem;border-radius:999px;font-size:0.72rem;"
        "font-weight:700;letter-spacing:0.02em;border:1px solid;"
    )
    status_pill_style += (
        "background:#ecfdf5;color:#047857;border-color:#6ee7b7;"
        if ready
        else "background:#fef2f2;color:#b91c1c;border-color:#fecaca;"
    )

    st.markdown(
        f"""
<div class="alert-send-card" style="background:linear-gradient(135deg,#ffffff 0%,#f0fdfb 100%);border:1px solid #b8ebe3;border-radius:16px;padding:1.25rem 1.5rem;margin-bottom:1.25rem;">
  <div style="display:flex;justify-content:space-between;align-items:center;gap:1rem;flex-wrap:wrap;">
    <div>
      <h4 style="margin:0 0 0.25rem 0;font-size:1.05rem;font-weight:700;color:#001d3d;">Send a test alert</h4>
      <p style="margin:0;color:#64748b;font-size:0.85rem;">Deliver via {provider} · threshold {FAVORABILITY_THRESHOLD:.0%}</p>
    </div>
    <span class="status-pill {status_class}" style="{status_pill_style}">{status_label}</span>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    with st.form("send_test_alert", clear_on_submit=False):
        recipient = st.text_input("Send to", value=recipient_default)
        submitted = st.form_submit_button("Send test alert", type="primary", use_container_width=True)

    if submitted:
        if not email_configured():
            st.error("Email not configured — add RESEND_API_KEY to secrets.")
        elif not recipient.strip():
            st.error("Enter a recipient email.")
        else:
            with st.spinner("Sending…"):
                ok, msg = send_trial_alert(recipient.strip())
            if ok:
                st.success(msg)
            else:
                st.error(msg)


def alerts_panel() -> None:
    render_send_test_alert()
    alerts = _cached_alerts()
    if not alerts:
        st.info("No emails sent yet — favorable trial changes above your threshold will appear here.")
        return
    st.markdown(f"**{len(alerts)} emails sent**")
    render_alert_timeline(alerts)


def account_panel() -> None:
    user = get_user(st.session_state.user_id)
    if not user:
        st.error("Session expired. Please sign in again.")
        return

    render_settings_rows([
        ("Username", user.username),
        ("Role", "Administrator" if user.is_admin else "User"),
        ("Alert email", user.alert_email or "Not set"),
    ])

    with st.form("alert_email_form"):
        alert_email = st.text_input("Alert email", value=user.alert_email or "")
        if st.form_submit_button("Save alert email"):
            update_alert_email(user.id, alert_email)
            st.success("Alert email updated.")

    with st.form("password_form"):
        st.markdown("**Change password**")
        current = st.text_input("Current password", type="password")
        new_pw = st.text_input("New password", type="password")
        confirm = st.text_input("Confirm new password", type="password")
        if st.form_submit_button("Update password"):
            if not authenticate(user.username, current):
                st.error("Current password is incorrect.")
            elif len(new_pw) < 8:
                st.error("New password must be at least 8 characters.")
            elif new_pw != confirm:
                st.error("New passwords do not match.")
            else:
                update_password(user.id, new_pw)
                st.success("Password updated.")

    if st.button("Sign out"):
        _clear_data_caches()
        for key in ("authenticated", "user_id", "username", "selected_sector"):
            st.session_state.pop(key, None)
        st.rerun()


def config_panel() -> None:
    render_settings_rows([
        ("Notifications", "Email via Resend" if resend_configured() else "Email via SMTP"),
        ("Alert email", os.getenv("ALERT_EMAIL", "") or "Not set"),
        ("Delivery", "Configured" if email_configured() else "Not configured"),
        ("OpenAI", "Configured" if os.getenv("OPENAI_API_KEY") else "Missing"),
        ("Score threshold", f"{FAVORABILITY_THRESHOLD:.0%}"),
    ])
    st.caption("When a trial change scores above the threshold, Elentrx sends one email alert.")


def legal_panel() -> None:
    st.subheader("Legal")
    st.warning(
        "**Not financial, medical, or investment advice.** Elentrx is a research and "
        "notification tool. You are solely responsible for investment decisions. "
        "ML scores and AI summaries may be incorrect."
    )
    doc = st.selectbox("Document", list(LEGAL_FILES.keys()))
    path = LEGAL_FILES[doc]
    if path.exists():
        st.markdown(path.read_text(encoding="utf-8"))
    else:
        st.error(f"Missing file: {path.name}")
    st.caption("Elentrx™ is a trademark of Brendan Fox. See TRADEMARKS.md for third-party marks.")


def admin_panel() -> None:
    user = get_user(st.session_state.get("user_id", 0))
    if not user or not user.is_admin:
        st.caption("Admin tools are available to administrators only.")
        return

    if st.button("Rebuild full digest", type="secondary"):
        build_daily_digest(force=True)
        _clear_data_caches()
        st.rerun()

    with st.expander("Manual sector refresh", expanded=False):
        render_manual_refresh(key_prefix="account")

    sectors = load_sectors()
    now = datetime.now(timezone.utc)
    current, index = get_sector_for_hour(now.hour)

    st.markdown("**Hourly rotation**")
    render_metric_grid([
        ("Focus now", current["name"]),
        ("Rotation slot", f"{index + 1} of {len(sectors)}"),
        ("Full cycle", f"Every {len(sectors)} hours"),
    ])
    render_rotation_schedule(sectors, index, now.hour)

    runs = _cached_runs()
    if runs:
        st.markdown("**Recent scraper runs**")
        render_run_cards(runs)
    else:
        st.info("No pipeline runs logged yet.")

    live = load_progress()
    if live and live.get("status") == "running":
        st.info("Model training in progress…")
        render_metric_grid([
            ("Events processed", f"{live.get('processed', 0)}/{live.get('total_events_fetched', 0)}"),
            ("Samples built", str(live.get("samples_built", 0))),
            ("Searches", str(live.get("openai_searches", live.get("serper_calls", 0)))),
            ("Time left", f"{int(live.get('eta_seconds', 0) // 60)} min" if live.get("eta_seconds") else "—"),
        ])

    report = load_evaluation_report()
    if report:
        metrics = report.get("metrics", {})
        ds = report.get("dataset", {})
        render_metric_grid([
            ("Test accuracy", f"{metrics.get('accuracy', 0):.1%}" if metrics.get("accuracy") is not None else "—"),
            ("F1 score", f"{metrics.get('f1', 0):.2f}" if metrics.get("f1") is not None else "—"),
            ("ROC-AUC", f"{metrics.get('roc_auc', 0):.2f}" if metrics.get("roc_auc") is not None else "—"),
            ("Dataset", f"{ds.get('total_samples', 0)} samples"),
        ])
    elif HISTORICAL_DATASET_PATH.exists():
        st.caption(f"Historical dataset: {len(load_dataset())} samples on disk.")
    else:
        st.caption("No evaluation report yet. Run `python -m src.ml.evaluate --rebuild` locally.")


def main() -> None:
    _ensure_app_ready()
    _require_login()
    inject_styles()

    username = st.session_state.get("username", "user")
    if st.session_state.get("nav_page") not in NAV_PAGES:
        st.session_state.nav_page = NAV_PAGES[0]
        st.session_state.pop("selected_sector", None)

    with st.sidebar:
        render_sidebar_brand()
        st.caption(f"Signed in · {username}")
        if st.button("Sign out", use_container_width=True):
            _clear_data_caches()
            for key in ("authenticated", "user_id", "username", "_app_ready", "selected_sector"):
                st.session_state.pop(key, None)
            st.rerun()

    st.markdown(
        '<div style="height:0.75rem;"></div>'
        '<style>'
        '.block-container{padding-top:3.25rem!important;}'
        '[data-testid="stVerticalBlockBorderWrapper"]{overflow:visible!important;'
        'padding:0.55rem 0.65rem!important;margin-bottom:1rem!important;}'
        '</style>',
        unsafe_allow_html=True,
    )
    with st.container(border=True):
        st.pills(
            "Navigate",
            NAV_PAGES,
            selection_mode="single",
            key="nav_page",
            label_visibility="collapsed",
        )

    page_key = st.session_state.nav_page
    page = _NAV_LABELS.get(page_key, page_key)

    if page != "Home" and st.session_state.get("selected_sector"):
        st.session_state.pop("selected_sector", None)

    if page == "Home":
        render_page_header("Home", "Sector activity and live trial drill-downs")
        home_panel()
    elif page == "History":
        render_page_header("History", "Past events, market reactions, and model performance")
        history_panel()
    elif page == "Alerts":
        render_page_header("Alerts", "Email notifications and test delivery")
        alerts_panel()
    elif page == "Account":
        render_page_header("Account", "Profile, configuration, and legal")
        tab = st.segmented_control(
            "Account section",
            ["Profile", "Config", "Legal", "Admin"],
            default="Profile",
            label_visibility="collapsed",
            key="account_tab",
        )
        if tab == "Profile":
            account_panel()
        elif tab == "Config":
            config_panel()
        elif tab == "Legal":
            legal_panel()
        else:
            admin_panel()


if __name__ == "__main__":
    main()
