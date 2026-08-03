"""Map clinical trial sponsors to public tickers."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from functools import lru_cache

from rapidfuzz import fuzz, process

from src.config import SPONSOR_MAP_PATH


@dataclass(frozen=True)
class SponsorMatch:
    sponsor_name: str
    ticker: str
    exchange: str
    score: float


def _normalize(name: str) -> str:
    cleaned = name.lower().strip()
    cleaned = re.sub(r"[^\w\s&]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


@lru_cache(maxsize=1)
def load_sponsor_map() -> list[dict]:
    rows: list[dict] = []
    with SPONSOR_MAP_PATH.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            aliases = [row["sponsor_name"].strip()]
            if row.get("aliases"):
                aliases.extend(part.strip() for part in row["aliases"].split("|") if part.strip())
            rows.append(
                {
                    "sponsor_name": row["sponsor_name"].strip(),
                    "ticker": row["ticker"].strip().upper(),
                    "exchange": row["exchange"].strip(),
                    "aliases": aliases,
                }
            )
    return rows


def build_lookup() -> dict[str, dict]:
    lookup: dict[str, dict] = {}
    for row in load_sponsor_map():
        for alias in row["aliases"]:
            lookup[_normalize(alias)] = row
    return lookup


def resolve_sponsor(sponsor: str, min_score: float = 85.0) -> SponsorMatch | None:
    if not sponsor or not sponsor.strip():
        return None

    lookup = build_lookup()
    normalized = _normalize(sponsor)
    if normalized in lookup:
        row = lookup[normalized]
        return SponsorMatch(sponsor, row["ticker"], row["exchange"], 100.0)

    choices = list(lookup.keys())
    result = process.extractOne(normalized, choices, scorer=fuzz.token_set_ratio)
    if not result:
        return None

    matched_key, score, _ = result
    if score < min_score:
        return None

    row = lookup[matched_key]
    return SponsorMatch(sponsor, row["ticker"], row["exchange"], float(score))
