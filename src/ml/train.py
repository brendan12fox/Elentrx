"""Train favorability classifier on historical phase transitions."""

from __future__ import annotations

import argparse
import contextlib
import io
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.model_selection import train_test_split

from src.config import MODEL_PATH, PHASE_ORDER, ensure_dirs
from src.db.schema import init_db
from src.ml.features import build_features
from src.ml.historical import HISTORICAL_DATASET_PATH, load_dataset
from src.ml.modeling import FEATURE_NAMES, fit_classifier
from src.research.llm_agent import ResearchBrief
from src.scrape.diff import PhaseChange

TRAINING_TICKERS = [
    "PFE", "MRK", "JNJ", "ABBV", "LLY", "BMY", "AMGN", "GILD", "REGN", "VRTX",
    "MRNA", "BIIB", "NVS", "SNY", "GSK", "NVO", "TAK", "INCY", "BMRN", "SRPT",
    "ALNY", "EXEL", "IONS", "NBIX", "CRSP", "JAZZ", "ALKS", "ACAD", "INSM", "UTHR",
]

logging.getLogger("yfinance").setLevel(logging.CRITICAL)


def _synthetic_brief(change_type: str, phase_delta: float) -> ResearchBrief:
    tone = "bullish" if phase_delta > 0 and change_type != "status_negative" else "neutral"
    if change_type == "status_negative":
        tone = "bearish"
    return ResearchBrief(
        summary="Historical bootstrap record",
        catalysts=["data readout"] if phase_delta > 0 else [],
        safety_signals=["adverse event"] if change_type == "status_negative" else [],
        endpoints=["primary endpoint"],
        analyst_tone=tone,
        risk_flags=["trial delay"] if change_type == "status_negative" else [],
        raw_json={},
    )


def _download_history(ticker: str, start: str, end: str) -> pd.DataFrame:
    with contextlib.redirect_stderr(io.StringIO()):
        return yf.download(
            ticker,
            start=start,
            end=end,
            progress=False,
            auto_adjust=True,
            threads=False,
        )


def _phase_delta(old_phase: str | None, new_phase: str | None) -> float:
    old_rank = PHASE_ORDER.get(old_phase or "", -1)
    new_rank = PHASE_ORDER.get(new_phase or "", -1)
    return float(new_rank - old_rank)


def bootstrap_training_rows(limit: int = 500) -> tuple[np.ndarray, np.ndarray]:
    tickers = TRAINING_TICKERS[: min(limit, len(TRAINING_TICKERS))]
    rows_x: list[list[float]] = []
    rows_y: list[int] = []

    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=730)

    for ticker in tickers:
        try:
            hist = _download_history(ticker, start.isoformat(), end.isoformat())
        except Exception:
            continue
        if hist.empty:
            continue

        if isinstance(hist.columns, pd.MultiIndex):
            closes = hist["Close"].squeeze()
        else:
            closes = hist["Close"]
        closes = pd.Series(closes).dropna()
        if len(closes) < 30:
            continue

        returns = pd.Series(closes).pct_change().dropna()
        step = max(1, len(returns) // 15)
        for idx in range(5, len(returns) - 5, step):
            forward = float(np.nansum(returns.iloc[idx : idx + 5].to_numpy(dtype=float)))
            label = 1 if forward > 0.02 else 0
            change_type = "phase_upgrade" if label == 1 else "status_negative"
            old_phase, new_phase = "PHASE2", "PHASE3" if label == 1 else "PHASE2"
            change = PhaseChange(
                nct_id=f"BOOT-{ticker}-{idx}",
                ticker=ticker,
                sponsor=ticker,
                drug="bootstrap",
                sector_id="other",
                old_phase=old_phase,
                new_phase=new_phase,
                old_status="RECRUITING",
                new_status="COMPLETED" if label == 1 else "TERMINATED",
                change_type=change_type,
            )
            brief = _synthetic_brief(change_type, _phase_delta(old_phase, new_phase))
            news_count = 2 if label == 1 else 0
            rows_x.append(build_features(change, brief, news_count=news_count).values)
            rows_y.append(label)

    return np.array(rows_x, dtype=float), np.array(rows_y, dtype=int)


def load_historical_arrays() -> tuple[np.ndarray, np.ndarray]:
    samples = load_dataset()
    if not samples:
        return np.array([]), np.array([])
    X = np.array([s.features for s in samples], dtype=float)
    y = np.array([s.label for s in samples], dtype=int)
    target = len(FEATURE_NAMES)
    if X.shape[1] < target:
        pad = np.zeros((X.shape[0], target - X.shape[1]), dtype=float)
        X = np.hstack([X, pad])
    elif X.shape[1] > target:
        X = X[:, :target]
    return X, y


def train_model(output_path: Path | None = None, prefer_historical: bool = True) -> Path:
    ensure_dirs()
    init_db()

    X_hist, y_hist = load_historical_arrays() if prefer_historical else (np.array([]), np.array([]))
    X_boot, y_boot = bootstrap_training_rows()

    if len(X_hist) >= 12:
        X = np.vstack([X_hist, X_boot]) if len(X_boot) else X_hist
        y = np.concatenate([y_hist, y_boot]) if len(y_boot) else y_hist
        mode = "historical+bootstrap"
    else:
        X, y = X_boot, y_boot
        mode = "bootstrap"

    if len(y) < 4:
        raise RuntimeError("Not enough training samples. Run: python -m src.ml.evaluate --rebuild")

    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y if len(set(y)) > 1 else None
    )
    model, threshold = fit_classifier(X_train, y_train, X_val, y_val)
    score = float(model.score(X_val, y_val)) if len(y_val) else float(model.score(X_train, y_train))

    path = output_path or MODEL_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": model,
            "feature_names": FEATURE_NAMES,
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "holdout_accuracy": score,
            "optimized_threshold": threshold,
            "samples": int(len(y)),
            "training_mode": mode,
        },
        path,
    )
    print(f"Trained on {len(y)} samples ({mode}), holdout accuracy={score:.1%}, threshold={threshold:.2f}")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Train favorability classifier")
    parser.add_argument("--output", type=Path, default=MODEL_PATH)
    parser.add_argument("--bootstrap-only", action="store_true")
    args = parser.parse_args()
    path = train_model(args.output, prefer_historical=not args.bootstrap_only)
    print(f"Model saved to {path}")


if __name__ == "__main__":
    main()
