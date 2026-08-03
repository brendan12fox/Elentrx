"""Temporal train/test evaluation for the favorability classifier."""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta, timezone

import joblib
import numpy as np
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from src.config import DATA_DIR, MODEL_PATH, ensure_dirs
from src.ml.historical import (
    HISTORICAL_DATASET_PATH,
    build_historical_dataset,
    dataset_to_arrays,
    load_dataset,
    save_dataset,
)
from src.ml.modeling import FEATURE_NAMES, fit_classifier

EVAL_REPORT_PATH = DATA_DIR / "evaluation_report.json"


def _align_features(X: np.ndarray) -> np.ndarray:
    """Pad or trim feature columns to match current FEATURE_NAMES length."""
    target = len(FEATURE_NAMES)
    if X.shape[1] == target:
        return X
    if X.shape[1] < target:
        pad = np.zeros((X.shape[0], target - X.shape[1]), dtype=float)
        return np.hstack([X, pad])
    return X[:, :target]


def temporal_three_way_split(
    X: np.ndarray,
    y: np.ndarray,
    dates: list[str],
    train_ratio: float = 0.7,
    val_ratio: float = 0.15,
) -> dict:
    n = len(y)
    train_end = max(1, int(n * train_ratio))
    val_end = max(train_end + 1, int(n * (train_ratio + val_ratio)))
    if val_end >= n:
        val_end = n - 1
    return {
        "X_train": X[:train_end],
        "y_train": y[:train_end],
        "X_val": X[train_end:val_end],
        "y_val": y[train_end:val_end],
        "X_test": X[val_end:],
        "y_test": y[val_end:],
        "train_dates": dates[:train_end],
        "val_dates": dates[train_end:val_end],
        "test_dates": dates[val_end:],
    }


def score_predictions(y_true: np.ndarray, proba: np.ndarray, threshold: float) -> dict:
    preds = (proba >= threshold).astype(int)
    metrics: dict = {
        "threshold": threshold,
        "accuracy": float(accuracy_score(y_true, preds)),
        "precision": float(precision_score(y_true, preds, zero_division=0)),
        "recall": float(recall_score(y_true, preds, zero_division=0)),
        "f1": float(f1_score(y_true, preds, zero_division=0)),
    }
    if len(set(y_true)) > 1:
        metrics["roc_auc"] = float(roc_auc_score(y_true, proba))
    else:
        metrics["roc_auc"] = None
    metrics["confusion_matrix"] = confusion_matrix(y_true, preds).tolist()
    metrics["classification_report"] = classification_report(
        y_true, preds, zero_division=0, output_dict=True
    )
    majority = int(np.round(np.mean(y_true))) if len(y_true) else 0
    baseline_preds = np.full_like(y_true, majority)
    metrics["baseline_accuracy"] = float(accuracy_score(y_true, baseline_preds))
    return metrics


