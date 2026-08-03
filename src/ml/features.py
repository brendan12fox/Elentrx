"""Feature engineering for favorability classifier."""

from __future__ import annotations

import json
from dataclasses import dataclass

from src.config import PHASE_ORDER
from src.research.llm_agent import ResearchBrief
from src.scrape.diff import PhaseChange

TONE_MAP = {"bullish": 1.0, "neutral": 0.0, "bearish": -1.0}


@dataclass
class FeatureVector:
    values: list[float]
    names: list[str]


def _phase_delta(old_phase: str | None, new_phase: str | None) -> float:
    old_rank = PHASE_ORDER.get(old_phase or "", -1)
    new_rank = PHASE_ORDER.get(new_phase or "", -1)
    return float(new_rank - old_rank)


def build_features(
    change: PhaseChange,
    brief: ResearchBrief,
    news_count: int = 0,
) -> FeatureVector:
    tone = TONE_MAP.get(brief.analyst_tone.lower(), 0.0)
    new_rank = float(PHASE_ORDER.get(change.new_phase or "", -1))
    names = [
        "phase_delta",
        "new_phase_rank",
        "is_phase_upgrade",
        "is_status_completed",
        "is_status_negative",
        "is_phase3",
        "num_catalysts",
        "num_safety_signals",
        "num_risk_flags",
        "analyst_tone_score",
        "summary_length",
        "has_drug_name",
        "news_count",
        "num_endpoints",
    ]
    values = [
        _phase_delta(change.old_phase, change.new_phase),
        new_rank,
        1.0 if change.change_type == "phase_upgrade" else 0.0,
        1.0 if change.change_type == "status_completed" else 0.0,
        1.0 if change.change_type == "status_negative" else 0.0,
        1.0 if change.new_phase == "PHASE3" else 0.0,
        float(len(brief.catalysts)),
        float(len(brief.safety_signals)),
        float(len(brief.risk_flags)),
        tone,
        float(len(brief.summary)),
        1.0 if change.drug else 0.0,
        float(news_count),
        float(len(brief.endpoints)),
    ]
    return FeatureVector(values=values, names=names)


def features_to_dict(feature_vector: FeatureVector) -> dict[str, float]:
    return dict(zip(feature_vector.names, feature_vector.values, strict=True))


def features_to_json(feature_vector: FeatureVector) -> str:
    return json.dumps(features_to_dict(feature_vector))
