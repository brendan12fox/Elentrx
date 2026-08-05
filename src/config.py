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


def _env(name: str, default: str = "") -> str:
    """Read env var; treat missing/blank (common in Actions) as default."""
    value = os.getenv(name)
    if value is None or not str(value).strip():
        return default
    return str(value).strip()


def _env_float(name: str, default: float) -> float:
    raw = _env(name, "")
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = _env(name, "")
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
MODELS_DIR = ROOT / "models"


def _is_streamlit_cloud() -> bool:
    """Heuristic for Streamlit Community Cloud (read-only app dir)."""
    if os.getenv("SNAPSHOT_DB_PATH"):
        return False
    if os.getenv("USER") == "appuser":
        return True
    hostname = os.getenv("HOSTNAME", "").lower()
    if "streamlit" in hostname:
        return True
    return Path("/home/appuser/.streamlit").exists()


def _resolve_db_path() -> Path:
    explicit = _env("SNAPSHOT_DB_PATH", "")
    if explicit:
        return Path(explicit)
    if _is_streamlit_cloud():
        cloud_dir = Path("/tmp/elentrx")
        cloud_dir.mkdir(parents=True, exist_ok=True)
        return cloud_dir / "snapshots.db"
    default = DATA_DIR / "snapshots.db"
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        probe = DATA_DIR / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return default
    except OSError:
        fallback = Path("/tmp/elentrx")
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback / "snapshots.db"


DB_PATH = _resolve_db_path()
SPONSOR_MAP_PATH = DATA_DIR / "sponsor_tickers.csv"
SECTORS_PATH = CONFIG_DIR / "sectors.yaml"
MODEL_PATH = MODELS_DIR / "favorability.pkl"

FAVORABILITY_THRESHOLD = _env_float("FAVORABILITY_THRESHOLD", 0.65)
OPENAI_MODEL = _env("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_SEARCH_MODEL = _env("OPENAI_SEARCH_MODEL", "gpt-4o")

# News: production = free RSS/GDELT only; training = Serper (budget-limited) + free fill
NEWS_MODE_PRODUCTION = "production"
NEWS_MODE_TRAINING = "training"
SERPER_MONTHLY_LIMIT = _env_int("SERPER_MONTHLY_LIMIT", 2500)
CTGOV_BASE_URL = "https://clinicaltrials.gov/api/v2"
CTGOV_PAGE_SIZE = _env_int("CTGOV_PAGE_SIZE", 100)
CTGOV_MAX_PAGES = _env_int("CTGOV_MAX_PAGES", 20)
CTGOV_REQUEST_DELAY = _env_float("CTGOV_REQUEST_DELAY", 0.15)

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
    for path in (DATA_DIR, MODELS_DIR, DB_PATH.parent):
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