def run_evaluation(
    max_events: int = 200,
    train_ratio: float = 0.7,
    val_ratio: float = 0.15,
    rebuild: bool = False,
    use_llm: bool = False,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict:
    ensure_dirs()

    samples = load_dataset()
    if rebuild or not samples:
        end = end_date or (date.today() - timedelta(days=20))
        start = start_date or (end - timedelta(days=365 * 4))
        samples = build_historical_dataset(
            start_date=start,
            end_date=end,
            max_events=max_events,
            use_llm=use_llm,
        )
        save_dataset(samples)

    X, y, dates = dataset_to_arrays(samples)
    X = _align_features(X)

    if len(samples) < 12:
        return {
            "error": f"Need at least 12 labeled samples, got {len(samples)}. "
            "Try increasing --max-events or widening the date range.",
            "samples": len(samples),
        }

    split = temporal_three_way_split(X, y, dates, train_ratio, val_ratio)
    model, threshold = fit_classifier(
        split["X_train"],
        split["y_train"],
        split["X_val"],
        split["y_val"],
    )

    test_proba = model.predict_proba(split["X_test"])[:, 1] if len(split["y_test"]) else np.array([])
    test_metrics = (
        score_predictions(split["y_test"], test_proba, threshold)
        if len(split["y_test"])
        else {"error": "empty test set"}
    )

    val_proba = model.predict_proba(split["X_val"])[:, 1] if len(split["y_val"]) else np.array([])
    val_metrics = (
        score_predictions(split["y_val"], val_proba, threshold)
        if len(split["y_val"])
        else {}
    )

    # Retrain on train+val for production deployment
    X_prod = np.vstack([split["X_train"], split["X_val"]]) if len(split["X_val"]) else split["X_train"]
    y_prod = np.concatenate([split["y_train"], split["y_val"]]) if len(split["y_val"]) else split["y_train"]
    prod_model, prod_threshold = fit_classifier(X_prod, y_prod)

    report = {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "methodology": {
            "split": "temporal 70/15/15 (train/val/test)",
            "train_ratio": train_ratio,
            "val_ratio": val_ratio,
            "news_cutoff": "articles on or before event_date only",
            "label": "5-day forward return >= 2% after event_date",
            "use_llm": use_llm,
            "class_balancing": "sample weights",
            "threshold_tuning": "balanced accuracy + F1 on validation set",
        },
        "dataset": {
            "total_samples": len(samples),
            "train_date_range": [split["train_dates"][0], split["train_dates"][-1]]
            if split["train_dates"]
            else [],
            "val_date_range": [split["val_dates"][0], split["val_dates"][-1]]
            if split["val_dates"]
            else [],
            "test_date_range": [split["test_dates"][0], split["test_dates"][-1]]
            if split["test_dates"]
            else [],
            "positive_rate": float(np.mean(y)),
        },
        "metrics": {
            **{k: v for k, v in test_metrics.items() if k != "classification_report"},
            "val_f1": val_metrics.get("f1"),
            "optimized_threshold": threshold,
            "production_threshold": prod_threshold,
            "train_size": int(len(split["y_train"])),
            "val_size": int(len(split["y_val"])),
            "test_size": int(len(split["y_test"])),
        },
        "classification_report": test_metrics.get("classification_report"),
    }

    EVAL_REPORT_PATH.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    joblib.dump(
        {
            "model": prod_model,
            "feature_names": FEATURE_NAMES,
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "holdout_accuracy": test_metrics.get("accuracy"),
            "holdout_f1": test_metrics.get("f1"),
            "optimized_threshold": prod_threshold,
            "samples": int(len(y_prod)),
            "eval_report": str(EVAL_REPORT_PATH),
            "training_mode": "historical_temporal_balanced",
        },
        MODEL_PATH,
    )

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Historical batch evaluation with temporal split")
    parser.add_argument("--rebuild", action="store_true", help="Rebuild dataset from CT.gov + news")
    parser.add_argument("--max-events", type=int, default=200)
    parser.add_argument("--train-ratio", type=float, default=0.7)
    parser.add_argument("--val-ratio", type=float, default=0.15)
    parser.add_argument("--use-llm", action="store_true", default=True, help="Use OpenAI web search + LLM (default: on)")
    parser.add_argument("--no-llm", action="store_true", help="Skip OpenAI; use heuristics only")
    parser.add_argument("--start-date", type=str, default=None, help="YYYY-MM-DD")
    parser.add_argument("--end-date", type=str, default=None, help="YYYY-MM-DD")
    args = parser.parse_args()

    start = datetime.strptime(args.start_date, "%Y-%m-%d").date() if args.start_date else None
    end = datetime.strptime(args.end_date, "%Y-%m-%d").date() if args.end_date else None

    report = run_evaluation(
        max_events=args.max_events,
        train_ratio=args.train_ratio,
        val_ratio=args.val_ratio,
        rebuild=args.rebuild,
        use_llm=not args.no_llm,
        start_date=start,
        end_date=end,
    )

    print(json.dumps({k: v for k, v in report.items() if k != "classification_report"}, indent=2))
    if "error" not in report:
        print(f"\nFull report saved to {EVAL_REPORT_PATH}")
        print(f"Production model saved to {MODEL_PATH}")


if __name__ == "__main__":
    main()
