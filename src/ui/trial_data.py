"""Read trial snapshots and build instant preview digests (no LLM)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from src.config import get_sector_for_hour, load_sectors
from src.db.schema import get_connection, init_db

PHASE_LABELS = {
    "PHASE1": "Phase 1",
    "PHASE2": "Phase 2",
    "PHASE3": "Phase 3",
    "PHASE4": "Phase 4",
    "EARLY_PHASE1": "Early Phase 1",
    "NA": "Not applicable",
}

STATUS_LABELS = {
    "RECRUITING": "Recruiting",
    "ACTIVE_NOT_RECRUITING": "Active, not recruiting",
    "COMPLETED": "Completed",
    "TERMINATED": "Terminated",
    "WITHDRAWN": "Withdrawn",
    "SUSPENDED": "Suspended",
    "ENROLLING_BY_INVITATION": "Enrolling by invitation",
    "NOT_YET_RECRUITING": "Not yet recruiting",
}

CHANGE_LABELS = {
    "phase_upgrade": "Phase advanced",
    "phase_downgrade": "Phase stepped back",
    "phase_assigned": "Phase assigned",
    "status_completed": "Trial completed",
    "status_negative": "Trial halted",
    "status_change": "Status updated",
}


def human_phase(phase: str | None) -> str:
    if not phase:
        return "Unknown phase"
    return PHASE_LABELS.get(phase, phase.replace("_", " ").title())


def human_status(status: str | None) -> str:
    if not status:
        return "Unknown status"
    return STATUS_LABELS.get(status, status.replace("_", " ").title())


def human_change(change_type: str | None) -> str:
    if not change_type:
        return "Update"
    return CHANGE_LABELS.get(change_type, change_type.replace("_", " ").title())


def sector_name(sector_id: str | None) -> str:
    if not sector_id:
        return "General"
    for s in load_sectors():
        if s["id"] == sector_id:
            return s["name"]
    return sector_id.replace("_", " ").title()


def fetch_trials_enriched(limit: int = 24) -> list[dict]:
    """Trials with optional latest brief and score — read only."""
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                t.nct_id, t.ticker, t.sponsor, t.drug, t.sector_id,
                t.phase, t.overall_status, t.title, t.last_seen_at,
                (
                    SELECT rb.summary FROM phase_changes pc
                    JOIN research_briefs rb ON rb.phase_change_id = pc.id
                    WHERE pc.nct_id = t.nct_id
                    ORDER BY pc.detected_at DESC LIMIT 1
                ) AS brief_summary,
                (
                    SELECT rb.analyst_tone FROM phase_changes pc
                    JOIN research_briefs rb ON rb.phase_change_id = pc.id
                    WHERE pc.nct_id = t.nct_id
                    ORDER BY pc.detected_at DESC LIMIT 1
                ) AS analyst_tone,
                (
                    SELECT cs.probability FROM phase_changes pc
                    JOIN classifier_scores cs ON cs.phase_change_id = pc.id
                    WHERE pc.nct_id = t.nct_id
                    ORDER BY pc.detected_at DESC LIMIT 1
                ) AS score
            FROM trials t
            ORDER BY t.last_seen_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    out: list[dict] = []
    for row in rows:
        title = row["title"] or ""
        brief = row["brief_summary"] or (
            title[:220] + "…" if len(title) > 220 else title
        ) or f"{row['sponsor']} study for {row['drug'] or 'pipeline candidate'}."
        out.append(
            {
                "nct_id": row["nct_id"],
                "ticker": row["ticker"],
                "sponsor": row["sponsor"],
                "drug": row["drug"],
                "sector_id": row["sector_id"],
                "sector": sector_name(row["sector_id"]),
                "phase": row["phase"],
                "phase_label": human_phase(row["phase"]),
                "status": row["overall_status"],
                "status_label": human_status(row["overall_status"]),
                "title": title,
                "last_seen_at": row["last_seen_at"],
                "brief": brief,
                "headline": _headline_from_trial(row["ticker"], row["drug"], row["phase"]),
                "analyst_tone": row["analyst_tone"] or "neutral",
                "score": float(row["score"]) if row["score"] is not None else None,
                "watch_reason": f"{human_phase(row['phase'])} · {sector_name(row['sector_id'])}",
                "news": [],
                "catalysts": [],
                "preview": True,
            }
        )
    return out


def fetch_phase_changes(limit: int = 20) -> list[dict]:
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                pc.detected_at, pc.ticker, pc.nct_id, pc.sponsor, pc.drug,
                pc.change_type, pc.old_phase, pc.new_phase,
                pc.old_status, pc.new_status,
                rb.summary, rb.analyst_tone,
                cs.probability, cs.favorable
            FROM phase_changes pc
            LEFT JOIN research_briefs rb ON rb.phase_change_id = pc.id
            LEFT JOIN classifier_scores cs ON cs.phase_change_id = pc.id
            ORDER BY pc.detected_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [
        {
            "detected_at": r["detected_at"],
            "ticker": r["ticker"],
            "nct_id": r["nct_id"],
            "sponsor": r["sponsor"],
            "drug": r["drug"],
            "change_label": human_change(r["change_type"]),
            "change_type": r["change_type"],
            "phase_from": human_phase(r["old_phase"]),
            "phase_to": human_phase(r["new_phase"]),
            "status_from": human_status(r["old_status"]),
            "status_to": human_status(r["new_status"]),
            "summary": r["summary"] or "Research brief pending.",
            "analyst_tone": r["analyst_tone"] or "neutral",
            "score": float(r["probability"]) if r["probability"] is not None else None,
            "favorable": bool(r["favorable"]) if r["favorable"] is not None else None,
        }
        for r in rows
    ]


def fetch_alerts(limit: int = 30) -> list[dict]:
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT sent_at, ticker, nct_id, message
            FROM alerts ORDER BY sent_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def fetch_runs(limit: int = 20) -> list[dict]:
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT started_at, finished_at, sector_name, trials_fetched,
                   changes_detected, alerts_sent, status, error
            FROM run_log ORDER BY started_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def _headline_from_trial(ticker: str, drug: str | None, phase: str | None) -> str:
    drug_bit = drug or "pipeline asset"
    return f"{ticker} · {drug_bit} ({human_phase(phase)})"


def build_preview_digest(max_trials: int = 8) -> dict:
    """Instant digest from DB — no API calls."""
    sector, _ = get_sector_for_hour()
    trials = fetch_trials_enriched(limit=max_trials)
    changes = fetch_phase_changes(limit=3)

    if changes:
        pulse = (
            f"Tracking {len(trials)} public-company trials in {sector['name']}. "
            f"Latest activity: {changes[0]['ticker']} — {changes[0]['change_label'].lower()}."
        )
    elif trials:
        pulse = (
            f"Tracking {len(trials)} publicly sponsored trials in {sector['name']}. "
            "Full AI digest refreshes daily once the pipeline runs."
        )
    else:
        pulse = "Trial snapshot loading — check back after the hourly scraper runs."

    card_trials = []
    for t in trials[:max_trials]:
        card_trials.append(
            {
                "nct_id": t["nct_id"],
                "ticker": t["ticker"],
                "headline": t["headline"],
                "brief": t["brief"],
                "analyst_tone": t["analyst_tone"],
                "phase": t["phase"],
                "watch_reason": t["watch_reason"],
                "score": t["score"],
                "news": t["news"],
                "catalysts": t["catalysts"],
                "preview": True,
            }
        )

    return {
        "cache_key": "preview",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sector_id": sector["id"],
        "sector_name": sector["name"],
        "market_pulse": pulse,
        "trials": card_trials,
        "trial_count": len(card_trials),
        "preview": True,
    }


def merge_digest_with_preview(digest: dict | None) -> tuple[dict, bool]:
    """Use full digest if it has trials; otherwise fall back to preview."""
    if digest and digest.get("trials"):
        return digest, False
    preview = build_preview_digest()
    if digest:
        preview["market_pulse"] = digest.get("market_pulse") or preview["market_pulse"]
        preview["sector_name"] = digest.get("sector_name") or preview["sector_name"]
    return preview, True
