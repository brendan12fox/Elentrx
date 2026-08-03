"""Build point-in-time historical labeled dataset for classifier evaluation."""

from __future__ import annotations

import contextlib
import io
import json
import logging
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from src.config import DATA_DIR, PHASE_ORDER, ensure_dirs
from src.ml.features import build_features
from src.research.llm_agent import ResearchBrief, analyze_phase_change
from src.research.openai_search import sources_found_from_brief
from src.scrape.diff import PhaseChange
from src.ml.progress import TrainingProgress
from src.scrape.historical_trials import HistoricalTrialEvent, HistoricalTrialsClient

HISTORICAL_DATASET_PATH = DATA_DIR / "historical_dataset.json"
FORWARD_RETURN_DAYS = 5
LABEL_THRESHOLD = 0.02
NEWS_LOOKBACK_DAYS = 30

logging.getLogger("yfinance").setLevel(logging.CRITICAL)


@dataclass
class HistoricalSample:
    nct_id: str
    ticker: str
    sponsor: str
    drug: str | None
    event_date: str
    event_type: str
    change_type: str
    old_phase: str | None
    new_phase: str | None
    old_status: str | None
    new_status: str | None
    forward_return_5d: float
    label: int
    news_count: int
    summary: str
    analyst_tone: str
    catalysts: list[str]
    safety_signals: list[str]
    risk_flags: list[str]
    features: list[float]

    def to_dict(self) -> dict:
        return asdict(self)


def _infer_phase_change(event: HistoricalTrialEvent) -> PhaseChange:
    old_phase = "PHASE2" if event.phase == "PHASE3" else "PHASE1"
    new_phase = event.phase
    if event.event_type == "status_negative":
        old_status = "RECRUITING"
        new_status = event.overall_status
    else:
        old_status = "ACTIVE_NOT_RECRUITING"
        new_status = event.overall_status or "COMPLETED"

    return PhaseChange(
        nct_id=event.nct_id,
        ticker=event.ticker,
        sponsor=event.sponsor,
        drug=event.drug,
        sector_id="historical",
        old_phase=old_phase,
        new_phase=new_phase,
        old_status=old_status,
        new_status=new_status,
        change_type=event.event_type,
    )


def _download_closes(ticker: str, start: date, end: date) -> pd.Series:
    with contextlib.redirect_stderr(io.StringIO()):
        hist = yf.download(
            ticker,
            start=start.isoformat(),
            end=(end + timedelta(days=10)).isoformat(),
            progress=False,
            auto_adjust=True,
            threads=False,
        )
    if hist.empty:
        return pd.Series(dtype=float)
    if isinstance(hist.columns, pd.MultiIndex):
        closes = hist["Close"].squeeze()
    else:
        closes = hist["Close"]
    return pd.Series(closes).dropna()


def forward_return(ticker: str, event_date: date, trading_days: int = FORWARD_RETURN_DAYS) -> float | None:
    """Compute forward return starting the first trading day AFTER event_date."""
    start = event_date - timedelta(days=5)
    end = event_date + timedelta(days=trading_days * 3)
    closes = _download_closes(ticker, start, end)
    if closes.empty:
        return None

    index = closes.index
    if hasattr(index, "tz") and index.tz is not None:
        index = index.tz_localize(None)
    closes.index = pd.to_datetime(index).normalize()

    event_ts = pd.Timestamp(event_date)
    future = closes[closes.index > event_ts]
    if future.empty:
        return None

    base = float(future.iloc[0])
    if len(future) <= trading_days:
        target = float(future.iloc[-1])
    else:
        target = float(future.iloc[trading_days])

    if base == 0:
        return None
    return (target - base) / base


def _brief_to_sample_fields(brief: ResearchBrief) -> dict:
    return {
        "summary": brief.summary,
        "analyst_tone": brief.analyst_tone,
        "catalysts": brief.catalysts,
        "safety_signals": brief.safety_signals,
        "risk_flags": brief.risk_flags,
    }


