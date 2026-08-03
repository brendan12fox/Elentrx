"""OpenAI Responses API with built-in web search."""

from __future__ import annotations

import json
import os
import re
from datetime import date

from openai import OpenAI

from src.config import OPENAI_MODEL, OPENAI_SEARCH_MODEL
from src.scrape.diff import PhaseChange

SYSTEM_PROMPT = """You are a biotech equity research analyst with web search access.
Search for news and filings about the clinical trial / company described.
Produce a JSON object with:
- summary: 2-3 sentence investment-relevant summary
- catalysts: list of near-term positive catalysts
- safety_signals: list of safety concerns if any
- endpoints: list of key endpoints or readouts mentioned
- analyst_tone: one of bullish, neutral, bearish
- risk_flags: list of risk factors
- sources_found: integer count of distinct news sources you used

Be factual. If evidence is thin, say so. Return valid JSON only."""


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            return json.loads(match.group())
        return {"summary": text[:500], "analyst_tone": "neutral", "sources_found": 0}


def _count_search_calls(response) -> int:
    count = 0
    for item in getattr(response, "output", []) or []:
        if getattr(item, "type", "") == "web_search_call":
            count += 1
    return count


def _build_prompt(change: PhaseChange, cutoff: date, lookback_days: int) -> str:
    start = cutoff.isoformat()
    return f"""Research this clinical trial catalyst for stock {change.ticker}.

Trial context:
- NCT ID: {change.nct_id}
- Sponsor: {change.sponsor}
- Drug/intervention: {change.drug or 'Unknown'}
- Change type: {change.change_type}
- Phase: {change.old_phase or 'NA'} -> {change.new_phase or 'NA'}
- Status: {change.old_status or 'NA'} -> {change.new_status or 'NA'}

Search instructions:
- Find news, press releases, SEC filings, and analyst coverage about this drug/trial/company.
- INFORMATION CUTOFF: only use sources from the {lookback_days} days ending on {start}.
- Do not use information published after {start}.
- Search queries should include: {change.ticker}, {change.sponsor}, {change.drug or 'pipeline'}, clinical trial, FDA.

Return JSON only."""


def analyze_with_openai_web_search(
    change: PhaseChange,
    as_of_date: date | None = None,
    lookback_days: int = 30,
) -> dict:
    from datetime import date as date_cls

    cutoff = as_of_date or date_cls.today()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {
            "summary": "LLM analysis unavailable (OPENAI_API_KEY not set).",
            "catalysts": [],
            "safety_signals": [],
            "endpoints": [],
            "analyst_tone": "neutral",
            "risk_flags": ["missing_openai_key"],
            "raw_json": {"error": "missing_openai_key"},
            "sources_found": 0,
        }

    client = OpenAI(api_key=api_key)
    model = OPENAI_SEARCH_MODEL or OPENAI_MODEL
    user_prompt = _build_prompt(change, cutoff, lookback_days)

    try:
        response = client.responses.create(
            model=model,
            tools=[{"type": "web_search", "search_context_size": "medium"}],
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
    except Exception as exc:
        # Fallback model if configured model lacks web_search support
        if model != "gpt-4o":
            response = client.responses.create(
                model="gpt-4o",
                tools=[{"type": "web_search", "search_context_size": "medium"}],
                input=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            )
        else:
            return {
                "summary": f"OpenAI web search failed: {exc}",
                "catalysts": [],
                "safety_signals": [],
                "endpoints": [],
                "analyst_tone": "neutral",
                "risk_flags": ["openai_web_search_error"],
                "raw_json": {"error": str(exc)},
                "sources_found": 0,
            }

    payload = _extract_json(response.output_text or "{}")
    search_calls = _count_search_calls(response)
    sources_found = int(payload.get("sources_found") or search_calls or 0)

    raw_json = {
        **payload,
        "search_engine": "openai_web_search",
        "search_calls": search_calls,
        "sources_found": sources_found,
        "model": model,
        "cutoff_date": cutoff.isoformat(),
    }

    return {
        "summary": payload.get("summary", ""),
        "catalysts": payload.get("catalysts", []) or [],
        "safety_signals": payload.get("safety_signals", []) or [],
        "endpoints": payload.get("endpoints", []) or [],
        "analyst_tone": payload.get("analyst_tone", "neutral"),
        "risk_flags": payload.get("risk_flags", []) or [],
        "raw_json": raw_json,
        "sources_found": sources_found,
    }


def sources_found_from_brief(raw_json: dict) -> int:
    return int(raw_json.get("sources_found") or raw_json.get("search_calls") or 0)
