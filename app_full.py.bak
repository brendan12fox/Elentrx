"""Streamlit dashboard for healthcare trial scraper."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import pandas as pd
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
from src.pipeline.run_hourly import run_hourly
from src.research.watchlist import (
    build_daily_digest,
    cache_is_fresh,
    load_digest_for_display,
)
from src.ui.trial_data import (
    fetch_alerts,
    fetch_phase_changes,
    fetch_runs,
    fetch_trials_enriched,
    merge_digest_with_preview,
)
from src.ui.styles import (
    inject_styles,
    render_alert_timeline,
    render_change_cards,
    render_empty_watchlist,
    render_metric_grid,
    render_page_header,
    render_pulse_banner,
    render_rotation_schedule,
    render_run_cards,
    render_section_label,
    render_settings_rows,
    render_sidebar_brand,
    render_trial_cards_grid,
    render_trial_list_cards,
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
    "Watchlist": "Watchlist",
    "Trials": "Trials",
    "Updates": "Updates",
    "Alerts": "Alerts",
    "Activity": "Activity",
    "Settings": "Settings",
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
        _cached_digest.clear()
        for key in ("authenticated", "user_id", "username"):
            st.session_state.pop(key, None)
        st.rerun()


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


@st.cache_data(show_spinner=False, ttl=300)
def _cached_trials() -> list[dict]:
    return fetch_trials_enriched(limit=200, active_first=True)


@st.cache_data(show_spinner=False, ttl=60)
def _cached_alerts() -> list[dict]:
    return fetch_alerts(limit=30)


@st.cache_data(show_spinner=False, ttl=60)
def _cached_changes() -> list[dict]:
    return fetch_phase_changes(limit=20)


@st.cache_data(show_spinner=False, ttl=60)
def _cached_runs() -> list[dict]:
    return fetch_runs(limit=15)


@st.cache_data(show_spinner=False, ttl=300)
def _cached_dataset_count() -> int:
    return len(load_dataset())


@st.cache_data(show_spinner=False, ttl=300)
def _cached_eval_samples() -> list[dict]:
    samples = load_dataset()
    return [s.to_dict() for s in samples[:12]] if samples else []


def _clear_data_caches() -> None:
    """Force Streamlit panels to re-read DB / digest after a manual scan."""
    for fn in (
        _cached_digest,
        _cached_trials,
        _cached_alerts,
        _cached_changes,
        _cached_runs,
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


def watchlist_panel() -> None:
    """Instant read — full cross-sector catalogue, with AI digest enrichment when available."""
    raw_digest, stale = _cached_digest()
    digest, is_preview = merge_digest_with_preview(raw_digest)
    user = get_user(st.session_state.get("user_id", 0))
    focus, _ = get_sector_for_hour()

    if user and user.is_admin:
        if st.button("Rebuild full digest", type="secondary"):
            build_daily_digest(force=True)
            _clear_data_caches()
            st.rerun()

    with st.expander("Manual sector refresh", expanded=False):
        render_manual_refresh(key_prefix="watchlist")

    trials = digest.get("trials") or []
    if not trials:
        render_empty_watchlist(
            "Trial data will show here once the scraper runs. "
            "Sample trials load automatically on first deploy."
        )
        return

    render_pulse_banner(
        market_pulse=digest.get("market_pulse", ""),
        sector_name=digest.get("focus_sector_name") or digest.get("sector_name") or focus["name"],
        generated_at=digest.get("generated_at", ""),
        trial_count=digest.get("trial_count", len(trials)),
        stale=stale and not is_preview,
        preview=is_preview,
        sectors_covered=digest.get("sectors_covered"),
        all_sectors=bool(digest.get("all_sectors", True)),
    )

    sector_options = ["All sectors"] + sorted(
        {t.get("sector") for t in trials if t.get("sector")}
    )
    sector_filter = st.selectbox(
        "Filter by sector",
        sector_options,
        index=0,
        help=f"Hourly scraper is currently scanning {focus['name']}.",
    )
    if sector_filter != "All sectors":
        trials = [t for t in trials if t.get("sector") == sector_filter]

    render_trial_cards_grid(trials, quotes=_quotes_for(trials))


def rotation_panel() -> None:
    sectors = load_sectors()
    now = datetime.now(timezone.utc)
    current, index = get_sector_for_hour(now.hour)

    render_metric_grid([
        ("Focus now", current["name"]),
        ("Rotation slot", f"{index + 1} of {len(sectors)}"),
        ("Full cycle", f"Every {len(sectors)} hours"),
    ])
    render_manual_refresh(key_prefix="rotation")
    st.markdown("**Upcoming schedule**")
    render_rotation_schedule(sectors, index, now.hour)


def trials_panel() -> None:
    trials = _cached_trials()
    if not trials:
        st.info("No trials yet — the hourly scraper will populate this list.")
        return

    render_section_label(f"{len(trials)} trials from publicly traded sponsors")
    ticker_filter = st.text_input("Filter by ticker or company", placeholder="e.g. LLY or Lilly")
    if ticker_filter.strip():
        q = ticker_filter.strip().lower()
        trials = [
            t for t in trials
            if q in t["ticker"].lower() or q in t["sponsor"].lower() or q in (t.get("drug") or "").lower()
        ]

    render_trial_list_cards(trials, quotes=_quotes_for(trials))


def changes_panel() -> None:
    changes = _cached_changes()
    if not changes:
        st.info("No phase changes detected yet — these appear when trials advance or halt.")
        return
    st.markdown(f"**{len(changes)} recent updates**")
    render_change_cards(changes, quotes=_quotes_for(changes))


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


def runs_panel() -> None:
    runs = _cached_runs()
    if not runs:
        st.info("No pipeline runs logged yet.")
        return
    st.markdown("**Recent scraper runs**")
    render_run_cards(runs)


def evaluation_panel() -> None:
    report_path = DATA_DIR / "evaluation_report.json"
    from src.ml.progress import load_progress

    live = load_progress()
    if live and live.get("status") == "running":
        st.info("Model training in progress…")
        render_metric_grid([
            ("Events processed", f"{live.get('processed', 0)}/{live.get('total_events_fetched', 0)}"),
            ("Samples built", str(live.get("samples_built", 0))),
            ("Searches", str(live.get("openai_searches", live.get("serper_calls", 0)))),
            ("Time left", f"{int(live.get('eta_seconds', 0) // 60)} min" if live.get("eta_seconds") else "—"),
        ])

    st.caption(
        "How we score the model: news is cut off at each event date; "
        "labels use 5-day stock returns after the event."
    )

    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        metrics = report.get("metrics", {})
        render_metric_grid([
            ("Test accuracy", f"{metrics.get('accuracy', 0):.1%}" if metrics.get("accuracy") is not None else "—"),
            ("F1 score", f"{metrics.get('f1', 0):.2f}" if metrics.get("f1") is not None else "—"),
            ("ROC-AUC", f"{metrics.get('roc_auc', 0):.2f}" if metrics.get("roc_auc") is not None else "—"),
            ("Baseline", f"{metrics.get('baseline_accuracy', 0):.1%}" if metrics.get("baseline_accuracy") is not None else "—"),
        ])
        ds = report.get("dataset", {})
        st.markdown(
            f"**Dataset:** {ds.get('total_samples', 0)} samples · "
            f"train {ds.get('train_date_range', ['',''])[0]} → "
            f"test {ds.get('test_date_range', ['',''])[-1]}"
        )
    else:
        st.info("No evaluation report yet. Run `python -m src.ml.evaluate --rebuild` locally.")

    sample_rows = _cached_eval_samples()
    if sample_rows:
        st.markdown(f"**Historical samples cached:** {_cached_dataset_count()}")
        preview = pd.DataFrame(sample_rows)[
            ["event_date", "ticker", "nct_id", "label", "analyst_tone"]
        ].rename(columns={
            "event_date": "Date",
            "ticker": "Ticker",
            "nct_id": "Trial ID",
            "label": "Favorable",
            "analyst_tone": "Tone",
        })
        st.dataframe(preview, hide_index=True, use_container_width=True)


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


def main() -> None:
    _ensure_app_ready()
    _require_login()
    inject_styles()

    username = st.session_state.get("username", "user")
    # Drop removed pages (e.g. old Demo) from session so nav stays valid.
    if st.session_state.get("nav_page") not in NAV_PAGES:
        st.session_state.nav_page = NAV_PAGES[0]

    with st.sidebar:
        render_sidebar_brand()
        st.caption(f"Signed in · {username}")
        if st.button("Sign out", use_container_width=True):
            _cached_digest.clear()
            for key in ("authenticated", "user_id", "username", "_app_ready"):
                st.session_state.pop(key, None)
            st.rerun()

    # Keep nav clear of the Streamlit header so pill tops aren't clipped.
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

    if page == "Watchlist":
        render_page_header("Watchlist", "Daily sector digest and tracked trials")
        watchlist_panel()
    elif page == "Trials":
        render_page_header("Trials", "Public biotech studies we're tracking")
        trials_panel()
    elif page == "Updates":
        render_page_header("Updates", "Phase advances, completions, and halts")
        changes_panel()
    elif page == "Alerts":
        render_page_header("Alerts", "Email notifications and test delivery")
        alerts_panel()
    elif page == "Activity":
        render_page_header("Activity", "Rotation schedule, pipeline runs, and model evaluation")
        tab = st.segmented_control(
            "Activity section",
            ["Rotation", "Runs", "Evaluation"],
            default="Rotation",
            label_visibility="collapsed",
            key="activity_tab",
        )
        if tab == "Rotation":
            rotation_panel()
        elif tab == "Runs":
            runs_panel()
        else:
            evaluation_panel()
    elif page == "Settings":
        render_page_header("Settings", "Account, configuration, and legal")
        tab = st.segmented_control(
            "Settings section",
            ["Account", "Config", "Legal"],
            default="Account",
            label_visibility="collapsed",
            key="settings_tab",
        )
        if tab == "Account":
            account_panel()
        elif tab == "Config":
            config_panel()
        else:
            legal_panel()


if __name__ == "__main__":
    main()
