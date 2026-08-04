"""Streamlit dashboard for healthcare trial scraper."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from src.alert.email import email_configured, normalize_app_password, send_trial_alert, verify_smtp_login
from src.auth.users import (
    authenticate,
    create_user,
    ensure_bootstrap_admin,
    get_user,
    update_alert_email,
    update_password,
    user_count,
)
from src.config import DATA_DIR, FAVORABILITY_THRESHOLD, get_sector_for_hour, hydrate_streamlit_secrets, load_sectors
from src.db.schema import init_db
from src.db.seed import seed_if_empty
from src.ml.historical import HISTORICAL_DATASET_PATH, load_dataset
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
    render_pulse_banner,
    render_rotation_schedule,
    render_run_cards,
    render_settings_rows,
    render_sidebar_brand,
    render_trial_cards_grid,
    render_trial_list_cards,
    render_demo_gallery,
)
from src.ui.demo import get_demo_scenarios, preview_alerts

st.set_page_config(
    page_title="Elentrx™ — Clinical Trial Alerter",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded",
)

LEGAL_FILES = {
    "Disclaimer": DATA_DIR.parent / "DISCLAIMER.md",
    "Terms of Use": DATA_DIR.parent / "TERMS_OF_USE.md",
    "Privacy Policy": DATA_DIR.parent / "PRIVACY_POLICY.md",
    "Trademarks": DATA_DIR.parent / "TRADEMARKS.md",
}

NAV_PAGES = [
    "Watchlist",
    "Trials",
    "Updates",
    "Alerts",
    "Alert demo",
    "Activity",
    "Settings",
]

init_db()
ensure_bootstrap_admin()
seed_if_empty()
hydrate_streamlit_secrets()


def _auth_disabled() -> bool:
    return os.getenv("AUTH_DISABLED", "").lower() in ("1", "true", "yes")


def _require_login() -> None:
    if _auth_disabled():
        if "user" not in st.session_state:
            st.session_state.user = {"username": "dev", "id": 0, "is_admin": True}
        return

    if st.session_state.get("authenticated") and st.session_state.get("user_id"):
        return

    inject_styles()
    st.markdown(
        """
<div style="text-align:center;padding:3rem 1rem 1.5rem;">
  <div style="font-size:2rem;font-weight:700;letter-spacing:-0.04em;color:#0b0f19;">Elentrx</div>
  <div style="color:#64748b;font-size:0.9rem;margin-top:0.35rem;">Clinical trial intelligence</div>
</div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        if user_count() == 0:
            st.markdown("##### Create account")
            with st.form("setup_form"):
                username = st.text_input("Username")
                email = st.text_input("Email")
                password = st.text_input("Password", type="password")
                confirm = st.text_input("Confirm password", type="password")
                submitted = st.form_submit_button("Get started", type="primary", use_container_width=True)
                if submitted:
                    if len(password) < 8:
                        st.error("Password must be at least 8 characters.")
                    elif password != confirm:
                        st.error("Passwords do not match.")
                    elif not username.strip():
                        st.error("Username is required.")
                    else:
                        user = create_user(
                            username=username,
                            password=password,
                            email=email or None,
                            alert_email=email or None,
                            is_admin=True,
                        )
                        st.session_state.authenticated = True
                        st.session_state.user_id = user.id
                        st.session_state.username = user.username
                        st.rerun()
        else:
            st.markdown("##### Sign in")
            with st.form("login_form"):
                username = st.text_input("Username")
                password = st.text_input("Password", type="password")
                submitted = st.form_submit_button("Sign in", type="primary", use_container_width=True)
                if submitted:
                    user = authenticate(username, password)
                    if user:
                        st.session_state.authenticated = True
                        st.session_state.user_id = user.id
                        st.session_state.username = user.username
                        st.rerun()
                    st.error("Invalid username or password.")
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


@st.cache_data(show_spinner=False, ttl=300)
def _cached_digest() -> tuple[dict | None, bool]:
    digest = load_digest_for_display()
    stale = bool(digest and not cache_is_fresh(digest))
    return digest, stale


@st.cache_data(show_spinner=False, ttl=300)
def _cached_trials() -> list[dict]:
    return fetch_trials_enriched(limit=24)


