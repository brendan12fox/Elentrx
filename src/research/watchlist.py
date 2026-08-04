"""Shared daily watchlist digest — one cache for all users."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from openai import OpenAI

from src.config import DATA_DIR, OPENAI_MODEL, get_sector_for_hour
from src.db.schema import get_connection, init_db
from src.research.search import build_fallback_queries, search_news

WATCHLIST_JSON_PATH = DATA_DIR / "watchlist_digest.json"
CACHE_TTL_HOURS = int(os.getenv("WATCHLIST_CACHE_HOURS", "24"))
MAX_WATCH_TRIALS = int(os.getenv("WATCHLIST_MAX_TRIALS", "10"))
NEWS_PER_TRIAL = 4


@dataclass
class WatchTrial:
    nct_id: str
    ticker: str
    sponsor: str
    drug: str | None
    sector_id: str
    phase: str | None
    status: str | None
    title: str | None
    change_type: str | None
    watch_reason: str
    score: float | None = None
    detected_at: str | None = None


def _cache_key(for_date: date | None = None) -> str:
    return (for_date or date.today()).isoformat()


def _tone_css(tone: str) -> str:
    return {"bullish": "#22c55e", "bearish": "#ef4444", "neutral": "#94a3b8"}.get(
        tone.lower(), "#94a3b8"
    )


def fetch_watch_trials(limit: int = MAX_WATCH_TRIALS) -> list[WatchTrial]:
    """Priority: recent phase changes, then active phase 2/3 in current sector."""
    init_db()
    sector, _ = get_sector_for_hour()
    sector_id = sector["id"]
    seen: set[str] = set()
    trials: list[WatchTrial] = []

    with get_connection() as conn:
        change_rows = conn.execute(
            """
            SELECT
                pc.nct_id, pc.ticker, pc.sponsor, pc.drug, pc.sector_id,
                pc.new_phase AS phase, pc.new_status AS status,
                pc.change_type, pc.detected_at,
                t.title,
                cs.probability AS score
            FROM phase_changes pc
            LEFT JOIN trials t ON t.nct_id = pc.nct_id
            LEFT JOIN classifier_scores cs ON cs.phase_change_id = pc.id
            ORDER BY pc.detected_at DESC
            LIMIT ?
            """,
            (limit * 2,),
        ).fetchall()

        for row in change_rows:
            if row["nct_id"] in seen:
                continue
            seen.add(row["nct_id"])
            reason = (row["change_type"] or "update").replace("_", " ").title()
            trials.append(
                WatchTrial(
                    nct_id=row["nct_id"],
                    ticker=row["ticker"],
                    sponsor=row["sponsor"],
                    drug=row["drug"],
                    sector_id=row["sector_id"],
                    phase=row["phase"],
                    status=row["status"],
                    title=row["title"],
                    change_type=row["change_type"],
                    watch_reason=f"Recent {reason}",
                    score=float(row["score"]) if row["score"] is not None else None,
                    detected_at=row["detected_at"],
                )
            )
            if len(trials) >= limit:
                return trials[:limit]

        active_rows = conn.execute(
            """
            SELECT nct_id, ticker, sponsor, drug, sector_id, phase,
                   overall_status AS status, title, last_seen_at
            FROM trials
            WHERE sector_id = ?
              AND phase IN ('PHASE2', 'PHASE3', 'PHASE4')
              AND overall_status IN (
                  'RECRUITING', 'ACTIVE_NOT_RECRUITING', 'ENROLLING_BY_INVITATION'
              )
            ORDER BY last_seen_at DESC
            LIMIT ?
            """,
            (sector_id, limit * 2),
        ).fetchall()

        for row in active_rows:
            if row["nct_id"] in seen:
                continue
            seen.add(row["nct_id"])
            trials.append(
                WatchTrial(
                    nct_id=row["nct_id"],
                    ticker=row["ticker"],
                    sponsor=row["sponsor"],
                    drug=row["drug"],
                    sector_id=row["sector_id"],
                    phase=row["phase"],
                    status=row["status"],
                    title=row["title"],
                    change_type=None,
                    watch_reason=f"Active {row['phase'] or 'trial'} · {sector['name']}",
                )
            )
            if len(trials) >= limit:
                break

    return trials[:limit]


def _fetch_news_for_trial(trial: WatchTrial) -> list[dict]:
    queries = build_fallback_queries(trial.ticker, trial.drug, trial.sponsor)
    results: list[dict] = []
    seen_urls: set[str] = set()
    for query in queries:
        for hit in search_news(query, max_results=NEWS_PER_TRIAL):
            if hit.url in seen_urls:
                continue
            seen_urls.add(hit.url)
            results.append(
                {
                    "title": hit.title,
                    "url": hit.url,
                    "source": hit.source,
                    "published_at": hit.published_at.isoformat() if hit.published_at else None,
                }
            )
            if len(results) >= NEWS_PER_TRIAL:
                return results
    return results


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
        return {}


def _synthesize_briefs(trials: list[WatchTrial], news_map: dict[str, list[dict]]) -> dict:
    api_key = os.getenv("OPENAI_API_KEY")
    sector, _ = get_sector_for_hour()
    if not api_key:
        return _fallback_digest(trials, news_map, sector, error="OPENAI_API_KEY not set")

    trial_blocks = []
    for t in trials:
        headlines = news_map.get(t.nct_id, [])
        news_lines = "\n".join(f"- {n['title']}" for n in headlines[:4]) or "- No recent headlines found"
        trial_blocks.append(
            f"NCT: {t.nct_id}\n"
            f"Ticker: {t.ticker} | Sponsor: {t.sponsor} | Drug: {t.drug or 'Unknown'}\n"
            f"Phase: {t.phase or 'NA'} | Status: {t.status or 'NA'} | Reason: {t.watch_reason}\n"
            f"Title: {(t.title or '')[:200]}\n"
            f"Recent headlines:\n{news_lines}"
        )

    user_prompt = f"""Sector focus today: {sector['name']}

