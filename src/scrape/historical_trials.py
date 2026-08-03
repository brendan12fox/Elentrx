"""Fetch historical trial events for backtesting."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import requests

from src.config import CTGOV_BASE_URL, CTGOV_PAGE_SIZE, CTGOV_REQUEST_DELAY
from src.map.sponsors import resolve_sponsor
from src.scrape.ctgov import _extract_drug, _extract_phase


@dataclass
class HistoricalTrialEvent:
    nct_id: str
    ticker: str
    sponsor: str
    drug: str | None
    title: str | None
    phase: str | None
    overall_status: str | None
    event_date: date
    event_type: str


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    for fmt, length in (("%Y-%m-%d", 10), ("%Y-%m", 7), ("%Y", 4)):
        try:
            parsed = datetime.strptime(value[:length], fmt)
            return parsed.date()
        except ValueError:
            continue
    return None


def _event_date_from_study(study: dict[str, Any]) -> date | None:
    status_mod = study.get("protocolSection", {}).get("statusModule", {})
    for key in ("primaryCompletionDateStruct", "completionDateStruct", "lastUpdatePostDateStruct"):
        block = status_mod.get(key, {})
        parsed = _parse_date(block.get("date"))
        if parsed:
            return parsed
    return None


def parse_historical_event(study: dict[str, Any]) -> HistoricalTrialEvent | None:
    protocol = study.get("protocolSection", {})
    ident = protocol.get("identificationModule", {})
    sponsor_mod = protocol.get("sponsorCollaboratorsModule", {})
    status_mod = protocol.get("statusModule", {})
    design_mod = protocol.get("designModule", {})
    arms_mod = protocol.get("armsInterventionsModule", {})

    lead_sponsor = sponsor_mod.get("leadSponsor", {}).get("name")
    if not lead_sponsor:
        return None

    match = resolve_sponsor(lead_sponsor)
    if not match:
        return None

    event_date = _event_date_from_study(study)
    if not event_date:
        return None

    phase = _extract_phase(design_mod.get("phases"))
    status = status_mod.get("overallStatus") or status_mod.get("lastKnownStatus")

    if phase not in {"PHASE2", "PHASE3", "PHASE4"}:
        return None
    if status not in {"COMPLETED", "TERMINATED", "WITHDRAWN", "SUSPENDED"}:
        return None

    if status == "COMPLETED" and phase in {"PHASE3", "PHASE4"}:
        event_type = "status_completed"
    elif status in {"TERMINATED", "WITHDRAWN", "SUSPENDED"}:
        event_type = "status_negative"
    else:
        event_type = "phase_milestone"

    return HistoricalTrialEvent(
        nct_id=ident.get("nctId", ""),
        ticker=match.ticker,
        sponsor=lead_sponsor,
        drug=_extract_drug(arms_mod.get("interventions")),
        title=ident.get("briefTitle") or ident.get("officialTitle"),
        phase=phase,
        overall_status=status,
        event_date=event_date,
        event_type=event_type,
    )


class HistoricalTrialsClient:
    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    def fetch_completed_trials(
        self,
        start_date: date,
        end_date: date,
        max_pages: int = 10,
        max_events: int | None = None,
    ) -> list[HistoricalTrialEvent]:
        """Fetch trials across the date range using quarterly windows for spread."""
        all_events: list[HistoricalTrialEvent] = []
        window_start = start_date

        while window_start <= end_date:
            # ~3-month windows
            window_end = min(
                date(window_start.year, window_start.month, 28) + timedelta(days=35),
                end_date,
            )
            if window_end <= window_start:
                break

            batch = self._fetch_window(window_start, window_end, max_pages=max(2, max_pages // 3))
            all_events.extend(batch)

            if max_events and len(all_events) >= max_events:
                break
            window_start = window_end + timedelta(days=1)

        deduped: dict[str, HistoricalTrialEvent] = {}
        for event in all_events:
            existing = deduped.get(event.nct_id)
            if existing is None or event.event_date < existing.event_date:
                deduped[event.nct_id] = event

        results = sorted(deduped.values(), key=lambda e: e.event_date)
        if max_events:
            return results[:max_events]
        return results

    def _fetch_window(
        self,
        start_date: date,
        end_date: date,
        max_pages: int = 3,
    ) -> list[HistoricalTrialEvent]:
        date_filter = (
            f"AREA[PrimaryCompletionDate]RANGE[{start_date.isoformat()},{end_date.isoformat()}]"
        )
        params: dict[str, Any] = {
            "filter.advanced": f"AREA[StudyType]INTERVENTIONAL AND {date_filter}",
            "pageSize": CTGOV_PAGE_SIZE,
            "sort": "PrimaryCompletionDate:asc",
        }

        events: list[HistoricalTrialEvent] = []
        page_token: str | None = None

        for _ in range(max_pages):
            if page_token:
                params["pageToken"] = page_token
            else:
                params.pop("pageToken", None)

            response = self.session.get(f"{CTGOV_BASE_URL}/studies", params=params, timeout=60)
            response.raise_for_status()
            payload = response.json()

            for study in payload.get("studies", []):
                parsed = parse_historical_event(study)
                if parsed and parsed.nct_id:
                    events.append(parsed)

            page_token = payload.get("nextPageToken")
            if not page_token:
                break
            time.sleep(CTGOV_REQUEST_DELAY)

        return events
