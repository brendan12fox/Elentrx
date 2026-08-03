"""Live training progress tracking."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.config import DATA_DIR, ensure_dirs

PROGRESS_PATH = DATA_DIR / "training_progress.json"


class TrainingProgress:
    def __init__(self, total_events: int, max_events: int):
        ensure_dirs()
        self.data = {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": self._now(),
            "status": "running",
            "phase": "fetching_trials",
            "max_events": max_events,
            "total_events_fetched": total_events,
            "processed": 0,
            "samples_built": 0,
            "skipped_no_return": 0,
            "serper_calls": 0,
            "news_with_articles": 0,
            "current": None,
            "recent_events": [],
            "elapsed_seconds": 0,
            "eta_seconds": None,
            "rate_per_minute": None,
        }
        self._start = datetime.now(timezone.utc)
        self._write()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def set_phase(self, phase: str) -> None:
        self.data["phase"] = phase
        self.data["updated_at"] = self._now()
        self._write()

    def set_fetched(self, count: int) -> None:
        self.data["total_events_fetched"] = count
        self.data["phase"] = "processing_events"
        self.data["updated_at"] = self._now()
        self._write()

    def tick(
        self,
        *,
        ticker: str,
        nct_id: str,
        event_date: str,
        news_count: int,
        label: int,
        skipped: bool = False,
    ) -> None:
        self.data["processed"] += 1
        if skipped:
            self.data["skipped_no_return"] += 1
        else:
            self.data["samples_built"] += 1
            if news_count > 0:
                self.data["news_with_articles"] += 1

        elapsed = (datetime.now(timezone.utc) - self._start).total_seconds()
        self.data["elapsed_seconds"] = round(elapsed, 1)
        done = self.data["processed"]
        total = max(self.data["total_events_fetched"], 1)
        if done > 0:
            rate = done / (elapsed / 60) if elapsed > 0 else 0
            self.data["rate_per_minute"] = round(rate, 2)
            remaining = total - done
            if rate > 0:
                self.data["eta_seconds"] = round(remaining / rate * 60, 0)

        self.data["current"] = {
            "ticker": ticker,
            "nct_id": nct_id,
            "event_date": event_date,
            "news_count": news_count,
            "label": label,
        }
        entry = {
            "at": self._now(),
            "ticker": ticker,
            "nct_id": nct_id,
            "event_date": event_date,
            "news_count": news_count,
            "label": label,
        }
        recent = self.data.get("recent_events", [])
        recent.append(entry)
        self.data["recent_events"] = recent[-20:]

        try:
            from src.research.search import get_serper_usage
            self.data["serper_calls"] = get_serper_usage().get("monthly_calls", 0)
        except Exception:
            pass

        self.data["updated_at"] = self._now()
        self._write()

    def complete(self, sample_count: int) -> None:
        self.data["status"] = "complete"
        self.data["phase"] = "done"
        self.data["samples_built"] = sample_count
        self.data["updated_at"] = self._now()
        elapsed = (datetime.now(timezone.utc) - self._start).total_seconds()
        self.data["elapsed_seconds"] = round(elapsed, 1)
        self.data["eta_seconds"] = 0
        self._write()

    def fail(self, error: str) -> None:
        self.data["status"] = "error"
        self.data["error"] = error
        self.data["updated_at"] = self._now()
        self._write()

    def _write(self) -> None:
        PROGRESS_PATH.write_text(json.dumps(self.data, indent=2), encoding="utf-8")


def load_progress() -> dict | None:
    if not PROGRESS_PATH.exists():
        return None
    try:
        return json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
