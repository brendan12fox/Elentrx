"""Application configuration and paths."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()


def hydrate_streamlit_secrets() -> None:
    """Mirror Streamlit Cloud secrets into os.environ (local .env still wins)."""
    try:
        import streamlit as st

        for key, value in st.secrets.items():
            if isinstance(value, (str, int, float, bool)):
                os.environ.setdefault(str(key), str(value))
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
MODELS_DIR = ROOT / "models"

DB_PATH = Path(os.getenv("SNAPSHOT_DB_PATH", str(DATA_DIR / "snapshots.db")))
SPONSOR_MAP_PATH = DATA_DIR / "sponsor_tickers.csv"
SECTORS_PATH = CONFIG_DIR / "sectors.yaml"
MODEL_PATH = MODELS_DIR / "favorability.pkl"

FAVORABILITY_THRESHOLD = float(os.getenv("FAVORABILITY_THRESHOLD", "0.65"))
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_SEARCH_MODEL = os.getenv("OPENAI_SEARCH_MODEL", "gpt-4o")

# News: production = free RSS/GDELT only; training = Serper (budget-limited) + free fill
NEWS_MODE_PRODUCTION = "production"
NEWS_MODE_TRAINING = "training"
SERPER_MONTHLY_LIMIT = int(os.getenv("SERPER_MONTHLY_LIMIT", "2500"))
CTGOV_BASE_URL = "https://clinicaltrials.gov/api/v2"
CTGOV_PAGE_SIZE = int(os.getenv("CTGOV_PAGE_SIZE", "100"))
CTGOV_MAX_PAGES = int(os.getenv("CTGOV_MAX_PAGES", "20"))
CTGOV_REQUEST_DELAY = float(os.getenv("CTGOV_REQUEST_DELAY", "0.15"))

# Phase ordering for upgrade detection
PHASE_ORDER = {
    "NA": 0,
    "EARLY_PHASE1": 1,
    "PHASE1": 2,
    "PHASE2": 3,
    "PHASE3": 4,
    "PHASE4": 5,
}


def load_sectors() -> list[dict]:
    with SECTORS_PATH.open(encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    return payload["sectors"]


def get_sector_for_hour(hour_utc: int | None = None) -> tuple[dict, int]:
    """Return (sector, index) for the given UTC hour."""
    from datetime import datetime, timezone

    if hour_utc is None:
        hour_utc = datetime.now(timezone.utc).hour
    sectors = load_sectors()
    index = hour_utc % len(sectors)
    return sectors[index], index


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
