"""News and web search for trial research — free historical sources included."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.parse
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

import feedparser
import requests

from src.config import DATA_DIR, SERPER_MONTHLY_LIMIT

CACHE_DIR = DATA_DIR / "news_cache"
SERPER_USAGE_PATH = DATA_DIR / "serper_usage.json"
GDELT_MIN_INTERVAL = 5.5  # seconds between GDELT requests
RSS_MIN_INTERVAL = 1.0

NEWS_MODE_PRODUCTION = "production"
NEWS_MODE_TRAINING = "training"

_last_gdelt_at: float = 0.0
_last_rss_at: float = 0.0


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str
    published_at: date | None = None


def search_news(query: str, max_results: int = 8) -> list[SearchResult]:
    """Live/production news — free sources only (RSS/GDELT)."""
    return search_news_as_of(
        query,
        as_of_date=date.today(),
        lookback_days=30,
        max_results=max_results,
        mode=NEWS_MODE_PRODUCTION,
    )


def get_serper_usage() -> dict:
    """Return Serper call counts for budget tracking."""
    if not SERPER_USAGE_PATH.exists():
        return {"month": _current_month_key(), "monthly_calls": 0, "lifetime_calls": 0}
    try:
        return json.loads(SERPER_USAGE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"month": _current_month_key(), "monthly_calls": 0, "lifetime_calls": 0}


def serper_budget_remaining() -> int:
    usage = get_serper_usage()
    month = _current_month_key()
    calls = usage.get("monthly_calls", 0) if usage.get("month") == month else 0
    return max(0, SERPER_MONTHLY_LIMIT - calls)


def _current_month_key() -> str:
    return datetime.now().strftime("%Y-%m")


def _increment_serper_usage() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    usage = get_serper_usage()
    month = _current_month_key()
    if usage.get("month") != month:
        usage = {"month": month, "monthly_calls": 0, "lifetime_calls": usage.get("lifetime_calls", 0)}
    usage["monthly_calls"] = int(usage.get("monthly_calls", 0)) + 1
    usage["lifetime_calls"] = int(usage.get("lifetime_calls", 0)) + 1
    SERPER_USAGE_PATH.write_text(json.dumps(usage, indent=2), encoding="utf-8")


def build_search_query(
    ticker: str,
    drug: str | None,
    sponsor: str,
    nct_id: str,
    old_phase: str | None,
    new_phase: str | None,
) -> str:
    """Shorter query works better for RSS/GDELT news search."""
    parts = [ticker]
    if drug and len(drug) < 40:
        parts.append(drug)
    parts.append(sponsor.split()[0])  # first word of sponsor
    if new_phase:
        parts.append(new_phase.replace("_", " ").lower())
    parts.append("clinical trial")
    return " ".join(parts)


def build_fallback_queries(
    ticker: str,
    drug: str | None,
    sponsor: str,
) -> list[str]:
    """Progressively simpler queries when detailed search returns nothing."""
    sponsor_short = sponsor.split()[0]
    queries = [
        build_search_query(ticker, drug, sponsor, "", None, None),
        f"{ticker} {sponsor_short} clinical trial FDA",
        f"{ticker} {sponsor_short} phase 3",
        f"{sponsor_short} biotech clinical trial",
    ]
    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            out.append(q)
    return out


def search_news_as_of(
    query: str,
    as_of_date: date,
    lookback_days: int = 30,
    max_results: int = 8,
    fallback_queries: list[str] | None = None,
    mode: str = NEWS_MODE_PRODUCTION,
) -> list[SearchResult]:
    """Return news from [as_of_date - lookback, as_of_date].

    mode=production (default): free RSS/GDELT only — used by live hourly pipeline.
    mode=training: Serper on primary query only (budget-tracked), RSS/GDELT for fill/fallbacks.
    """
    start_date = as_of_date - timedelta(days=lookback_days)
    end_date = as_of_date

    queries = [query] + [q for q in (fallback_queries or []) if q != query]
    all_results: list[SearchResult] = []

    for idx, q in enumerate(queries):
        cached = _load_cache(q, start_date, end_date, mode)
        if cached is not None:
            all_results.extend(cached)
            if len(_dedupe_results(_filter_results_by_date(all_results, start_date, end_date))) >= max_results:
                break
            continue

        # Only spend Serper credits on the primary query during training
        allow_paid = mode == NEWS_MODE_TRAINING and idx == 0
        batch = _fetch_news_for_query(q, start_date, end_date, max_results, mode=mode, allow_paid=allow_paid)
        _save_cache(q, start_date, end_date, batch, mode)
        all_results.extend(batch)
        if len(_dedupe_results(_filter_results_by_date(all_results, start_date, end_date))) >= max_results:
            break

    return _dedupe_results(_filter_results_by_date(all_results, start_date, end_date))[:max_results]


def _fetch_news_for_query(
    query: str,
    start_date: date,
    end_date: date,
    max_results: int,
    mode: str = NEWS_MODE_PRODUCTION,
    allow_paid: bool = False,
) -> list[SearchResult]:
    results: list[SearchResult] = []

    if allow_paid and mode == NEWS_MODE_TRAINING:
        serper_key = os.getenv("SERPER_API_KEY")
        if serper_key and serper_budget_remaining() > 0:
            try:
                results.extend(_search_serper(query, serper_key, max_results, start_date, end_date))
                _increment_serper_usage()
            except Exception:
                pass
        tavily_key = os.getenv("TAVILY_API_KEY")
        if not results and tavily_key:
            try:
                results.extend(_search_tavily(query, tavily_key, max_results, start_date, end_date))
            except Exception:
                pass

    # Free sources — always available (production uses these exclusively)
    try:
        results.extend(_search_google_news_rss(query, start_date, end_date, max_results))
    except Exception:
        pass

    filtered = _filter_results_by_date(results, start_date, end_date)
    # Skip slow GDELT in training when Serper key is set (RSS + Serper is enough)
    skip_gdelt = mode == NEWS_MODE_TRAINING and os.getenv("SERPER_API_KEY")
    if len(filtered) < max_results // 2 and not skip_gdelt:
        try:
            results.extend(_search_gdelt(query, start_date, end_date, max_results))
        except Exception:
            pass

    if not results and end_date >= date.today() - timedelta(days=1) and mode == NEWS_MODE_PRODUCTION:
        try:
            results.extend(_search_duckduckgo_fallback(query, max_results))
        except Exception:
            pass

    return _dedupe_results(_filter_results_by_date(results, start_date, end_date))


def _cache_key(query: str, start: date, end: date, mode: str) -> str:
    raw = f"{mode}|{query}|{start.isoformat()}|{end.isoformat()}"
    return hashlib.md5(raw.encode()).hexdigest()


def _load_cache(query: str, start: date, end: date, mode: str) -> list[SearchResult] | None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{_cache_key(query, start, end, mode)}.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return [
            SearchResult(
                title=item["title"],
                url=item["url"],
                snippet=item["snippet"],
                source=item["source"],
                published_at=date.fromisoformat(item["published_at"]) if item.get("published_at") else None,
            )
            for item in payload
        ]
    except Exception:
        return None


def _save_cache(query: str, start: date, end: date, results: list[SearchResult], mode: str) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{_cache_key(query, start, end, mode)}.json"
    payload = [
        {
            "title": r.title,
            "url": r.url,
            "snippet": r.snippet,
            "source": r.source,
            "published_at": r.published_at.isoformat() if r.published_at else None,
        }
        for r in results
    ]
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _dedupe_results(results: list[SearchResult]) -> list[SearchResult]:
    seen: set[str] = set()
    out: list[SearchResult] = []
    for item in results:
        key = item.url or item.title
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _rate_limit(kind: str, interval: float) -> None:
    global _last_gdelt_at, _last_rss_at
    now = time.monotonic()
    if kind == "gdelt":
        wait = interval - (now - _last_gdelt_at)
        if wait > 0:
            time.sleep(wait)
        _last_gdelt_at = time.monotonic()
    elif kind == "rss":
        wait = interval - (now - _last_rss_at)
        if wait > 0:
            time.sleep(wait)
        _last_rss_at = time.monotonic()


def _search_google_news_rss(
    query: str,
    start_date: date,
    end_date: date,
    max_results: int,
) -> list[SearchResult]:
    """Google News RSS with after:/before: date operators — free, no API key."""
    _rate_limit("rss", RSS_MIN_INTERVAL)
    dated_query = f"{query} after:{start_date.isoformat()} before:{(end_date + timedelta(days=1)).isoformat()}"
    encoded = urllib.parse.quote(dated_query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"

    response = requests.get(
        url,
        timeout=30,
        headers={"User-Agent": "StonkScraper/1.0 (clinical trial research)"},
    )
    response.raise_for_status()

    feed = feedparser.parse(response.text)
    results: list[SearchResult] = []
    for entry in feed.entries[: max_results * 2]:
        pub = None
        if getattr(entry, "published", None):
            try:
                pub = parsedate_to_datetime(entry.published).date()
            except Exception:
                pub = _parse_published(entry.published)
        elif getattr(entry, "updated", None):
            try:
                pub = parsedate_to_datetime(entry.updated).date()
            except Exception:
                pass

        snippet = ""
        if getattr(entry, "summary", None):
            snippet = re.sub(r"<[^>]+>", "", entry.summary)[:500]

        results.append(
            SearchResult(
                title=getattr(entry, "title", ""),
                url=getattr(entry, "link", ""),
                snippet=snippet or getattr(entry, "title", ""),
                source="google_news_rss",
                published_at=pub,
            )
        )
    return results


def _search_gdelt(
    query: str,
    start_date: date,
    end_date: date,
    max_results: int,
) -> list[SearchResult]:
    """GDELT DOC API — free historical news archive, 1 req / 5 sec."""
    _rate_limit("gdelt", GDELT_MIN_INTERVAL)

    # GDELT prefers shorter queries
    short_query = " ".join(query.split()[:6])

    params = {
        "query": short_query,
        "mode": "artlist",
        "maxrecords": min(max_results, 25),
        "STARTDATETIME": start_date.strftime("%Y%m%d") + "000000",
        "ENDDATETIME": end_date.strftime("%Y%m%d") + "235959",
        "format": "json",
    }
    response = requests.get(
        "https://api.gdeltproject.org/api/v2/doc/doc",
        params=params,
        timeout=45,
    )
    if response.status_code == 429:
        time.sleep(GDELT_MIN_INTERVAL)
        response = requests.get(
            "https://api.gdeltproject.org/api/v2/doc/doc",
            params=params,
            timeout=45,
        )
    response.raise_for_status()
    payload = response.json()

    results: list[SearchResult] = []
    for item in payload.get("articles", []):
        seendate = item.get("seendate", "")
        pub = None
        if seendate and len(seendate) >= 8:
            try:
                pub = datetime.strptime(seendate[:8], "%Y%m%d").date()
            except ValueError:
                pass

        results.append(
            SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=f"{item.get('domain', '')} — {item.get('title', '')}",
                source="gdelt",
                published_at=pub,
            )
        )
    return results


def _filter_results_by_date(
    results: list[SearchResult],
    start_date: date,
    end_date: date,
) -> list[SearchResult]:
    filtered: list[SearchResult] = []
    for item in results:
        if item.published_at is None:
            continue
        if start_date <= item.published_at <= end_date:
            filtered.append(item)
    return filtered


def _parse_published(value: str | None) -> date | None:
    if not value:
        return None
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%b %d, %Y", "%B %d, %Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(value[: len(fmt.replace("%", "0"))], fmt).date()
        except ValueError:
            continue
    iso_match = re.match(r"(\d{4}-\d{2}-\d{2})", value)
    if iso_match:
        return datetime.strptime(iso_match.group(1), "%Y-%m-%d").date()
    return None


def _search_tavily(
    query: str,
    api_key: str,
    max_results: int,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[SearchResult]:
    body: dict = {
        "api_key": api_key,
        "query": query,
        "search_depth": "advanced",
        "max_results": max_results,
        "include_answer": False,
    }
    if start_date and end_date:
        body["start_date"] = start_date.isoformat()
        body["end_date"] = end_date.isoformat()

    response = requests.post("https://api.tavily.com/search", json=body, timeout=30)
    response.raise_for_status()
    payload = response.json()
    results: list[SearchResult] = []
    for item in payload.get("results", []):
        published = _parse_published(item.get("published_date") or item.get("date"))
        results.append(
            SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("content", ""),
                source="tavily",
                published_at=published,
            )
        )
    return results


def _search_serper(
    query: str,
    api_key: str,
    max_results: int,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[SearchResult]:
    body: dict = {"q": query, "num": max_results}
    if start_date and end_date:
        body["tbs"] = (
            f"cdr:1,cd_min:{start_date.month}/{start_date.day}/{start_date.year},"
            f"cd_max:{end_date.month}/{end_date.day}/{end_date.year}"
        )

    response = requests.post(
        "https://google.serper.dev/news",
        headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
        json=body,
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    results: list[SearchResult] = []
    for item in payload.get("news", []):
        results.append(
            SearchResult(
                title=item.get("title", ""),
                url=item.get("link", ""),
                snippet=item.get("snippet", ""),
                source="serper",
                published_at=_parse_published(item.get("date")),
            )
        )
    return results


def _search_duckduckgo_fallback(query: str, max_results: int) -> list[SearchResult]:
    response = requests.get(
        "https://api.duckduckgo.com/",
        params={"q": query, "format": "json", "no_redirect": 1, "no_html": 1},
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    results: list[SearchResult] = []
    for item in payload.get("RelatedTopics", [])[:max_results]:
        if isinstance(item, dict) and "Text" in item:
            results.append(
                SearchResult(
                    title=item.get("Text", "")[:120],
                    url=item.get("FirstURL", ""),
                    snippet=item.get("Text", ""),
                    source="duckduckgo",
                )
            )
    return results
