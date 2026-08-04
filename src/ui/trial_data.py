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


def fetch_trials_enriched(limit: int = 80, *, active_first: bool = True) -> list[dict]:
    """Trials across all sectors — read only. Prefer active mid/late-phase when set."""
    init_db()
    order_sql = (
        """
        ORDER BY
          CASE WHEN t.phase IN ('PHASE2', 'PHASE3', 'PHASE4') THEN 0 ELSE 1 END,
          CASE WHEN t.overall_status IN (
              'RECRUITING', 'ACTIVE_NOT_RECRUITING', 'ENROLLING_BY_INVITATION'
          ) THEN 0 ELSE 1 END,
          t.last_seen_at DESC
        """
        if active_first
        else "ORDER BY t.last_seen_at DESC"
    )
    with get_connection() as conn:
        rows = conn.execute(
            f"""
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
            {order_sql}
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


def fetch_trial_sector_counts() -> dict[str, int]:
    """How many trials we have per sector."""
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT sector_id, COUNT(*) AS n FROM trials GROUP BY sector_id"
        ).fetchall()
    return {str(r["sector_id"] or "other"): int(r["n"]) for r in rows}


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


def build_preview_digest(max_trials: int = 60) -> dict:
    """Instant cross-sector digest from DB — no API calls."""
    focus, _ = get_sector_for_hour()
    trials = fetch_trials_enriched(limit=max_trials, active_first=True)
    changes = fetch_phase_changes(limit=3)
    sector_counts = fetch_trial_sector_counts()
    sectors_with_data = sum(1 for n in sector_counts.values() if n > 0)

    if changes:
        pulse = (
            f"Tracking {len(trials)} trials across {sectors_with_data} sectors. "
            f"Hourly scan focus: {focus['name']}. "
            f"Latest activity: {changes[0]['ticker']} — {changes[0]['change_label'].lower()}."
        )
    elif trials:
        pulse = (
            f"Tracking {len(trials)} publicly sponsored trials across {sectors_with_data} sectors. "
            f"Hourly scraper is focused on {focus['name']} this hour."
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
                "sector_id": t.get("sector_id"),
                "sector": t.get("sector"),
                "preview": True,
            }
        )

    return {
        "cache_key": "preview",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sector_id": focus["id"],
        "sector_name": focus["name"],
        "focus_sector_name": focus["name"],
        "market_pulse": pulse,
        "trials": card_trials,
        "trial_count": len(card_trials),
        "sectors_covered": sectors_with_data,
        "preview": True,
        "all_sectors": True,
    }


def merge_digest_with_preview(digest: dict | None) -> tuple[dict, bool]:
    """Always show a cross-sector catalogue; overlay AI digest enrichment when available."""
    catalogue = build_preview_digest(max_trials=60)
    if not digest or not digest.get("trials"):
        return catalogue, True

    by_nct = {t.get("nct_id"): t for t in digest.get("trials", []) if t.get("nct_id")}
    merged_trials = []
    seen: set[str] = set()

    # Put digest (enriched) cards first, then fill with the rest of the catalogue.
    for t in digest["trials"]:
        nct = t.get("nct_id")
        if not nct or nct in seen:
            continue
        seen.add(nct)
        base = next((c for c in catalogue["trials"] if c.get("nct_id") == nct), {})
        merged = {**base, **t, "preview": False}
        if not merged.get("sector"):
            merged["sector"] = base.get("sector") or sector_name(merged.get("sector_id"))
        merged_trials.append(merged)

    for t in catalogue["trials"]:
        nct = t.get("nct_id")
        if not nct or nct in seen:
            continue
        seen.add(nct)
        merged_trials.append(t)

    focus, _ = get_sector_for_hour()
    sectors_covered = catalogue.get("sectors_covered") or len(
        {t.get("sector_id") for t in merged_trials if t.get("sector_id")}
    )
    pulse = digest.get("market_pulse") or catalogue["market_pulse"]
    if "Hourly" not in pulse and "hourly" not in pulse:
        pulse = f"{pulse} Hourly scan focus: {focus['name']}."

    return {
        "cache_key": digest.get("cache_key") or catalogue["cache_key"],
        "generated_at": digest.get("generated_at") or catalogue["generated_at"],
        "sector_id": focus["id"],
        "sector_name": focus["name"],
        "focus_sector_name": focus["name"],
        "market_pulse": pulse,
        "trials": merged_trials[:60],
        "trial_count": min(len(merged_trials), 60),
        "sectors_covered": sectors_covered,
        "preview": False,
        "all_sectors": True,
    }, False
