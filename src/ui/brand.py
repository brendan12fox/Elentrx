"""Elentrx brand assets — logo and color tokens from elentrx.png."""

from __future__ import annotations

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


def ctgov_study_url(nct_id: str) -> str:
    nct = (nct_id or "").strip().upper()
    if not nct.startswith("NCT"):
        return ""
    return f"https://clinicaltrials.gov/study/{nct}"


def render_sidebar_logo() -> None:
    st.image(str(LOGO_UI_PATH), width=SIDEBAR_LOGO_WIDTH)
    st.markdown(
        f'<p class="brand-sub">{TAGLINE}</p>',
        unsafe_allow_html=True,
    )


def render_auth_logo() -> None:
    _, col, _ = st.columns([1, 1.4, 1])
    with col:
        # Full-res source downscales crisply on retina displays.
        st.image(str(LOGO_PATH), width=AUTH_LOGO_WIDTH)
        st.markdown(
            f'<p class="auth-tagline">{TAGLINE}</p>',
            unsafe_allow_html=True,
        )
