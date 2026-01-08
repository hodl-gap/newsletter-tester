"""
Save Twitter Availability Node

Saves Layer 1 results:
- twitter_availability.json: Account status and activity metrics
- twitter_raw_cache.json: Raw tweets for Layer 2 consumption

Merges with existing availability results (incremental runs).
"""

import json
from datetime import datetime
from pathlib import Path
from typing import TypedDict
from collections import defaultdict

from src.config import get_data_dir
from src.tracking import debug_log, track_time


def _get_availability_file() -> Path:
    """Get path for twitter_availability.json."""
    return get_data_dir() / "twitter_availability.json"


def _get_cache_file() -> Path:
    """Get path for twitter_raw_cache.json."""
    return get_data_dir() / "twitter_raw_cache.json"


class SaveStatus(TypedDict):
    """Status of save operation."""
    availability_path: str
    cache_path: str
    total_accounts: int
    active_accounts: int
    inactive_accounts: int
    cached_tweets: int


def save_twitter_availability(state: dict) -> dict:
    """
    Save activity results and raw tweet cache.

    Args:
        state: Pipeline state with:
            - 'activity_results': List of AccountActivityResult dicts
            - 'raw_tweets': List of RawTweet dicts
            - 'twitter_settings': Settings dict

    Returns:
        Dict with 'save_status'
    """
    with track_time("save_twitter_availability"):
        debug_log("[NODE: save_twitter_availability] Entering")

        activity_results = state.get("activity_results", [])
        raw_tweets = state.get("raw_tweets", [])
        settings = state.get("twitter_settings", {})

        debug_log(f"[NODE: save_twitter_availability] Saving {len(activity_results)} accounts")
        debug_log(f"[NODE: save_twitter_availability] Caching {len(raw_tweets)} tweets")

        availability_file = _get_availability_file()
        cache_file = _get_cache_file()

        # Build availability JSON
        availability_data = _build_availability_json(activity_results, settings)

        # Merge with existing results
        availability_data = _merge_with_existing(availability_data, availability_file)

        # Build cache JSON
        cache_data = _build_cache_json(raw_tweets, settings)

        # Save files (get_data_dir creates the directory if needed)
        with open(availability_file, "w", encoding="utf-8") as f:
            json.dump(availability_data, f, indent=2, ensure_ascii=False)
        debug_log(f"[NODE: save_twitter_availability] Saved: {availability_file}")

        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, indent=2, ensure_ascii=False)
        debug_log(f"[NODE: save_twitter_availability] Saved: {cache_file}")

        # Calculate stats
        active_count = sum(1 for r in availability_data["results"] if r["status"] == "active")
        inactive_count = sum(1 for r in availability_data["results"] if r["status"] == "inactive")

        save_status: SaveStatus = {
            "availability_path": str(availability_file),
            "cache_path": str(cache_file),
            "total_accounts": len(availability_data["results"]),
            "active_accounts": active_count,
            "inactive_accounts": inactive_count,
            "cached_tweets": len(raw_tweets),
        }

        debug_log(f"[NODE: save_twitter_availability] Status: {save_status}")

        return {"save_status": save_status}


def _build_availability_json(activity_results: list[dict], settings: dict) -> dict:
    """
    Build the availability JSON structure.

    Args:
        activity_results: List of AccountActivityResult dicts
        settings: Twitter settings

    Returns:
        Availability data dict
    """
    timestamp = datetime.now().isoformat(timespec="seconds") + "Z"

    # Count by status
    active = sum(1 for r in activity_results if r["status"] == "active")
    inactive = sum(1 for r in activity_results if r["status"] == "inactive")
    error = sum(1 for r in activity_results if r["status"] == "error")

    return {
        "results": activity_results,
        "timestamp": timestamp,
        "total": len(activity_results),
        "active": active,
        "inactive": inactive,
        "error": error,
        "settings": {
            "inactivity_threshold_days": settings.get("inactivity_threshold_days", 14),
            "scrape_delay_seconds": settings.get("scrape_delay_seconds", 30),
        },
    }


def _merge_with_existing(new_data: dict, availability_file: Path) -> dict:
    """
    Merge new results with existing availability file.

    Updates existing entries, adds new ones. Does not remove entries
    that weren't processed in this run (allows incremental updates).

    Args:
        new_data: New availability data
        availability_file: Path to the availability file

    Returns:
        Merged availability data
    """
    if not availability_file.exists():
        debug_log("[NODE: save_twitter_availability] No existing file, creating new")
        return new_data

    try:
        with open(availability_file, "r", encoding="utf-8") as f:
            existing_data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        debug_log(f"[NODE: save_twitter_availability] Error reading existing file: {e}", "warning")
        return new_data

    # Build lookup by handle
    existing_by_handle = {r["handle"]: r for r in existing_data.get("results", [])}

    # Merge: update existing, add new
    for result in new_data["results"]:
        handle = result["handle"]
        existing_by_handle[handle] = result  # Overwrite with new data

    # Rebuild results list
    merged_results = list(existing_by_handle.values())

    # Recalculate stats
    active = sum(1 for r in merged_results if r["status"] == "active")
    inactive = sum(1 for r in merged_results if r["status"] == "inactive")
    error = sum(1 for r in merged_results if r["status"] == "error")

    merged_data = {
        "results": merged_results,
        "timestamp": new_data["timestamp"],
        "total": len(merged_results),
        "active": active,
        "inactive": inactive,
        "error": error,
        "settings": new_data["settings"],
    }

    debug_log(f"[NODE: save_twitter_availability] Merged {len(new_data['results'])} new with "
              f"{len(existing_data.get('results', []))} existing = {len(merged_results)} total")

    return merged_data


def _build_cache_json(raw_tweets: list[dict], settings: dict) -> dict:
    """
    Build the raw tweet cache JSON structure.

    Groups tweets by handle for efficient lookup in Layer 2.

    Args:
        raw_tweets: List of RawTweet dicts
        settings: Twitter settings

    Returns:
        Cache data dict
    """
    timestamp = datetime.now().isoformat(timespec="seconds") + "Z"
    cache_ttl = settings.get("cache_ttl_hours", 24)

    # Group tweets by handle
    tweets_by_handle: dict[str, list[dict]] = defaultdict(list)
    for tweet in raw_tweets:
        handle = tweet.get("handle", "")
        if handle:
            tweets_by_handle[handle].append(tweet)

    # Build accounts structure
    accounts = {}
    for handle, tweets in tweets_by_handle.items():
        accounts[handle] = {
            "handle": handle,
            "last_scraped": timestamp,
            "tweet_count": len(tweets),
            "tweets": tweets,
        }

    return {
        "timestamp": timestamp,
        "cache_ttl_hours": cache_ttl,
        "accounts": accounts,
    }
