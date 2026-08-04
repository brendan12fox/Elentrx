"""Refresh the shared daily watchlist digest (run via cron or manually)."""

from __future__ import annotations

import argparse
import json

from src.research.watchlist import build_daily_digest, cache_is_fresh, load_digest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build shared daily watchlist digest")
    parser.add_argument("--force", action="store_true", help="Ignore cache TTL and rebuild")
    args = parser.parse_args()

    if not args.force:
        existing = load_digest()
        if existing and cache_is_fresh(existing):
            print(f"Cache fresh ({existing['generated_at']}), skipping rebuild.")
            print(json.dumps({"trial_count": existing.get("trial_count", 0), "cache_key": existing.get("cache_key")}))
            return

    digest = build_daily_digest(force=True)
    print(
        f"Built watchlist: {digest.get('trial_count', 0)} trials, "
        f"sector={digest.get('sector_name')}, key={digest.get('cache_key')}"
    )


if __name__ == "__main__":
    main()
