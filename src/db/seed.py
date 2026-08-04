"""Seed sample trials when the database is empty (demo / first deploy)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.config import DATA_DIR
from src.db.schema import get_connection, init_db

SEED_PATH = DATA_DIR / "seed_trials.json"


def trial_count() -> int:
    init_db()
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM trials").fetchone()
        return int(row["n"]) if row else 0


def seed_if_empty() -> int:
    """Load seed trials if DB is empty. Returns number seeded."""
    if trial_count() > 0:
        return 0
    if not SEED_PATH.exists():
        return 0

    payload = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    trials = payload.get("trials", [])
    now = datetime.now(timezone.utc).isoformat()
    init_db()

    with get_connection() as conn:
        for t in trials:
            conn.execute(
                """
                INSERT OR IGNORE INTO trials (
                    nct_id, ticker, sponsor, drug, sector_id, phase,
                    overall_status, title, last_seen_at, first_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    t["nct_id"],
                    t["ticker"],
                    t["sponsor"],
                    t["drug"],
                    t["sector_id"],
                    t["phase"],
                    t["overall_status"],
                    t["title"],
                    now,
                    now,
                ),
            )
    return len(trials)
