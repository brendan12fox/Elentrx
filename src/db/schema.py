"""SQLite schema and helpers."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from src.config import DB_PATH, ensure_dirs

SCHEMA = """
CREATE TABLE IF NOT EXISTS trials (
    nct_id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    sponsor TEXT NOT NULL,
    drug TEXT,
    sector_id TEXT NOT NULL,
    phase TEXT,
    overall_status TEXT,
    title TEXT,
    last_seen_at TEXT NOT NULL,
    first_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS phase_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nct_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    sponsor TEXT NOT NULL,
    drug TEXT,
    sector_id TEXT NOT NULL,
    old_phase TEXT,
    new_phase TEXT,
    old_status TEXT,
    new_status TEXT,
    change_type TEXT NOT NULL,
    detected_at TEXT NOT NULL,
    processed INTEGER DEFAULT 0,
    FOREIGN KEY (nct_id) REFERENCES trials(nct_id)
);

CREATE TABLE IF NOT EXISTS research_briefs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phase_change_id INTEGER NOT NULL,
    summary TEXT,
    catalysts TEXT,
    safety_signals TEXT,
    endpoints TEXT,
    analyst_tone TEXT,
    risk_flags TEXT,
    raw_json TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (phase_change_id) REFERENCES phase_changes(id)
);

CREATE TABLE IF NOT EXISTS classifier_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phase_change_id INTEGER NOT NULL,
    probability REAL NOT NULL,
    favorable INTEGER NOT NULL,
    features_json TEXT,
    scored_at TEXT NOT NULL,
    FOREIGN KEY (phase_change_id) REFERENCES phase_changes(id)
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phase_change_id INTEGER NOT NULL,
    ticker TEXT NOT NULL,
    nct_id TEXT NOT NULL,
    message TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    dedupe_key TEXT UNIQUE NOT NULL,
    FOREIGN KEY (phase_change_id) REFERENCES phase_changes(id)
);

CREATE TABLE IF NOT EXISTS run_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sector_id TEXT NOT NULL,
    sector_name TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    trials_fetched INTEGER DEFAULT 0,
    trials_matched INTEGER DEFAULT 0,
    changes_detected INTEGER DEFAULT 0,
    alerts_sent INTEGER DEFAULT 0,
    status TEXT DEFAULT 'running',
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_trials_sector ON trials(sector_id);
CREATE INDEX IF NOT EXISTS idx_trials_ticker ON trials(ticker);
CREATE INDEX IF NOT EXISTS idx_phase_changes_detected ON phase_changes(detected_at);
CREATE INDEX IF NOT EXISTS idx_alerts_sent ON alerts(sent_at);
"""


def init_db(db_path: Path | None = None) -> None:
    ensure_dirs()
    path = db_path or DB_PATH
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA)
        conn.commit()


@contextmanager
def get_connection(db_path: Path | None = None):
    ensure_dirs()
    path = db_path or DB_PATH
    init_db(path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
