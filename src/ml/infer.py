"""Inference for favorability classifier."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np

from src.config import FAVORABILITY_THRESHOLD, MODEL_PATH
from src.db.schema import get_connection
from src.ml.features import FeatureVector, build_features, features_to_json
from src.ml.train import train_model
from src.research.llm_agent import ResearchBrief
from src.scrape.diff import PhaseChange


@dataclass
class ScoreResult:
    probability: float
    favorable: bool
    features_json: str


def load_model_bundle(model_path: Path | None = None):
    path = model_path or MODEL_PATH
    if not path.exists():
        train_model(path)
    return joblib.load(path)


def score_change(
    change: PhaseChange,
    brief: ResearchBrief,
    threshold: float | None = None,
    news_count: int = 0,
) -> ScoreResult:
    bundle = load_model_bundle()
    model = bundle["model"]
    feature_vector = build_features(change, brief, news_count=news_count)
    X = np.array([feature_vector.values], dtype=float)
    # Align feature width if model was trained on older feature set
    target = len(bundle.get("feature_names", feature_vector.names))
    if X.shape[1] < target:
        X = np.hstack([X, np.zeros((1, target - X.shape[1]))])
    elif X.shape[1] > target:
        X = X[:, :target]
    proba = float(model.predict_proba(X)[0][1])
    cutoff = threshold
    if cutoff is None:
        cutoff = float(bundle.get("optimized_threshold", FAVORABILITY_THRESHOLD))
    favorable = proba >= cutoff
    return ScoreResult(
        probability=proba,
        favorable=favorable,
        features_json=features_to_json(feature_vector),
    )


def save_score(phase_change_id: int, result: ScoreResult) -> int:
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO classifier_scores (
                phase_change_id, probability, favorable, features_json, scored_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                phase_change_id,
                result.probability,
                1 if result.favorable else 0,
                result.features_json,
                now,
            ),
        )
        return int(cursor.lastrowid)
