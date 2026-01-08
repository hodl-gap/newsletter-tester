"""
Load Cached Tweets Node

Reads raw tweet cache from Layer 1 and returns tweets for available accounts.
Checks cache freshness and warns if stale.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from src.config import get_data_dir
from src.tracking import debug_log, track_time


def _get_cache_file() -> Path:
    """Get path for twitter_raw_cache.json."""
    return get_data_dir() / "twitter_raw_cache.json"


def load_cached_tweets(state: dict) -> dict:
    """
    Load cached tweets from twitter_raw_cache.json.

    Args:
        state: Pipeline state with:
            - 'available_accounts': List of AvailableAccountInfo from L1

    Returns:
        Dict with 'raw_tweets' list
    """
    with track_time("load_cached_tweets"):
        debug_log("[NODE: load_cached_tweets] Entering")

        available_accounts = state.get("available_accounts", [])
        available_handles = {acc["handle"] for acc in available_accounts}

        debug_log(f"[NODE: load_cached_tweets] Loading tweets for {len(available_handles)} accounts")

        cache_file = _get_cache_file()

        # Check if cache file exists
        if not cache_file.exists():
            debug_log(
                f"[NODE: load_cached_tweets] Cache not found: {cache_file}. Run Layer 1 first.",
                "error"
            )
            return {"raw_tweets": []}

        # Load cache data
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cache_data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            debug_log(f"[NODE: load_cached_tweets] Error reading cache: {e}", "error")
            return {"raw_tweets": []}

        # Check cache freshness
        cache_timestamp = cache_data.get("timestamp", "")
        cache_ttl_hours = cache_data.get("cache_ttl_hours", 24)

        if cache_timestamp:
            _check_cache_freshness(cache_timestamp, cache_ttl_hours)

        # Extract tweets for available accounts only
        accounts_data = cache_data.get("accounts", {})
        raw_tweets: list[dict] = []

        for handle in available_handles:
            account_cache = accounts_data.get(handle)

            if not account_cache:
                debug_log(
                    f"[NODE: load_cached_tweets] No cache for {handle}",
                    "warning"
                )
                continue

            tweets = account_cache.get("tweets", [])
            raw_tweets.extend(tweets)

            debug_log(
                f"[NODE: load_cached_tweets] Loaded {len(tweets)} tweets for {handle}"
            )

        debug_log(f"[NODE: load_cached_tweets] Output: {len(raw_tweets)} total tweets")

        return {"raw_tweets": raw_tweets}


def _check_cache_freshness(timestamp_str: str, ttl_hours: int) -> None:
    """
    Check if cache is within TTL and log warning if stale.

    Args:
        timestamp_str: ISO timestamp of cache creation
        ttl_hours: Cache time-to-live in hours
    """
    try:
        # Parse ISO timestamp (handle both with and without Z suffix)
        ts = timestamp_str.rstrip("Z")
        cache_time = datetime.fromisoformat(ts)
        now = datetime.now()

        age = now - cache_time
        age_hours = age.total_seconds() / 3600

        if age_hours > ttl_hours:
            debug_log(
                f"[NODE: load_cached_tweets] WARNING: Cache is stale "
                f"({age_hours:.1f}h old, TTL={ttl_hours}h). Consider re-running Layer 1.",
                "warning"
            )
        else:
            debug_log(
                f"[NODE: load_cached_tweets] Cache is fresh "
                f"({age_hours:.1f}h old, TTL={ttl_hours}h)"
            )

    except (ValueError, TypeError) as e:
        debug_log(
            f"[NODE: load_cached_tweets] Could not parse cache timestamp: {e}",
            "warning"
        )
