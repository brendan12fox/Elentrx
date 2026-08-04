"""Modern UI styles and components for Elentrx."""

from __future__ import annotations

import html

import streamlit as st

from src.ui.brand import render_sidebar_logo
from src.ui.links import inline_ctgov_link, trial_links_html

TONE = {
    "bullish": ("#059669", "#ecfdf5", "↑"),
    "bearish": ("#dc2626", "#fef2f2", "↓"),
    "neutral": ("#64748b", "#f8fafc", "→"),
}


def inject_styles() -> None:
    if st.session_state.get("_styles_loaded"):
        return
    st.session_state._styles_loaded = True
    st.markdown(
        """
<style>
    :root {
        --bg: #ffffff;
        --surface: #f5f8fa;
        --text: #001d3d;
        --muted: #4a6278;
        --border: #dce4ec;
        --accent: #00c4a7;
        --accent-dark: #001d3d;
        --accent-soft: #e6faf6;
        --sidebar: #001d3d;
    }

    html, body, [class*="css"] {
        font-family: "SF Pro Display", system-ui, -apple-system, "Segoe UI", sans-serif;
    }

    .stApp {
        background:
            radial-gradient(ellipse 70% 50% at 0% 0%, rgba(0, 196, 167, 0.08), transparent),
            radial-gradient(ellipse 50% 40% at 100% 0%, rgba(0, 29, 61, 0.05), transparent),
            linear-gradient(180deg, #ffffff 0%, #f5f8fa 100%) !important;
    }

    .block-container { padding-top: 1rem; max-width: 1180px; }

    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #001d3d 0%, #002847 100%) !important;
        border-right: none !important;
        box-shadow: 4px 0 24px rgba(0, 29, 61, 0.2);
    }
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] .stCaption,
    [data-testid="stSidebar"] small {
        color: #e2e8f0 !important;
    }
    [data-testid="stSidebar"] .stRadio > div {
        gap: 0.25rem;
    }
    [data-testid="stSidebar"] .stRadio label[data-baseweb="radio"] {
        background: transparent !important;
        padding: 0.45rem 0.65rem !important;
        border-radius: 8px !important;
    }
    [data-testid="stSidebar"] .stRadio label[data-baseweb="radio"]:has(input:checked) {
        background: rgba(0, 196, 167, 0.15) !important;
        border: 1px solid rgba(0, 196, 167, 0.45) !important;
    }
    [data-testid="stSidebar"] hr { border-color: rgba(255,255,255,0.1); }
    [data-testid="stSidebar"] .stButton button {
        background: rgba(255,255,255,0.08) !important;
        border: 1px solid rgba(255,255,255,0.15) !important;
        color: #f8fafc !important;
    }

    #MainMenu, footer { visibility: hidden; height: 0; }
    [data-testid="stHeader"] {
        background: rgba(255,255,255,0.85) !important;
        backdrop-filter: blur(8px);
    }
    /* Keep toolbar visible — it contains the sidebar expand/collapse button */
    [data-testid="stToolbar"] {
        visibility: visible !important;
        display: flex !important;
        opacity: 1 !important;
        z-index: 999998 !important;
    }
    [data-testid="stSidebarCollapsedControl"],
    [data-testid="collapsedControl"],
    button[kind="header"] {
        visibility: visible !important;
        display: flex !important;
        opacity: 1 !important;
        z-index: 999999 !important;
    }
    .stAppDeployButton, [data-testid="stMainMenu"] { display: none !important; }

    .nav-bar {
        background: #ffffff;
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: 0.5rem 0.65rem;
        margin-bottom: 1.25rem;
        box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
    }
    .nav-bar [data-testid="stPills"] button {
        border-radius: 10px !important;
        font-size: 0.8rem !important;
        font-weight: 600 !important;
        padding: 0.4rem 0.75rem !important;
    }

    [data-testid="stSidebar"] [data-testid="stImage"] {
        background: transparent;
        border-radius: 0;
        padding: 0;
        margin-bottom: 0.35rem;
        box-shadow: none;
        width: fit-content;
        max-width: 100%;
    }
    [data-testid="stSidebar"] [data-testid="stImage"] img {
        width: auto !important;
        max-width: 100% !important;
        height: auto !important;
        display: block;
        image-rendering: auto;
    }
    [data-testid="stImage"]:has(+ .auth-tagline) img {
        width: auto !important;
        max-width: 100% !important;
        height: auto !important;
        display: block;
        margin: 0 auto;
    }

    .sidebar-logo-wrap {
        background: #ffffff;
        border-radius: 14px;
        padding: 0.65rem 0.75rem;
        margin-bottom: 0.35rem;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
        text-align: center;
    }
    .elentrx-logo-img {
        display: block;
        max-width: 100%;
        height: auto;
        margin: 0 auto;
    }
    .auth-logo-wrap {
        text-align: center;
        margin-bottom: 0.5rem;
    }
    [data-testid="stImage"]:has(+ .auth-tagline) {
        display: flex;
        justify-content: center;
    }
    .brand-sub {
        font-size: 0.72rem;
        color: #7eb8aa;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        margin-bottom: 1.5rem;
    }

    .pulse-banner {
        background: linear-gradient(135deg, #ffffff 0%, #f0fdfb 100%);
        border: 1px solid #b8ebe3;
        border-radius: 20px;
        padding: 1.75rem 2rem;
        margin-bottom: 1.5rem;
        box-shadow: 0 8px 32px rgba(0, 196, 167, 0.1);
        position: relative;
        overflow: hidden;
    }
    .pulse-banner::before {
        content: '';
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 4px;
        background: linear-gradient(90deg, #001d3d, #00c4a7);
    }
    .pulse-label {
        font-size: 0.7rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        color: var(--accent);
        margin-bottom: 0.65rem;
    }
    .pulse-text {
        font-size: 1.125rem;
        font-weight: 500;
        line-height: 1.6;
        color: var(--text);
        margin: 0 0 1rem 0;
    }
    .stat-row { display: flex; flex-wrap: wrap; gap: 0.5rem; }
    .stat-chip {
        background: linear-gradient(135deg, #f0fdfa, #eef2ff);
        border: 1px solid #cbd5e1;
        border-radius: 10px;
        padding: 0.35rem 0.75rem;
        font-size: 0.78rem;
        color: #475569;
        font-weight: 600;
    }

    .cards-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
        gap: 1rem;
    }

    .card {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 16px;
        padding: 1.25rem;
        display: flex;
        flex-direction: column;
        gap: 0.75rem;
        transition: transform 0.15s, box-shadow 0.15s;
        border-left: 4px solid var(--accent);
    }
    .card:hover {
        transform: translateY(-2px);
        box-shadow: 0 12px 32px rgba(99, 102, 241, 0.12);
    }

    .card-top {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 0.75rem;
    }
    .card-ticker {
        font-size: 1.5rem;
        font-weight: 700;
        letter-spacing: -0.03em;
        color: var(--text);
        line-height: 1;
    }
    .card-nct {
        font-size: 0.72rem;
        color: var(--muted);
        font-weight: 500;
        margin-top: 0.25rem;
    }
    .quote-chip {
        display: inline-block;
        margin-top: 0.35rem;
        background: #f1f5f9;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 0.2rem 0.55rem;
        font-size: 0.78rem;
        font-weight: 600;
        color: #334155;
    }
    .quote-chip.quote-up { border-color: #a7f3d0; background: #ecfdf5; color: #047857; }
    .quote-chip.quote-down { border-color: #fecaca; background: #fef2f2; color: #b91c1c; }
    .tone-pill {
        font-size: 0.65rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        padding: 0.3rem 0.55rem;
        border-radius: 8px;
        white-space: nowrap;
    }
    .card-headline {
        font-size: 0.95rem;
        font-weight: 600;
        color: #1e293b;
        line-height: 1.4;
    }
    .card-brief {
        font-size: 0.84rem;
        color: var(--muted);
        line-height: 1.6;
    }
    .tag-row { display: flex; flex-wrap: wrap; gap: 0.35rem; }
    .tag {
        font-size: 0.68rem;
        font-weight: 500;
        padding: 0.2rem 0.55rem;
        border-radius: 6px;
        background: var(--bg);
        color: var(--muted);
        border: 1px solid var(--border);
    }
    .tag-score { background: #eff6ff; color: #1d4ed8; border-color: #bfdbfe; }
    .tag-catalyst { background: var(--accent-soft); color: #001d3d; border-color: #b8ebe3; }

    .links-block {
        border-top: 1px solid var(--border);
        padding-top: 0.65rem;
        margin-top: auto;
    }
    .links-label {
        font-size: 0.65rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: var(--muted);
        margin-bottom: 0.45rem;
    }
    .link-row {
        display: block;
        font-size: 0.78rem;
        color: #001d3d;
        text-decoration: none;
        padding: 0.45rem 0;
        line-height: 1.4;
        border-bottom: 1px solid #eef2f6;
    }
    .link-row:hover { color: var(--accent); }
    .link-row:last-child { border-bottom: none; }
    .link-title { display: block; font-weight: 600; color: inherit; }
    .link-meta, .link-hint { color: #94a3b8; font-size: 0.7rem; }
    .link-hint { display: block; margin-top: 0.35rem; }
    .ctgov-link { font-weight: 600; }
    .link-icon { color: var(--accent); margin-right: 0.2rem; }
    .inline-link { color: var(--accent); font-weight: 600; text-decoration: none; }
    .inline-link:hover { text-decoration: underline; }

    .empty-state {
        text-align: center;
        padding: 4rem 2rem;
        background: var(--surface);
        border: 1px dashed var(--border);
        border-radius: 20px;
        color: var(--muted);
    }
    .empty-state h3 { color: var(--text); font-weight: 600; margin-bottom: 0.5rem; }

    .login-wrap {
        max-width: 400px;
        margin: 4rem auto;
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 24px;
        padding: 2.5rem 2rem;
        box-shadow: 0 24px 48px rgba(11, 15, 25, 0.08);
    }
    .login-title {
        font-size: 1.75rem;
        font-weight: 700;
        letter-spacing: -0.04em;
        text-align: center;
        margin-bottom: 0.35rem;
    }
    .login-sub { text-align: center; color: var(--muted); font-size: 0.875rem; margin-bottom: 1.75rem; }

    .page-title {
        font-size: 1.5rem;
        font-weight: 700;
        letter-spacing: -0.03em;
        color: var(--text);
        margin: 0 0 0.25rem 0;
    }
    .page-sub { color: var(--muted); font-size: 0.875rem; margin-bottom: 1.25rem; }

    .preview-badge {
        display: inline-block;
        background: #fef3c7;
        color: #92400e;
        border: 1px solid #fcd34d;
        border-radius: 8px;
        padding: 0.25rem 0.65rem;
        font-size: 0.72rem;
        font-weight: 600;
        margin-bottom: 1rem;
    }

    .list-card {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: 1rem 1.15rem;
        margin-bottom: 0.65rem;
    }
    .list-card-top {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 0.35rem;
    }
    .list-ticker { font-weight: 700; font-size: 1.05rem; color: var(--text); }
    .list-meta { font-size: 0.78rem; color: var(--muted); line-height: 1.5; }
    .list-snippet { font-size: 0.84rem; color: #475569; line-height: 1.55; margin-top: 0.5rem; }

    .timeline-item {
        border-left: 2px solid var(--border);
        padding: 0 0 1rem 1rem;
        margin-left: 0.35rem;
        position: relative;
    }
    .timeline-item::before {
        content: '';
        width: 8px; height: 8px;
        background: var(--accent);
        border-radius: 50%;
        position: absolute;
        left: -5px; top: 0.35rem;
    }
    .timeline-when { font-size: 0.72rem; color: #94a3b8; margin-bottom: 0.2rem; }
    .timeline-title { font-weight: 600; font-size: 0.9rem; color: var(--text); }
    .timeline-body { font-size: 0.82rem; color: var(--muted); margin-top: 0.25rem; }

    .schedule-row {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        padding: 0.55rem 0;
        border-bottom: 1px solid #f1f5f9;
        font-size: 0.85rem;
    }
    .schedule-row.active { font-weight: 600; color: var(--accent); }
    .schedule-hour { width: 3rem; color: var(--muted); font-size: 0.78rem; }

    .metric-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
        gap: 0.65rem;
        margin-bottom: 1rem;
    }
    .metric-box {
        background: linear-gradient(145deg, #ffffff, #f8fafc);
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: 0.85rem 1rem;
        border-top: 3px solid #00c4a7;
    }
    .metric-box:nth-child(2) { border-top-color: #001d3d; }
    .metric-box:nth-child(3) { border-top-color: #00c4a7; }
    .metric-box:nth-child(4) { border-top-color: #4a6278; }
    .metric-label { font-size: 0.72rem; color: var(--muted); font-weight: 500; }
    .metric-value { font-size: 1.25rem; font-weight: 700; color: var(--text); margin-top: 0.15rem; }

    .settings-row {
        display: flex;
        justify-content: space-between;
        padding: 0.65rem 0;
        border-bottom: 1px solid #f1f5f9;
        font-size: 0.875rem;
    }
    .settings-label { color: var(--muted); }
    .settings-value { font-weight: 500; color: var(--text); }

    /* —— Alert demo —— */
    .demo-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
        gap: 1.25rem;
        margin-bottom: 1.5rem;
    }
    .demo-scenario {
        border-radius: 18px;
        overflow: hidden;
        background: #fff;
        border: 1px solid #e2e8f0;
        box-shadow: 0 8px 30px rgba(15, 23, 42, 0.08);
    }
    .demo-scenario-header {
        padding: 1.1rem 1.25rem;
        color: #fff;
    }
    .demo-scenario-header h3 { margin: 0; font-size: 1.05rem; font-weight: 700; }
    .demo-scenario-header p { margin: 0.25rem 0 0; font-size: 0.78rem; opacity: 0.9; }
    .demo-scenario-body { padding: 1.15rem 1.25rem; }
    .demo-score-bar {
        height: 8px;
        background: #e2e8f0;
        border-radius: 99px;
        overflow: hidden;
        margin: 0.65rem 0;
    }
    .demo-score-fill { height: 100%; border-radius: 99px; }
    .demo-alert-badge {
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
        padding: 0.35rem 0.75rem;
        border-radius: 8px;
        font-size: 0.75rem;
        font-weight: 700;
        margin-bottom: 0.75rem;
    }
    .demo-alert-yes { background: #ecfdf5; color: #047857; border: 1px solid #6ee7b7; }
    .demo-alert-no { background: #f1f5f9; color: #64748b; border: 1px solid #cbd5e1; }

    .email-mock {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 14px;
        overflow: hidden;
        margin-top: 0.75rem;
    }
    .email-mock-bar {
        background: linear-gradient(90deg, #001d3d, #00c4a7);
        padding: 0.5rem 1rem;
        font-size: 0.7rem;
        font-weight: 600;
        color: #fff;
        letter-spacing: 0.04em;
    }
    .email-mock-inner { padding: 1rem; font-size: 0.82rem; color: #334155; line-height: 1.55; }
    .email-subject { font-weight: 700; color: #001d3d; margin-bottom: 0.65rem; }
    .email-from { font-size: 0.72rem; color: #64748b; margin-bottom: 0.5rem; }

    /* Auth screen */
    .auth-backdrop {
        position: fixed;
        inset: 0;
        pointer-events: none;
        z-index: 0;
        overflow: hidden;
    }
    .auth-glow {
        position: absolute;
        border-radius: 50%;
        filter: blur(80px);
        opacity: 0.45;
    }
    .auth-glow-a {
        width: 420px; height: 420px;
        background: rgba(0, 196, 167, 0.25);
        top: -120px; left: -80px;
    }
    .auth-glow-b {
        width: 380px; height: 380px;
        background: rgba(0, 29, 61, 0.12);
        top: 10%; right: -100px;
    }
    .auth-shell { text-align: center; padding: 2.5rem 1rem 1rem; position: relative; z-index: 1; }
    .auth-hero { max-width: 520px; margin: 0 auto 1.5rem; }
    .auth-tagline { color: #4a6278; font-size: 1rem; margin-top: 0.35rem; }
    .auth-features {
        list-style: none;
        padding: 0;
        margin: 1.25rem auto 0;
        max-width: 340px;
        text-align: left;
    }
    .auth-features li {
        color: #475569;
        font-size: 0.88rem;
        padding: 0.45rem 0 0.45rem 1.5rem;
        position: relative;
        line-height: 1.45;
    }
    .auth-features li::before {
        content: '';
        position: absolute;
        left: 0; top: 0.75rem;
        width: 8px; height: 8px;
        border-radius: 50%;
        background: linear-gradient(135deg, #00c4a7, #001d3d);
    }
    .auth-card-label {
        font-size: 0.72rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        color: #94a3b8;
        margin-bottom: 0.5rem;
    }
    [data-testid="stForm"] {
        background: rgba(255,255,255,0.92) !important;
        border: 1px solid #e2e8f0 !important;
        border-radius: 18px !important;
        padding: 1.25rem 1.35rem !important;
        box-shadow: 0 20px 40px rgba(15, 23, 42, 0.08) !important;
        backdrop-filter: blur(12px);
    }

    .alert-send-card {
        background: linear-gradient(135deg, #ffffff 0%, #f0fdfb 100%);
        border: 1px solid #b8ebe3;
        border-radius: 16px;
        padding: 1.25rem 1.5rem;
        margin-bottom: 1.25rem;
    }
    .alert-send-card h4 {
        margin: 0 0 0.25rem 0;
        font-size: 1.05rem;
        font-weight: 700;
        color: var(--text);
    }
    .status-pill {
        display: inline-block;
        padding: 0.3rem 0.7rem;
        border-radius: 999px;
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.02em;
    }
    .status-pill.ok { background: #ecfdf5; color: #047857; border: 1px solid #6ee7b7; }
    .status-pill.warn { background: #fef2f2; color: #b91c1c; border: 1px solid #fecaca; }
</style>
        """,
        unsafe_allow_html=True,
    )