def watchlist_panel() -> None:
    """Instant read — full digest or DB preview fallback."""
    raw_digest, stale = _cached_digest()
    digest, is_preview = merge_digest_with_preview(raw_digest)
    user = get_user(st.session_state.get("user_id", 0))

    if user and user.is_admin:
        if st.button("Rebuild full digest", type="secondary"):
            build_daily_digest(force=True)
            _cached_digest.clear()
            st.rerun()

    if not digest.get("trials"):
        render_empty_watchlist(
            "Trial data will show here once the scraper runs. "
            "Sample trials load automatically on first deploy."
        )
        return

    render_pulse_banner(
        market_pulse=digest.get("market_pulse", ""),
        sector_name=digest.get("sector_name", "—"),
        generated_at=digest.get("generated_at", ""),
        trial_count=digest.get("trial_count", len(digest.get("trials", []))),
        stale=stale and not is_preview,
        preview=is_preview,
    )
    render_trial_cards_grid(digest.get("trials", []))


def rotation_panel() -> None:
    sectors = load_sectors()
    now = datetime.now(timezone.utc)
    current, index = get_sector_for_hour(now.hour)

    render_metric_grid([
        ("Focus now", current["name"]),
        ("Rotation slot", f"{index + 1} of {len(sectors)}"),
        ("Full cycle", f"Every {len(sectors)} hours"),
    ])
    st.markdown("**Upcoming schedule**")
    render_rotation_schedule(sectors, index, now.hour)


def trials_panel() -> None:
    trials = _cached_trials()
    if not trials:
        st.info("No trials yet — the hourly scraper will populate this list.")
        return

    st.markdown(f"**{len(trials)} trials** from publicly traded sponsors")
    ticker_filter = st.text_input("Filter by ticker or company", placeholder="e.g. LLY or Lilly")
    if ticker_filter.strip():
        q = ticker_filter.strip().lower()
        trials = [
            t for t in trials
            if q in t["ticker"].lower() or q in t["sponsor"].lower() or q in (t.get("drug") or "").lower()
        ]

    render_trial_list_cards(trials)


def changes_panel() -> None:
    changes = fetch_phase_changes(limit=20)
    if not changes:
        st.info("No phase changes detected yet — these appear when trials advance or halt.")
        return
    st.markdown(f"**{len(changes)} recent updates**")
    render_change_cards(changes)


def _default_alert_recipient() -> str:
    user = get_user(st.session_state.get("user_id", 0))
    return (user.alert_email if user else None) or os.getenv("ALERT_EMAIL", "")


def render_send_test_alert(*, key_prefix: str = "alert") -> None:
    """One-click test alert with optional Gmail app-password override."""
    recipient_default = _default_alert_recipient()
    smtp_user = os.getenv("SMTP_USER", "")

    st.markdown("#### Send a test alert")
    recipient = st.text_input(
        "Send to",
        value=recipient_default,
        placeholder="you@gmail.com",
        key=f"{key_prefix}_recipient",
    )
    app_password = st.text_input(
        "Gmail App Password",
        type="password",
        placeholder="16 characters — paste from Google App Passwords",
        help=(
            "This is NOT your Gmail login password. "
            "Create one at https://myaccount.google.com/apppasswords "
            "(2-Step Verification must be on for eletrx.trials@gmail.com)."
        ),
        key=f"{key_prefix}_app_password",
    )
    if smtp_user:
        st.caption(f"Sending from **{smtp_user}** via Gmail SMTP")
    else:
        st.warning("Set `SMTP_USER` in `.env` or Streamlit secrets.")

    col_a, col_b = st.columns(2)
    with col_a:
        test_login = st.button("Test login only", use_container_width=True, key=f"{key_prefix}_test_login")
    with col_b:
        send_now = st.button(
            "Send test alert now",
            type="primary",
            use_container_width=True,
            key=f"{key_prefix}_send_btn",
        )

    pw = normalize_app_password(app_password) or None

    if test_login:
        with st.spinner("Testing Gmail login…"):
            ok, msg = verify_smtp_login(pw)
        if ok:
            st.success(msg)
        else:
            st.error(msg)
            st.markdown(
                "**Fix checklist:**\n"
                "1. Open an **incognito** window and sign in as **eletrx.trials@gmail.com** only\n"
                "2. Turn on **2-Step Verification** (Google Account → Security)\n"
                "3. Go to [App Passwords](https://myaccount.google.com/apppasswords) → Mail → Other → name it Elentrx\n"
                "4. Copy all **16 letters** (no spaces) into the field above\n"
                "5. Click **Test login only** again\n\n"
                "Also update `SMTP_PASSWORD` in Streamlit Cloud secrets if testing on the deployed app."
            )

    if send_now:
        if not email_configured(pw):
            st.error("SMTP not configured — need SMTP_HOST, SMTP_USER, and an app password.")
        elif not recipient.strip():
            st.error("Enter a recipient email address.")
        else:
            with st.spinner("Sending test alert…"):
                ok, msg = send_trial_alert(recipient.strip(), smtp_password=pw)
            if ok:
                st.success(f"Test alert sent! {msg}")
                st.balloons()
            else:
                st.error(msg)


