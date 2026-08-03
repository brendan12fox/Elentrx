"""Watch live training progress."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime

from src.ml.progress import PROGRESS_PATH, load_progress


def _fmt_seconds(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    seconds = int(seconds)
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def print_progress(data: dict) -> None:
    processed = data.get("processed", 0)
    total = data.get("total_events_fetched", 0)
    built = data.get("samples_built", 0)
    pct = (processed / total * 100) if total else 0

    print("\033[2J\033[H", end="")  # clear screen
    print("=" * 60)
    print("  StonkScraper — Training Progress")
    print("=" * 60)
    print(f"  Status:   {data.get('status', '?')}  |  Phase: {data.get('phase', '?')}")
    print(f"  Started:  {data.get('started_at', '?')}")
    print(f"  Updated:  {data.get('updated_at', '?')}")
    print("-" * 60)
    print(f"  Events:   {processed}/{total}  ({pct:.0f}%)")
    print(f"  Samples:  {built} built  |  {data.get('skipped_no_return', 0)} skipped (no price data)")
    print(f"  News:     {data.get('news_with_articles', 0)} events with articles")
    print(f"  Serper:   {data.get('serper_calls', 0)} API calls this month")
    print(f"  Elapsed:  {_fmt_seconds(data.get('elapsed_seconds'))}  |  ETA: {_fmt_seconds(data.get('eta_seconds'))}")
    print(f"  Rate:     {data.get('rate_per_minute', '—')} events/min")
    print("-" * 60)

    current = data.get("current")
    if current:
        print(f"  Current:  {current.get('ticker')} {current.get('nct_id')}  ({current.get('event_date')})")
        print(f"            news={current.get('news_count')}  label={'favorable' if current.get('label') else 'unfavorable'}")

    recent = data.get("recent_events", [])[-8:]
    if recent:
        print("-" * 60)
        print("  Recent timeline:")
        for ev in recent:
            ts = ev.get("at", "")[:19].replace("T", " ")
            tag = "✓" if ev.get("label") else "·"
            print(
                f"    {ts}  {tag} {ev.get('ticker'):<6} {ev.get('nct_id')}  "
                f"news={ev.get('news_count')}  {ev.get('event_date')}"
            )

    if data.get("status") == "error":
        print(f"\n  ERROR: {data.get('error')}")
    elif data.get("status") == "complete":
        print(f"\n  Done — {built} samples saved.")

    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="Watch training progress")
    parser.add_argument("--once", action="store_true", help="Print once and exit")
    parser.add_argument("--interval", type=float, default=3.0, help="Refresh seconds")
    args = parser.parse_args()

    if args.once:
        data = load_progress()
        if not data:
            print(f"No progress file yet at {PROGRESS_PATH}")
            print("Start training: python -m src.ml.evaluate --rebuild --max-events 200 ...")
            return
        print_progress(data)
        return

    print(f"Watching {PROGRESS_PATH}  (Ctrl+C to stop)\n")
    try:
        while True:
            data = load_progress()
            if data:
                print_progress(data)
                if data.get("status") in {"complete", "error"}:
                    break
            else:
                print("Waiting for training to start...")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped watching.")


if __name__ == "__main__":
    main()