Trials on the watchlist:
{'---'.join(trial_blocks)}

Return JSON only:
{{
  "market_pulse": "2 sentences on sector/trial momentum for biotech investors",
  "trials": [
    {{
      "nct_id": "must match input",
      "headline": "short punchy headline under 12 words",
      "brief": "2-3 sentence investor-focused brief",
      "analyst_tone": "bullish|neutral|bearish",
      "catalysts": ["up to 3 near-term catalysts"]
    }}
  ]
}}"""

    client = OpenAI(api_key=api_key)
    model = os.getenv("WATCHLIST_LLM_MODEL", OPENAI_MODEL)
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a biotech equity research analyst writing a daily watchlist. "
                        "Be concise and factual. Do not invent trial results. Return valid JSON only."
                    ),
                },
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
        )
        payload = _extract_json(response.choices[0].message.content or "{}")
    except Exception as exc:
        return _fallback_digest(trials, news_map, sector, error=str(exc))

    llm_by_nct = {item.get("nct_id"): item for item in payload.get("trials", [])}
    merged_trials = []
    for t in trials:
        llm = llm_by_nct.get(t.nct_id, {})
        merged_trials.append(
            {
                "nct_id": t.nct_id,
                "ticker": t.ticker,
                "sponsor": t.sponsor,
                "drug": t.drug,
                "phase": t.phase,
                "status": t.status,
                "title": t.title,
                "change_type": t.change_type,
                "watch_reason": t.watch_reason,
                "score": t.score,
                "detected_at": t.detected_at,
                "headline": llm.get("headline") or f"{t.ticker} · {t.watch_reason}",
                "brief": llm.get("brief") or "Brief unavailable.",
                "analyst_tone": llm.get("analyst_tone", "neutral"),
                "catalysts": llm.get("catalysts", []) or [],
                "news": news_map.get(t.nct_id, []),
            }
        )

    now = datetime.now(timezone.utc).isoformat()
    return {
        "cache_key": _cache_key(),
        "generated_at": now,
        "sector_id": sector["id"],
        "sector_name": sector["name"],
        "market_pulse": payload.get("market_pulse", "Market pulse unavailable."),
        "trials": merged_trials,
        "trial_count": len(merged_trials),
    }


def _fallback_digest(
    trials: list[WatchTrial],
    news_map: dict[str, list[dict]],
    sector: dict,
    error: str | None = None,
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "cache_key": _cache_key(),
        "generated_at": now,
        "sector_id": sector["id"],
        "sector_name": sector["name"],
        "market_pulse": "Automated brief unavailable. Showing cached headlines only.",
        "error": error,
        "trials": [
            {
                "nct_id": t.nct_id,
                "ticker": t.ticker,
                "sponsor": t.sponsor,
                "drug": t.drug,
                "phase": t.phase,
                "status": t.status,
                "title": t.title,
                "change_type": t.change_type,
                "watch_reason": t.watch_reason,
                "score": t.score,
                "detected_at": t.detected_at,
                "headline": f"{t.ticker} · {t.watch_reason}",
                "brief": t.title or "No brief generated.",
                "analyst_tone": "neutral",
                "catalysts": [],
                "news": news_map.get(t.nct_id, []),
            }
            for t in trials
        ],
        "trial_count": len(trials),
    }


def save_digest(digest: dict) -> None:
    init_db()
    cache_key = digest["cache_key"]
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO watchlist_cache (cache_key, sector_id, sector_name, payload_json, generated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                sector_id = excluded.sector_id,
                sector_name = excluded.sector_name,
                payload_json = excluded.payload_json,
                generated_at = excluded.generated_at
            """,
            (
                cache_key,
                digest["sector_id"],
                digest["sector_name"],
                json.dumps(digest),
                digest["generated_at"],
            ),
        )
    WATCHLIST_JSON_PATH.write_text(json.dumps(digest, indent=2), encoding="utf-8")