def alerts_panel() -> None:
    render_send_test_alert(key_prefix="alerts")
    st.markdown("---")
    alerts = fetch_alerts(limit=30)
    if not alerts:
        st.info("No emails sent yet — favorable trial changes above your threshold will appear here.")
        return
    st.markdown(f"**{len(alerts)} emails sent**")
    render_alert_timeline(alerts)


def runs_panel() -> None:
    runs = fetch_runs(limit=15)
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

    samples = load_dataset()
    if samples:
        st.markdown(f"**Historical samples cached:** {len(samples)}")
        preview = pd.DataFrame([s.to_dict() for s in samples[:12]])[
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
        ("Notifications", "Email only"),
        ("Alert email", os.getenv("ALERT_EMAIL", "") or "Not set"),
        ("Email configured", "Yes" if email_configured() else "No — add SMTP in secrets"),
        ("OpenAI configured", "Yes" if os.getenv("OPENAI_API_KEY") else "No"),
        ("Score threshold", f"{FAVORABILITY_THRESHOLD:.0%}"),
    ])
    st.caption("When a trial change scores above the threshold, Elentrx sends one email alert.")


def demo_panel() -> None:
    render_send_test_alert(key_prefix="demo")
    st.markdown("---")
    scenarios = get_demo_scenarios()
    previews = {s.id: preview_alerts(s) for s in scenarios}
    st.markdown(
        f'<p class="page-sub">Examples only — not real alerts. '
        f"Your threshold is <b>{FAVORABILITY_THRESHOLD:.0%}</b>.</p>",
        unsafe_allow_html=True,
    )
    render_demo_gallery(scenarios, previews)


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
    _require_login()
    inject_styles()

    username = st.session_state.get("username", "user")
    if "nav_page" not in st.session_state:
        st.session_state.nav_page = NAV_PAGES[0]

    with st.sidebar:
        render_sidebar_brand()
        sidebar_page = st.radio(
            "Navigation",
            NAV_PAGES,
            index=NAV_PAGES.index(st.session_state.nav_page),
            label_visibility="collapsed",
            key="sidebar_nav",
        )
        if sidebar_page != st.session_state.nav_page:
            st.session_state.nav_page = sidebar_page
        st.markdown("---")
        st.caption(f"Signed in · {username}")
        st.caption("Use the **›** button top-left or the nav bar below to switch pages.")
        if st.button("Sign out", use_container_width=True):
            _cached_digest.clear()
            for key in ("authenticated", "user_id", "username"):
                st.session_state.pop(key, None)
            st.rerun()

    st.markdown('<div class="top-nav-wrap">', unsafe_allow_html=True)
    top_page = st.pills(
        "Pages",
        NAV_PAGES,
        default=st.session_state.nav_page,
        selection_mode="single",
        label_visibility="collapsed",
        key="top_nav_pills",
    )
    st.markdown("</div>", unsafe_allow_html=True)
    if top_page and top_page != st.session_state.nav_page:
        st.session_state.nav_page = top_page
        st.rerun()

    page = st.session_state.nav_page

    if page == "Watchlist":
        watchlist_panel()
    elif page == "Trials":
        st.markdown('<p class="page-title">Trials</p><p class="page-sub">Public biotech studies we\'re tracking</p>', unsafe_allow_html=True)
        trials_panel()
    elif page == "Updates":
        st.markdown('<p class="page-title">Updates</p><p class="page-sub">Phase advances, completions, and halts</p>', unsafe_allow_html=True)
        changes_panel()
    elif page == "Alerts":
        st.markdown('<p class="page-title">Alerts</p><p class="page-sub">Email notifications we\'ve sent you</p>', unsafe_allow_html=True)
        alerts_panel()
    elif page == "Alert demo":
        st.markdown(
            '<p class="page-title">Alert demo</p><p class="page-sub">'
            "See what favorable, neutral, and negative changes look like</p>",
            unsafe_allow_html=True,
        )
        demo_panel()
    elif page == "Activity":
        st.markdown('<p class="page-title">Activity</p><p class="page-sub">Rotation, runs & model eval</p>', unsafe_allow_html=True)
        t1, t2, t3 = st.tabs(["Rotation", "Runs", "Evaluation"])
        with t1:
            rotation_panel()
        with t2:
            runs_panel()
        with t3:
            evaluation_panel()
    elif page == "Settings":
        st.markdown('<p class="page-title">Settings</p><p class="page-sub">Account, config & legal</p>', unsafe_allow_html=True)
        t1, t2, t3 = st.tabs(["Account", "Config", "Legal"])
        with t1:
            account_panel()
        with t2:
            config_panel()
        with t3:
            legal_panel()


if __name__ == "__main__":
    main()