def render_page_header(title: str, subtitle: str) -> None:
    st.markdown(f'<p class="page-title">{html.escape(title)}</p>', unsafe_allow_html=True)
    st.markdown(f'<p class="page-sub">{subtitle}</p>', unsafe_allow_html=True)


def render_sidebar_brand() -> None:
    render_sidebar_logo()


def render_login_shell(title: str = "Welcome back") -> None:
    inject_styles()
    st.markdown(
        f"""
<div class="login-wrap">
  <div class="login-title">Elentrx</div>
  <div class="login-sub">{html.escape(title)}</div>
</div>
        """,
        unsafe_allow_html=True,
    )


def render_pulse_banner(
    market_pulse: str,
    sector_name: str,
    generated_at: str,
    trial_count: int,
    *,
    stale: bool = False,
    preview: bool = False,
) -> None:
    updated = generated_at[:16].replace("T", " ") + " UTC" if generated_at else "—"
    notes = []
    if preview:
        notes.append("snapshot preview")
    if stale:
        notes.append("last full digest")
    note = f" · {' · '.join(notes)}" if notes else ""
    preview_badge = (
        '<div class="preview-badge">Snapshot preview — full AI digest updates daily</div>'
        if preview
        else ""
    )
    st.markdown(preview_badge, unsafe_allow_html=True)
    st.markdown(
        f"""
<div class="pulse-banner">
  <div class="pulse-label">Today's focus · {html.escape(sector_name)}{html.escape(note)}</div>
  <p class="pulse-text">{html.escape(market_pulse)}</p>
  <div class="stat-row">
    <span class="stat-chip">{trial_count} trials</span>
    <span class="stat-chip">As of {html.escape(updated)}</span>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )


def render_trial_cards_grid(trials: list[dict], quotes: dict | None = None) -> None:
    cards_html = ['<div class="cards-grid">']
    for trial in trials:
        ticker = (trial.get("ticker") or "").upper()
        quote = (quotes or {}).get(ticker)
        cards_html.append(_trial_card_html(trial, quote))
    cards_html.append("</div>")
    st.markdown("\n".join(cards_html), unsafe_allow_html=True)


def _trial_card_html(trial: dict, quote=None) -> str:
    from src.market.quotes import StockQuote, format_quote_chip

    if quote and not isinstance(quote, StockQuote):
        quote = None
    tone = (trial.get("analyst_tone") or "neutral").lower()
    fg, bg, arrow = TONE.get(tone, TONE["neutral"])
    score = trial.get("score")
    score_tag = (
        f'<span class="tag tag-score">{score:.0%} score</span>' if score is not None else ""
    )
    phase = html.escape((trial.get("phase") or "—").replace("_", " "))
    ticker = html.escape(str(trial.get("ticker", "—")))
    quote_html = format_quote_chip(quote)
    nct_id = html.escape(str(trial.get("nct_id", "")))
    headline = html.escape(str(trial.get("headline", "")))
    brief = html.escape(str(trial.get("brief", "")))
    reason = html.escape(str(trial.get("watch_reason", "")))
    catalysts = trial.get("catalysts") or []
    cat_tags = "".join(f'<span class="tag tag-catalyst">{html.escape(str(c))}</span>' for c in catalysts[:2])
    links_html = trial_links_html(trial)

    return f"""
<div class="card" style="border-left-color:{fg};">
  <div class="card-top">
    <div>
      <div class="card-ticker">{ticker}</div>
      {quote_html}
      <div class="card-nct">{nct_id}</div>
    </div>
    <span class="tone-pill" style="color:{fg};background:{bg};">{arrow} {tone}</span>
  </div>
  <div class="card-headline">{headline}</div>
  <div class="card-brief">{brief}</div>
  <div class="tag-row">{score_tag}<span class="tag">{phase}</span><span class="tag">{reason}</span>{cat_tags}</div>
  {links_html}
</div>"""


def render_empty_watchlist(message: str) -> None:
    st.markdown(
        f"""
<div class="empty-state">
  <h3>Nothing here yet</h3>
  <p>{html.escape(message)}</p>
</div>
        """,
        unsafe_allow_html=True,
    )


def render_trial_list_cards(trials: list[dict], quotes: dict | None = None) -> None:
    from src.market.quotes import StockQuote, format_quote_chip

    for t in trials:
        score = t.get("score")
        score_badge = f" · {score:.0%} favorability" if score is not None else ""
        ticker = (t.get("ticker") or "").upper()
        quote = (quotes or {}).get(ticker)
        if quote and not isinstance(quote, StockQuote):
            quote = None
        quote_html = format_quote_chip(quote)
        quote_row = f'<div style="margin:0.35rem 0;">{quote_html}</div>' if quote_html else ""
        nct_link = inline_ctgov_link(t.get("nct_id", ""))
        st.markdown(
            f"""
<div class="list-card">
  <div class="list-card-top">
    <span class="list-ticker">{html.escape(t.get('ticker',''))}</span>
    <span class="tag">{html.escape(t.get('phase_label',''))}</span>
  </div>
  {quote_row}
  <div class="list-meta">
    {html.escape(t.get('drug') or 'Unknown drug')} · {html.escape(t.get('sponsor',''))}<br>
    {html.escape(t.get('status_label',''))} · {html.escape(t.get('sector',''))}{html.escape(score_badge)}
  </div>
  <div class="list-snippet">{html.escape(t.get('brief',''))}</div>
  <div class="list-meta" style="margin-top:0.4rem;">{nct_link}</div>
</div>
            """,
            unsafe_allow_html=True,
        )


def render_change_cards(changes: list[dict], quotes: dict | None = None) -> None:
    from src.market.quotes import StockQuote, format_quote_chip

    for c in changes:
        when = (c.get("detected_at") or "")[:16].replace("T", " ")
        tone = (c.get("analyst_tone") or "neutral").lower()
        fg, bg, arrow = TONE.get(tone, TONE["neutral"])
        score_line = f"Favorability {c['score']:.0%}" if c.get("score") is not None else "Not scored yet"
        ticker = (c.get("ticker") or "").upper()
        quote = (quotes or {}).get(ticker)
        if quote and not isinstance(quote, StockQuote):
            quote = None
        quote_html = format_quote_chip(quote)
        quote_row = f'<div style="margin:0.35rem 0;">{quote_html}</div>' if quote_html else ""
        nct_link = inline_ctgov_link(c.get("nct_id", ""))
        st.markdown(
            f"""
<div class="list-card">
  <div class="list-card-top">
    <span class="list-ticker">{html.escape(c.get('ticker',''))}</span>
    <span class="tone-pill" style="color:{fg};background:{bg};font-size:0.65rem;">{arrow} {tone}</span>
  </div>
  {quote_row}
  <div class="list-meta">{html.escape(c.get('change_label',''))} · {when} UTC</div>
  <div class="list-meta">Phase: {html.escape(c.get('phase_from',''))} → {html.escape(c.get('phase_to',''))}</div>
  <div class="list-snippet">{html.escape(c.get('summary',''))}</div>
  <div class="list-meta" style="margin-top:0.35rem;">{score_line} · {nct_link}</div>
</div>
            """,
            unsafe_allow_html=True,
        )


def render_alert_timeline(alerts: list[dict]) -> None:
    for a in alerts:
        when = (a.get("sent_at") or "")[:16].replace("T", " ")
        msg = html.escape(a.get("message", ""))
        st.markdown(
            f"""
<div class="timeline-item">
  <div class="timeline-when">{when} UTC</div>
  <div class="timeline-title">{html.escape(a.get('ticker',''))} · {html.escape(a.get('nct_id',''))}</div>
  <div class="timeline-body">{msg}</div>
</div>
            """,
            unsafe_allow_html=True,
        )


def render_run_cards(runs: list[dict]) -> None:
    for r in runs:
        when = (r.get("started_at") or "")[:16].replace("T", " ")
        status = r.get("status", "unknown")
        status_color = "#059669" if status == "success" else "#dc2626" if status == "error" else "#64748b"
        err = f"<div class='list-meta' style='color:#dc2626;'>{html.escape(r.get('error',''))}</div>" if r.get("error") else ""
        st.markdown(
            f"""
<div class="list-card">
  <div class="list-card-top">
    <span class="list-ticker">{html.escape(r.get('sector_name',''))}</span>
    <span style="color:{status_color};font-weight:600;font-size:0.8rem;">{html.escape(status.title())}</span>
  </div>
  <div class="list-meta">{when} UTC</div>
  <div class="list-meta">
    {r.get('trials_fetched',0)} trials scanned ·
    {r.get('changes_detected',0)} changes ·
    {r.get('alerts_sent',0)} alerts sent
  </div>
  {err}
</div>
            """,
            unsafe_allow_html=True,
        )


def render_rotation_schedule(sectors: list[dict], current_index: int, now_hour: int) -> None:
    rows = []
    for offset in range(len(sectors)):
        hour = (now_hour + offset) % 24
        sector = sectors[hour % len(sectors)]
        active = "active" if offset == 0 else ""
        label = "Now" if offset == 0 else f"+{offset}h"
        rows.append(
            f'<div class="schedule-row {active}">'
            f'<span class="schedule-hour">{label}</span>'
            f'<span>{html.escape(sector["name"])}</span></div>'
        )
    st.markdown("".join(rows), unsafe_allow_html=True)


def render_metric_grid(items: list[tuple[str, str]]) -> None:
    boxes = "".join(
        f'<div class="metric-box"><div class="metric-label">{html.escape(l)}</div>'
        f'<div class="metric-value">{html.escape(v)}</div></div>'
        for l, v in items
    )
    st.markdown(f'<div class="metric-grid">{boxes}</div>', unsafe_allow_html=True)


def render_settings_rows(items: list[tuple[str, str]]) -> None:
    rows = "".join(
        f'<div class="settings-row"><span class="settings-label">{html.escape(l)}</span>'
        f'<span class="settings-value">{html.escape(v)}</span></div>'
        for l, v in items
    )
    st.markdown(rows, unsafe_allow_html=True)


def render_demo_gallery(scenarios: list, previews: dict, quotes: dict | None = None) -> None:
    from src.market.quotes import StockQuote, format_quote_chip

    cards = ['<div class="demo-grid">']
    for s in scenarios:
        prev = previews[s.id]
        alert_cls = "demo-alert-yes" if s.alert_fires else "demo-alert-no"
        alert_icon = "✉ Email would send" if s.alert_fires else "○ No email"
        score_pct = int(s.score * 100)
        quote = (quotes or {}).get(s.ticker.upper())
        if quote and not isinstance(quote, StockQuote):
            quote = None
        quote_html = format_quote_chip(quote)
        quote_block = f'<div style="margin:0.35rem 0 0.5rem;">{quote_html}</div>' if quote_html else ""
        body_html = html.escape(prev["body"]).replace(chr(10), "<br>")
        cards.append(f"""
<div class="demo-scenario">
  <div class="demo-scenario-header" style="background:{s.accent};">
    <h3>{s.icon} {html.escape(s.label)}</h3>
    <p>{html.escape(s.subtitle)}</p>
  </div>
  <div class="demo-scenario-body">
    <div style="display:flex;justify-content:space-between;align-items:center;">
      <span style="font-size:1.35rem;font-weight:800;color:#001d3d;">{html.escape(s.ticker)}</span>
      <span class="tone-pill" style="color:{TONE.get(s.analyst_tone, TONE['neutral'])[0]};background:{TONE.get(s.analyst_tone, TONE['neutral'])[1]};">{s.analyst_tone}</span>
    </div>
    {quote_block}
    <div class="list-meta" style="margin-top:0.35rem;">{html.escape(s.drug)} · {html.escape(s.change_label)}</div>
    <div class="list-meta">Phase: {html.escape(s.phase_from)} → {html.escape(s.phase_to)}</div>
    <div class="list-snippet">{html.escape(s.summary)}</div>
    <div class="demo-score-bar"><div class="demo-score-fill" style="width:{score_pct}%;background:{s.border_color};"></div></div>
    <div style="font-size:0.78rem;font-weight:700;color:#475569;">Favorability score: {score_pct}%</div>
    <div class="demo-alert-badge {alert_cls}">{alert_icon}</div>
    <div style="font-size:0.75rem;color:#64748b;margin-bottom:0.5rem;">{html.escape(s.alert_reason)}</div>
    <div class="email-mock">
      <div class="email-mock-bar">INBOX PREVIEW</div>
      <div class="email-mock-inner">
        <div class="email-from">From: Elentrx Alerts</div>
        <div class="email-subject">{html.escape(prev['subject'])}</div>
        {body_html}
      </div>
    </div>
  </div>
</div>""")
    cards.append("</div>")
    st.markdown("\n".join(cards), unsafe_allow_html=True)
