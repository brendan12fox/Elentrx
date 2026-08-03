"""Shared classifier training utilities."""

from __future__ import annotations

import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import balanced_accuracy_score, f1_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

FEATURE_NAMES = [
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


def build_pipeline() -> Pipeline:
    return Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            (
                "clf",
                GradientBoostingClassifier(
                    n_estimators=300,
                    max_depth=4,
                    learning_rate=0.05,
                    min_samples_leaf=2,
                    subsample=0.85,
                    random_state=42,
                ),
            ),
        ]
    )


def class_balanced_weights(y: np.ndarray) -> np.ndarray:
    if len(y) == 0:
        return np.array([])
    n_pos = max(int(np.sum(y)), 1)
    n_neg = max(int(len(y) - n_pos), 1)
    w_pos = len(y) / (2 * n_pos)
    w_neg = len(y) / (2 * n_neg)
    return np.where(y == 1, w_pos, w_neg).astype(float)


def optimize_threshold(y_true: np.ndarray, proba: np.ndarray) -> float:
    """Pick threshold maximizing balanced accuracy on validation data."""
    if len(y_true) == 0 or len(set(y_true)) < 2:
        return 0.5
    best_t, best_score = 0.5, -1.0
    for t in np.arange(0.20, 0.81, 0.05):
        preds = (proba >= t).astype(int)
        bal_acc = balanced_accuracy_score(y_true, preds)
        f1 = f1_score(y_true, preds, zero_division=0)
        # Weight balanced accuracy and F1 for stable alerts
        score = 0.6 * bal_acc + 0.4 * f1
        if score > best_score:
            best_score, best_t = score, float(t)
    return best_t


def fit_classifier(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray | None = None,
    y_val: np.ndarray | None = None,
) -> tuple[Pipeline, float]:
    model = build_pipeline()
    weights = class_balanced_weights(y_train)
    model.fit(X_train, y_train, clf__sample_weight=weights)

    if X_val is not None and y_val is not None and len(y_val) > 0:
        proba = model.predict_proba(X_val)[:, 1]
        threshold = optimize_threshold(y_val, proba)
    else:
        proba = model.predict_proba(X_train)[:, 1]
        threshold = optimize_threshold(y_train, proba)

    return model, threshold
