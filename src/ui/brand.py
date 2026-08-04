"""Elentrx brand assets — logo and color tokens from elentrx.png."""

from __future__ import annotations

import re
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
LOGO_PATH = ROOT / "assets" / "elentrx.png"
LOGO_UI_PATH = ROOT / "assets" / "elentrx-ui.png"

# Official palette
NAVY = "#001D3D"
TEAL = "#00C4A7"
WHITE = "#FFFFFF"
MUTED = "#4A6278"
SURFACE = "#F5F8FA"

BRAND_NAME = "Elentrx"
TAGLINE = "Clinical trial intelligence"

SIDEBAR_LOGO_WIDTH = 152
AUTH_LOGO_WIDTH = 240

_NCT_RE = re.compile(r"^NCT(\d{8})$")


def is_valid_nct_id(nct_id: str) -> bool:
    """True for real CT.gov IDs — rejects placeholders like NCT00000001."""
    match = _NCT_RE.fullmatch((nct_id or "").strip().upper())
    if not match:
        return False
    return int(match.group(1)) >= 10_000


def ctgov_study_url(nct_id: str) -> str:
    nct = (nct_id or "").strip().upper()
    if not is_valid_nct_id(nct):
        return ""
    return f"https://clinicaltrials.gov/study/{nct}"


def render_sidebar_logo() -> None:
    # White pill so the transparent logo stays readable on navy sidebar.
    st.markdown(
        """
<style>
[data-testid="stSidebar"] [data-testid="stImage"] {
    background: #ffffff !important;
    border-radius: 14px !important;
    padding: 0.55rem 0.65rem !important;
    margin-bottom: 0.45rem !important;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.18) !important;
    width: fit-content !important;
    max-width: 100% !important;
}
[data-testid="stSidebar"] [data-testid="stImage"] img {
    width: auto !important;
    max-width: 100% !important;
    height: auto !important;
    display: block !important;
}
</style>
        """,
        unsafe_allow_html=True,
    )
    st.image(str(LOGO_UI_PATH), width=SIDEBAR_LOGO_WIDTH)
    st.markdown(
        f'<p class="brand-sub" style="font-size:0.72rem;color:#7eb8aa;text-transform:uppercase;'
        f'letter-spacing:0.08em;margin-bottom:1.5rem;">{TAGLINE}</p>',
        unsafe_allow_html=True,
    )


def render_auth_logo() -> None:
    _, col, _ = st.columns([1, 1.4, 1])
    with col:
        st.image(str(LOGO_UI_PATH), width=AUTH_LOGO_WIDTH)
        st.markdown(
            f'<p class="auth-tagline">{TAGLINE}</p>',
            unsafe_allow_html=True,
        )
