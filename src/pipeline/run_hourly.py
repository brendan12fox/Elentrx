"""Hourly pipeline entrypoint."""

from __future__ import annotations

import argparse
import sys
import traceback
from datetime import datetime, timezone

from src.alert.sms import alert_if_new
from src.config import get_sector_for_hour, load_sectors
from src.db.schema import get_connection, init_db
from src.ml.infer import save_score, score_change
from src.research.llm_agent import analyze_phase_change, get_latest_phase_change_id, save_brief
from src.scrape.ctgov import ClinicalTrialsClient
from src.scrape.diff import upsert_trials


def run_hourly(hour_utc: int | None = None, dry_run: bool = False) -> dict:
    init_db()
    sector, sector_index = get_sector_for_hour(hour_utc)
    started_at = datetime.now(timezone.utc).isoformat()

    stats = {
        "sector_id": sector["id"],
        "sector_name": sector["name"],
        "sector_index": sector_index,
        "trials_fetched": 0,
        "trials_matched": 0,
        "changes_detected": 0,
        "alerts_sent": 0,
        "status": "running",
        "error": None,
    }

    run_id: int | None = None
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO run_log (sector_id, sector_name, started_at, status)
            VALUES (?, ?, ?, 'running')
            """,
            (sector["id"], sector["name"], started_at),
        )
        run_id = int(cursor.lastrowid)

    try:
        client = ClinicalTrialsClient()
        records = client.fetch_sector_studies(sector)
        stats["trials_fetched"] = len(records)
        stats["trials_matched"] = len(records)

        changes = upsert_trials(records)
        stats["changes_detected"] = len(changes)

        for change in changes:
            brief = analyze_phase_change(change)
            with get_connection() as conn:
                phase_change_id = get_latest_phase_change_id(conn, change)
            if phase_change_id is None:
                continue

            save_brief(phase_change_id, brief)
            result = score_change(change, brief)

            save_score(phase_change_id, result)

            if result.favorable and not dry_run:
                sent = alert_if_new(
                    phase_change_id=phase_change_id,
                    ticker=change.ticker,
                    nct_id=change.nct_id,
                    old_phase=change.old_phase,
                    new_phase=change.new_phase,
                    probability=result.probability,
                    summary=brief.summary,
                )
                if sent:
                    stats["alerts_sent"] += 1

            with get_connection() as conn:
                conn.execute(
                    "UPDATE phase_changes SET processed = 1 WHERE id = ?",
                    (phase_change_id,),
                )

        stats["status"] = "success"
    except Exception as exc:
        stats["status"] = "error"
        stats["error"] = str(exc)
        traceback.print_exc()
    finally:
        finished_at = datetime.now(timezone.utc).isoformat()
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE run_log
                SET finished_at = ?, trials_fetched = ?, trials_matched = ?,
                    changes_detected = ?, alerts_sent = ?, status = ?, error = ?
                WHERE id = ?
                """,
                (
                    finished_at,
                    stats["trials_fetched"],
                    stats["trials_matched"],
                    stats["changes_detected"],
                    stats["alerts_sent"],
                    stats["status"],
                    stats["error"],
                    run_id,
                ),
            )

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Run hourly clinical trial scraper")
    parser.add_argument("--hour-utc", type=int, default=None, help="Override UTC hour for sector rotation")
    parser.add_argument("--dry-run", action="store_true", help="Skip SMS alerts")
    parser.add_argument("--list-sectors", action="store_true", help="Print sector rotation schedule")
    args = parser.parse_args()

    if args.list_sectors:
        sectors = load_sectors()
        for idx, sector in enumerate(sectors):
            print(f"{idx}: {sector['name']} ({sector['id']})")
        return

    stats = run_hourly(hour_utc=args.hour_utc, dry_run=args.dry_run)
    print(stats)
    if stats["status"] == "error":
        sys.exit(1)


if __name__ == "__main__":
    main()