def _heuristic_brief(news_count: int, event_type: str, phase: str | None = None) -> ResearchBrief:
    if event_type == "status_negative":
        tone = "bearish"
        catalysts: list[str] = []
        safety = ["trial halt"]
    elif event_type == "status_completed" and phase in {"PHASE3", "PHASE4"}:
        tone = "bullish"
        catalysts = ["pivotal readout", "regulatory path"]
        safety = []
    elif news_count >= 3:
        tone = "bullish"
        catalysts = ["trial milestone"]
        safety = []
    else:
        tone = "neutral"
        catalysts = []
        safety = []

    return ResearchBrief(
        summary=f"Heuristic brief ({news_count} pre-event articles, {event_type}).",
        catalysts=catalysts,
        safety_signals=safety,
        endpoints=["primary endpoint"] if event_type == "status_completed" else [],
        analyst_tone=tone,
        risk_flags=["low_news_coverage"] if news_count == 0 else [],
        raw_json={"mode": "heuristic", "news_count": news_count},
    )


def build_historical_dataset(
    start_date: date | None = None,
    end_date: date | None = None,
    max_events: int = 60,
    use_llm: bool = True,
    lookback_days: int = NEWS_LOOKBACK_DAYS,
) -> list[HistoricalSample]:
    ensure_dirs()
    end = end_date or (date.today() - timedelta(days=FORWARD_RETURN_DAYS * 2))
    start = start_date or (end - timedelta(days=365 * 3))

    client = HistoricalTrialsClient()
    events = client.fetch_completed_trials(
        start, end, max_pages=max(8, max_events // 15), max_events=max_events * 2
    )
    events = events[:max_events]

    progress = TrainingProgress(total_events=len(events), max_events=max_events)
    progress.set_fetched(len(events))

    samples: list[HistoricalSample] = []
    for event in events:
        ret = forward_return(event.ticker, event.event_date)
        if ret is None:
            progress.tick(
                ticker=event.ticker,
                nct_id=event.nct_id,
                event_date=event.event_date.isoformat(),
                news_count=0,
                label=0,
                skipped=True,
            )
            continue

        label = 1 if ret >= LABEL_THRESHOLD else 0
        change = _infer_phase_change(event)

        if use_llm:
            brief = analyze_phase_change(
                change,
                as_of_date=event.event_date,
                lookback_days=lookback_days,
            )
            news_count = sources_found_from_brief(brief.raw_json)
        else:
            brief = _heuristic_brief(0, event.event_type, event.phase)
            news_count = 0

        fields = _brief_to_sample_fields(brief)
        fv = build_features(change, brief, news_count=news_count)

        samples.append(
            HistoricalSample(
                nct_id=event.nct_id,
                ticker=event.ticker,
                sponsor=event.sponsor,
                drug=event.drug,
                event_date=event.event_date.isoformat(),
                event_type=event.event_type,
                change_type=change.change_type,
                old_phase=change.old_phase,
                new_phase=change.new_phase,
                old_status=change.old_status,
                new_status=change.new_status,
                forward_return_5d=float(ret),
                label=label,
                news_count=news_count,
                summary=fields["summary"],
                analyst_tone=fields["analyst_tone"],
                catalysts=fields["catalysts"],
                safety_signals=fields["safety_signals"],
                risk_flags=fields["risk_flags"],
                features=fv.values,
            )
        )
        progress.tick(
            ticker=event.ticker,
            nct_id=event.nct_id,
            event_date=event.event_date.isoformat(),
            news_count=news_count,
            label=label,
        )

    samples.sort(key=lambda s: s.event_date)
    progress.complete(len(samples))
    return samples


def save_dataset(samples: list[HistoricalSample], path: Path | None = None) -> Path:
    ensure_dirs()
    out = path or HISTORICAL_DATASET_PATH
    payload = {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "forward_return_days": FORWARD_RETURN_DAYS,
        "label_threshold": LABEL_THRESHOLD,
        "news_lookback_days": NEWS_LOOKBACK_DAYS,
        "samples": [s.to_dict() for s in samples],
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out


def load_dataset(path: Path | None = None) -> list[HistoricalSample]:
    src = path or HISTORICAL_DATASET_PATH
    if not src.exists():
        return []
    payload = json.loads(src.read_text(encoding="utf-8"))
    return [HistoricalSample(**row) for row in payload.get("samples", [])]


def dataset_to_arrays(samples: list[HistoricalSample]) -> tuple[np.ndarray, np.ndarray, list[str]]:
    if not samples:
        return np.array([]), np.array([]), []
    X = np.array([s.features for s in samples], dtype=float)
    y = np.array([s.label for s in samples], dtype=int)
    dates = [s.event_date for s in samples]
    return X, y, dates
