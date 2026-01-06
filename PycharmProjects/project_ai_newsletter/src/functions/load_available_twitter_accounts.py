"""
Load Available Twitter Accounts Node

Reads Layer 1 availability results and returns only active accounts.
Used by Layer 2 to skip inactive/error accounts.
"""

import json
from pathlib import Path
from typing import TypedDict, Optional

from src.tracking import debug_log, track_time


# Input file path
DATA_DIR = Path(__file__).parent.parent.parent / "data"
AVAILABILITY_FILE = DATA_DIR / "twitter_availability.json"


class AvailableAccountInfo(TypedDict):
    """Information about an available Twitter account."""
    handle: str
    category: str
    status: str
    last_tweet_date: Optional[str]


def load_available_twitter_accounts(state: dict) -> dict:
    """
    Load accounts marked as 'active' from twitter_availability.json.

    Args:
        state: Pipeline state with optional 'handle_filter'

    Returns:
        Dict with:
            - 'available_accounts': List of AvailableAccountInfo
            - 'twitter_settings': Settings from availability file
    """
    with track_time("load_available_twitter_accounts"):
        debug_log("[NODE: load_available_twitter_accounts] Entering")

        handle_filter = state.get("handle_filter")

        # Check if availability file exists
        if not AVAILABILITY_FILE.exists():
            debug_log(
                f"[NODE: load_available_twitter_accounts] "
                f"File not found: {AVAILABILITY_FILE}. Run Layer 1 first.",
                "error"
            )
            return {
                "available_accounts": [],
                "twitter_settings": {},
            }

        # Load availability data
        try:
            with open(AVAILABILITY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            debug_log(
                f"[NODE: load_available_twitter_accounts] Error reading file: {e}",
                "error"
            )
            return {
                "available_accounts": [],
                "twitter_settings": {},
            }

        results = data.get("results", [])
        settings = data.get("settings", {})

        debug_log(f"[NODE: load_available_twitter_accounts] Loaded {len(results)} accounts from L1")

        # Filter for active accounts only
        available_accounts: list[AvailableAccountInfo] = []

        for result in results:
            handle = result.get("handle", "")
            status = result.get("status", "")

            # Skip non-active accounts
            if status != "active":
                debug_log(
                    f"[NODE: load_available_twitter_accounts] Skipping {handle}: {status}"
                )
                continue

            # Apply handle filter if provided
            if handle_filter:
                if not any(f.lower() in handle.lower() for f in handle_filter):
                    debug_log(
                        f"[NODE: load_available_twitter_accounts] "
                        f"Skipping {handle}: not in filter"
                    )
                    continue

            account_info: AvailableAccountInfo = {
                "handle": handle,
                "category": result.get("category", "unknown"),
                "status": status,
                "last_tweet_date": result.get("last_tweet_date"),
            }
            available_accounts.append(account_info)

        debug_log(
            f"[NODE: load_available_twitter_accounts] "
            f"Output: {len(available_accounts)} available accounts"
        )

        # Log which accounts are available
        for acc in available_accounts:
            debug_log(
                f"[NODE: load_available_twitter_accounts] "
                f"  - {acc['handle']} ({acc['category']})"
            )

        return {
            "available_accounts": available_accounts,
            "twitter_settings": settings,
        }
