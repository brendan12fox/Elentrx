"""ClinicalTrials.gov v2 API client."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import requests

from src.config import (
    CTGOV_BASE_URL,
    CTGOV_MAX_PAGES,
    CTGOV_PAGE_SIZE,
    CTGOV_REQUEST_DELAY,
)
from src.map.sponsors import resolve_sponsor


@dataclass
class TrialRecord:
    nct_id: str
    ticker: str
    sponsor: str
    drug: str | None
    sector_id: str
    phase: str | None
    overall_status: str | None
    title: str | None


def _extract_phase(phases: list[str] | None) -> str | None:
    if not phases:
        return None
    # Use highest phase when multiple are listed
    order = {"NA": 0, "EARLY_PHASE1": 1, "PHASE1": 2, "PHASE2": 3, "PHASE3": 4, "PHASE4": 5}
    ranked = sorted(phases, key=lambda p: order.get(p, -1), reverse=True)
    return ranked[0] if ranked else None


def _extract_drug(interventions: list[dict] | None) -> str | None:
    if not interventions:
        return None
    for item in interventions:
        if item.get("type") in {"DRUG", "BIOLOGICAL"}:
            return item.get("name")
    for item in interventions:
        if item.get("name"):
            return item.get("name")
    return None


def parse_study(study: dict[str, Any], sector_id: str) -> TrialRecord | None:
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

    phases = design_mod.get("phases")
    return TrialRecord(
        nct_id=ident.get("nctId", ""),
        ticker=match.ticker,
        sponsor=lead_sponsor,
        drug=_extract_drug(arms_mod.get("interventions")),
        sector_id=sector_id,
        phase=_extract_phase(phases),
        overall_status=status_mod.get("overallStatus"),
        title=ident.get("briefTitle") or ident.get("officialTitle"),
    )


class ClinicalTrialsClient:
    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    def fetch_sector_studies(
        self,
        sector: dict,
        max_pages: int = CTGOV_MAX_PAGES,
    ) -> list[TrialRecord]:
        params: dict[str, Any] = {
            "query.cond": sector["query_cond"],
            "filter.advanced": "AREA[StudyType]INTERVENTIONAL",
            "pageSize": CTGOV_PAGE_SIZE,
        }

        records: list[TrialRecord] = []
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
                parsed = parse_study(study, sector["id"])
                if parsed and parsed.nct_id:
                    records.append(parsed)

            page_token = payload.get("nextPageToken")
            if not page_token:
                break
            time.sleep(CTGOV_REQUEST_DELAY)

        return records
