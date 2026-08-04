"""Sample phase-change scenarios for the alert demo."""

from __future__ import annotations

from dataclasses import dataclass

from src.alert.email import build_alert_email
from src.config import FAVORABILITY_THRESHOLD


@dataclass
class DemoScenario:
    id: str
    label: str
    subtitle: str
    accent: str  # css gradient
    border_color: str
    icon: str
    ticker: str
    nct_id: str
    drug: str
    sponsor: str
    change_label: str
    phase_from: str
    phase_to: str
    analyst_tone: str
    score: float
    summary: str
    alert_fires: bool
    alert_reason: str


def get_demo_scenarios() -> list[DemoScenario]:
    threshold = FAVORABILITY_THRESHOLD
    return [
        DemoScenario(
            id="bullish",
            label="Favorable · Alert sent",
            subtitle="Phase advance with strong ML score",
            accent="linear-gradient(135deg, #059669 0%, #10b981 50%, #34d399 100%)",
            border_color="#10b981",
            icon="↑",
            ticker="REGN",
            nct_id="NCT04426695",
            drug="Odronextamab",
            sponsor="Regeneron",
            change_label="Phase advanced",
            phase_from="Phase 2",
            phase_to="Phase 3",
            analyst_tone="bullish",
            score=0.84,
            summary=(
                "Regeneron advanced odronextamab into Phase 3 after encouraging lymphoma response rates. "
                "Analysts cite a clear regulatory path and limited competing CD20×CD3 bispecifics."
            ),
            alert_fires=True,
            alert_reason=f"Score 84% is above your {threshold:.0%} threshold — an email would be sent.",
        ),
        DemoScenario(
            id="neutral",
            label="Neutral · No alert",
            subtitle="Completed trial, mixed signals",
            accent="linear-gradient(135deg, #6366f1 0%, #818cf8 50%, #a5b4fc 100%)",
            border_color="#6366f1",
            icon="→",
            ticker="AMGN",
            nct_id="NCT04104683",
            drug="Tezepelumab",
            sponsor="Amgen",
            change_label="Trial completed",
            phase_from="Phase 3",
            phase_to="Phase 3",
            analyst_tone="neutral",
            score=0.51,
            summary=(
                "Amgen completed the SOURCE asthma study on schedule. Results are awaited; "
                "consensus is cautiously neutral pending full data at a medical meeting."
            ),
            alert_fires=False,
            alert_reason=f"Score 51% is below your {threshold:.0%} threshold — logged only, no email.",
        ),
        DemoScenario(
            id="bearish",
            label="Negative · No alert",
            subtitle="Trial halted — bearish tone",
            accent="linear-gradient(135deg, #dc2626 0%, #ef4444 50%, #f87171 100%)",
            border_color="#ef4444",
            icon="↓",
            ticker="BMY",
            nct_id="NCT03338790",
            drug="Relatlimab combo",
            sponsor="Bristol-Myers Squibb",
            change_label="Trial halted",
            phase_from="Phase 3",
            phase_to="Phase 3",
            analyst_tone="bearish",
            score=0.12,
            summary=(
                "BMS terminated the study early following a futility analysis and emerging safety signals. "
                "Street models may trim peak sales assumptions for the combination."
            ),
            alert_fires=False,
            alert_reason=f"Score 12% is well below threshold — you would not receive an alert.",
        ),
    ]


def preview_alerts(scenario: DemoScenario) -> dict:
    old_p = scenario.phase_from.upper().replace(" ", "")
    new_p = scenario.phase_to.upper().replace(" ", "")
    subject, body, html_body = build_alert_email(
        scenario.ticker,
        scenario.nct_id,
        old_p,
        new_p,
        scenario.score,
        scenario.summary,
    )
    return {"subject": subject, "body": body, "html": html_body}
