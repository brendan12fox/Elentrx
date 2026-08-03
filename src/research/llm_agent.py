"""LLM research agent for phase changes."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone

from src.db.schema import get_connection
from src.research.openai_search import analyze_with_openai_web_search
from src.scrape.diff import PhaseChange


@dataclass
class ResearchBrief:
    summary: str
    catalysts: list[str]
    safety_signals: list[str]
    endpoints: list[str]
    analyst_tone: str
    risk_flags: list[str]
    raw_json: dict


def analyze_phase_change(
    change: PhaseChange,
    as_of_date: date | None = None,
    lookback_days: int = 30,
    news_mode: str | None = None,  # kept for API compat; ignored
) -> ResearchBrief:
    """Research a phase change using OpenAI Responses API + web_search tool."""
    result = analyze_with_openai_web_search(change, as_of_date=as_of_date, lookback_days=lookback_days)
    return ResearchBrief(
        summary=result["summary"],
        catalysts=result["catalysts"],
        safety_signals=result["safety_signals"],
        endpoints=result["endpoints"],
        analyst_tone=result["analyst_tone"],
        risk_flags=result["risk_flags"],
        raw_json=result["raw_json"],
    )


def save_brief(phase_change_id: int, brief: ResearchBrief) -> int:
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO research_briefs (
                phase_change_id, summary, catalysts, safety_signals,
                endpoints, analyst_tone, risk_flags, raw_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                phase_change_id,
                brief.summary,
                json.dumps(brief.catalysts),
                json.dumps(brief.safety_signals),
                json.dumps(brief.endpoints),
                brief.analyst_tone,
                json.dumps(brief.risk_flags),
                json.dumps(brief.raw_json),
                now,
            ),
        )
        return int(cursor.lastrowid)


def get_latest_phase_change_id(conn, change: PhaseChange) -> int | None:
    row = conn.execute(
        """
        SELECT id FROM phase_changes
        WHERE nct_id = ? AND old_phase IS ? AND new_phase IS ? AND change_type = ?
        ORDER BY id DESC LIMIT 1
        """,
        (change.nct_id, change.old_phase, change.new_phase, change.change_type),
    ).fetchone()
    return int(row["id"]) if row else None