def load_digest(for_date: date | None = None) -> dict | None:
    init_db()
    key = _cache_key(for_date)
    with get_connection() as conn:
        row = conn.execute(
            "SELECT payload_json, generated_at FROM watchlist_cache WHERE cache_key = ?",
            (key,),
        ).fetchone()
    if row:
        return json.loads(row["payload_json"])
    if WATCHLIST_JSON_PATH.exists():
        try:
            return json.loads(WATCHLIST_JSON_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return None


def load_digest_for_display() -> dict | None:
    """Read-only: latest cached digest. Never triggers LLM/RSS builds."""
    if WATCHLIST_JSON_PATH.exists():
        try:
            data = json.loads(WATCHLIST_JSON_PATH.read_text(encoding="utf-8"))
            if data.get("generated_at"):
                return data
        except json.JSONDecodeError:
            pass

    init_db()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT payload_json FROM watchlist_cache ORDER BY generated_at DESC LIMIT 1"
        ).fetchone()
    if row:
        return json.loads(row["payload_json"])

    return load_digest()


def cache_is_fresh(digest: dict | None = None) -> bool:
    digest = digest or load_digest()
    if not digest or not digest.get("generated_at"):
        return False
    generated = datetime.fromisoformat(digest["generated_at"])
    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - generated
    return age < timedelta(hours=CACHE_TTL_HOURS)


def build_daily_digest(force: bool = False) -> dict:
    if not force:
        existing = load_digest()
        if existing and cache_is_fresh(existing):
            return existing

    trials = fetch_watch_trials()
    if not trials:
        sector, _ = get_sector_for_hour()
        empty = {
            "cache_key": _cache_key(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "sector_id": sector["id"],
            "sector_name": sector["name"],
            "market_pulse": "No trials in snapshot yet. The hourly scraper will populate watch targets.",
            "trials": [],
            "trial_count": 0,
        }
        save_digest(empty)
        return empty

    news_map = {t.nct_id: _fetch_news_for_trial(t) for t in trials}
    digest = _synthesize_briefs(trials, news_map)
    save_digest(digest)
    return digest


def get_watchlist_digest(force_refresh: bool = False) -> dict:
    """Build or return cache. For pipeline/cron/admin only — not the Streamlit UI."""
    if not force_refresh:
        cached = load_digest_for_display()
        if cached and cache_is_fresh(cached):
            return cached
    return build_daily_digest(force=force_refresh)
