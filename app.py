"""Streamlit dashboard for healthcare trial scraper."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from src.config import DATA_DIR, FAVORABILITY_THRESHOLD, get_sector_for_hour, load_sectors
from src.db.schema import get_connection, init_db
from src.ml.historical import HISTORICAL_DATASET_PATH, load_dataset

st.set_page_config(
    page_title="StonkScraper — Clinical Trial Alerter",
    page_icon="🧬",
    layout="wide",
)

init_db()


def _load_df(query: str, params: tuple = ()) -> pd.DataFrame:
    with get_connection() as conn:
        return pd.read_sql_query(query, conn, params=params)


def rotation_panel() -> None:
    sectors = load_sectors()
    now = datetime.now(timezone.utc)
    current, index = get_sector_for_hour(now.hour)

    st.subheader("Sector rotation")
    col1, col2, col3 = st.columns(3)
    col1.metric("Current sector", current["name"])
    col2.metric("Sector index", f"{index + 1} / {len(sectors)}")
    col3.metric("Full cycle", f"{len(sectors)} hours")

    schedule_rows = []
    for offset in range(len(sectors)):
        hour = (now.hour + offset) % 24
        sector = sectors[hour % len(sectors)]
        schedule_rows.append(
            {
                "offset_hours": offset,
                "utc_hour": hour,
                "sector": sector["name"],
                "active": offset == 0,
            }
        )
    st.dataframe(pd.DataFrame(schedule_rows), width="stretch", hide_index=True)


def trials_panel() -> None:
    st.subheader("Public-company trials (latest snapshot)")
    df = _load_df(
        """
        SELECT nct_id, ticker, sponsor, drug, sector_id, phase, overall_status,
               title, last_seen_at
        FROM trials
        ORDER BY last_seen_at DESC
        LIMIT 500
        """
    )
    if df.empty:
        st.info("No trials in snapshot yet. The hourly job will populate this table.")
    else:
        st.dataframe(df, width="stretch", hide_index=True)


def changes_panel() -> None:
    st.subheader("Phase changes & research briefs")
    df = _load_df(
        """
        SELECT
            pc.id,
            pc.detected_at,
            pc.ticker,
            pc.nct_id,
            pc.change_type,
            pc.old_phase,
            pc.new_phase,
            pc.old_status,
            pc.new_status,
            rb.summary,
            rb.analyst_tone,
            cs.probability,
            cs.favorable
        FROM phase_changes pc
        LEFT JOIN research_briefs rb ON rb.phase_change_id = pc.id
        LEFT JOIN classifier_scores cs ON cs.phase_change_id = pc.id
        ORDER BY pc.detected_at DESC
        LIMIT 100
        """
    )
    if df.empty:
        st.info("No phase changes detected yet.")
        return

    st.dataframe(df, width="stretch", hide_index=True)

    for _, row in df.head(10).iterrows():
        with st.expander(f"{row['ticker']} {row['nct_id']} — {row['change_type']}"):
            st.write(row.get("summary") or "No brief yet.")
            st.caption(
                f"Score: {row.get('probability', 'n/a')} | "
                f"Tone: {row.get('analyst_tone', 'n/a')} | "
                f"Favorable: {row.get('favorable', 'n/a')}"
            )


def alerts_panel() -> None:
    st.subheader("Alert history")
    df = _load_df(
        """
        SELECT sent_at, ticker, nct_id, message
        FROM alerts
        ORDER BY sent_at DESC
        LIMIT 100
        """
    )
    if df.empty:
        st.info("No alerts sent yet.")
    else:
        st.dataframe(df, width="stretch", hide_index=True)


def runs_panel() -> None:
    st.subheader("Hourly run log")
    df = _load_df(
        """
        SELECT started_at, finished_at, sector_name, trials_fetched, trials_matched,
               changes_detected, alerts_sent, status, error
        FROM run_log
        ORDER BY started_at DESC
        LIMIT 50
        """
    )
    if df.empty:
        st.info("No runs logged yet.")
    else:
        st.dataframe(df, width="stretch", hide_index=True)


def evaluation_panel() -> None:
    st.subheader("Historical classifier evaluation")
    report_path = DATA_DIR / "evaluation_report.json"

    from src.ml.progress import load_progress

    live = load_progress()
    if live and live.get("status") == "running":
        st.info("Training in progress…")
        c1, c2, c3, c4 = st.columns(4)
        processed = live.get("processed", 0)
        total = live.get("total_events_fetched", 0)
        c1.metric("Events", f"{processed}/{total}")
        c2.metric("Samples", live.get("samples_built", 0))
        c3.metric("OpenAI searches", live.get("openai_searches", live.get("serper_calls", 0)))
        eta = live.get("eta_seconds")
        c4.metric("ETA", f"{int(eta // 60)}m" if eta else "—")
        if live.get("recent_events"):
            st.dataframe(
                pd.DataFrame(live["recent_events"])[
                    ["at", "ticker", "nct_id", "event_date", "news_count", "label"]
                ],
                width="stretch",
                hide_index=True,
            )
        st.code("python -m src.ml.watch_progress", language="bash")

    st.markdown(
        "Point-in-time backtest: news is cut off at each trial **event date**, "
        "labels use **5-day forward returns** after the event (no lookahead in features)."
    )

    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        metrics = report.get("metrics", {})
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Accuracy", f"{metrics.get('accuracy', 0):.1%}" if metrics.get("accuracy") is not None else "n/a")
        m2.metric("F1", f"{metrics.get('f1', 0):.2f}" if metrics.get("f1") is not None else "n/a")
        m3.metric("ROC-AUC", f"{metrics.get('roc_auc', 0):.2f}" if metrics.get("roc_auc") is not None else "n/a")
        m4.metric("Baseline", f"{metrics.get('baseline_accuracy', 0):.1%}" if metrics.get("baseline_accuracy") is not None else "n/a")

        st.json(report.get("methodology", {}))
        ds = report.get("dataset", {})
        st.write(
            f"Train: {ds.get('train_date_range', [])} | "
            f"Test: {ds.get('test_date_range', [])} | "
            f"Samples: {ds.get('total_samples', 0)}"
        )
        if report.get("classification_report"):
            st.write("Classification report (test set)")
            st.json(report["classification_report"])
    else:
        st.info("No evaluation report yet. Run the historical batch below.")

    samples = load_dataset()
    if samples:
        st.write(f"Cached historical dataset: {len(samples)} samples")
        df = pd.DataFrame([s.to_dict() for s in samples])
        st.dataframe(
            df[["event_date", "ticker", "nct_id", "label", "forward_return_5d", "news_count", "analyst_tone"]],
            width="stretch",
            hide_index=True,
        )
    elif HISTORICAL_DATASET_PATH.exists():
        st.warning("Dataset file exists but could not be loaded.")

    st.code(
        "python -m src.ml.watch_progress          # live timeline in terminal\n"
        "python -m src.ml.evaluate --rebuild --max-events 200\n"
        "python -m src.ml.evaluate --rebuild --max-events 100 --use-llm",
        language="bash",
    )


def config_panel() -> None:
    st.subheader("Configuration")
    st.write(f"Favorability threshold: `{FAVORABILITY_THRESHOLD}`")
    st.write(f"Alert phone configured: `{bool(os.getenv('ALERT_PHONE'))}`")
    st.write(f"Twilio configured: `{bool(os.getenv('TWILIO_ACCOUNT_SID'))}`")
    st.write(f"OpenAI configured: `{bool(os.getenv('OPENAI_API_KEY'))}`")
    st.caption("News + research via **OpenAI Responses API web_search** (no Serper/RSS needed).")

    sectors = load_sectors()
    st.json({"sectors": [s["name"] for s in sectors]})


def main() -> None:
    st.title("StonkScraper")
    st.caption("Healthcare clinical trial phase tracker — public sponsors only, sector rotation at :58 UTC")

    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(
        ["Rotation", "Trials", "Changes", "Alerts", "Runs", "Evaluation", "Config"]
    )

    with tab1:
        rotation_panel()
    with tab2:
        trials_panel()
    with tab3:
        changes_panel()
    with tab4:
        alerts_panel()
    with tab5:
        runs_panel()
    with tab6:
        evaluation_panel()
    with tab7:
        config_panel()


if __name__ == "__main__":
    main()
