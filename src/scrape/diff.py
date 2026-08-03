"""Detect phase and status changes between snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.config import PHASE_ORDER
from src.db.schema import get_connection
from src.scrape.ctgov import TrialRecord


@dataclass
class PhaseChange:
    nct_id: str
    ticker: str
    sponsor: str
    drug: str | None
    sector_id: str
    old_phase: str | None
    new_phase: str | None
    old_status: str | None
    new_status: str | None
    change_type: str


def _phase_rank(phase: str | None) -> int:
    if not phase:
        return -1
    return PHASE_ORDER.get(phase, -1)


def classify_change(
    old_phase: str | None,
    new_phase: str | None,
    old_status: str | None,
    new_status: str | None,
) -> str | None:
    old_rank = _phase_rank(old_phase)
    new_rank = _phase_rank(new_phase)

    if old_phase != new_phase and new_rank > old_rank >= 0:
        return "phase_upgrade"
    if old_phase != new_phase and new_rank < old_rank:
        return "phase_downgrade"
    if old_phase != new_phase and old_rank < 0 <= new_rank:
        return "phase_assigned"
    if old_status != new_status and new_status == "COMPLETED" and old_status != "COMPLETED":
        return "status_completed"
    if old_status != new_status and new_status in {"TERMINATED", "WITHDRAWN", "SUSPENDED"}:
        return "status_negative"
    return None


def upsert_trials(records: list[TrialRecord]) -> list[PhaseChange]:
    now = datetime.now(timezone.utc).isoformat()
    changes: list[PhaseChange] = []

    with get_connection() as conn:
        for record in records:
            row = conn.execute(
                "SELECT phase, overall_status FROM trials WHERE nct_id = ?",
                (record.nct_id,),
            ).fetchone()

            if row is None:
                conn.execute(
                    """
                    INSERT INTO trials (
                        nct_id, ticker, sponsor, drug, sector_id, phase,
                        overall_status, title, last_seen_at, first_seen_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.nct_id,
                        record.ticker,
                        record.sponsor,
                        record.drug,
                        record.sector_id,
                        record.phase,
                        record.overall_status,
                        record.title,
                        now,
                        now,
                    ),
                )
                continue

            old_phase = row["phase"]
            old_status = row["overall_status"]
            change_type = classify_change(
                old_phase, record.phase, old_status, record.overall_status
            )

            conn.execute(
                """
                UPDATE trials
                SET ticker = ?, sponsor = ?, drug = ?, sector_id = ?, phase = ?,
                    overall_status = ?, title = ?, last_seen_at = ?
                WHERE nct_id = ?
                """,
                (
                    record.ticker,
                    record.sponsor,
                    record.drug,
                    record.sector_id,
                    record.phase,
                    record.overall_status,
                    record.title,
                    now,
                    record.nct_id,
                ),
            )

            if change_type:
                change = PhaseChange(
                    nct_id=record.nct_id,
                    ticker=record.ticker,
                    sponsor=record.sponsor,
                    drug=record.drug,
                    sector_id=record.sector_id,
                    old_phase=old_phase,
                    new_phase=record.phase,
                    old_status=old_status,
                    new_status=record.overall_status,
                    change_type=change_type,
                )
                changes.append(change)
                conn.execute(
                    """
                    INSERT INTO phase_changes (
                        nct_id, ticker, sponsor, drug, sector_id,
                        old_phase, new_phase, old_status, new_status,
                        change_type, detected_at, processed
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                    """,
                    (
                        change.nct_id,
                        change.ticker,
                        change.sponsor,
                        change.drug,
                        change.sector_id,
                        change.old_phase,
                        change.new_phase,
                        change.old_status,
                        change.new_status,
                        change.change_type,
                        now,
                    ),
                )

    return changes
