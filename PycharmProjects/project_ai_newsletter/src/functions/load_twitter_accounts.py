"""
Load Twitter Accounts Node

Reads Twitter account handles from configuration file for scraping.
"""

import json
from pathlib import Path
from typing import TypedDict

from src.config import get_twitter_accounts_path
from src.tracking import debug_log, track_time


class TwitterAccountInfo(TypedDict):
    """Information about a Twitter account to scrape."""
    handle: str         # e.g., "@a16z"
    category: str       # e.g., "VC/funding"


class TwitterSettings(TypedDict):
    """Settings for Twitter scraping."""
    scrape_delay_seconds: int
    max_age_hours: int


def load_twitter_accounts(state: dict) -> dict:
    """
    Load Twitter accounts from twitter_accounts.json.

    Args:
        state: Pipeline state. Optional 'handle_filter' list to filter accounts.

    Returns:
        Dict with 'twitter_accounts' list and 'twitter_settings' dict
    """
    with track_time("load_twitter_accounts"):
        debug_log("[NODE: load_twitter_accounts] Entering")

        # Check for handle filter
        handle_filter = state.get("handle_filter", None)
        if handle_filter:
            debug_log(f"[NODE: load_twitter_accounts] Filtering for handles: {handle_filter}")

        # Read Twitter accounts config
        data_path = get_twitter_accounts_path()
        if not data_path.exists():
            debug_log("[NODE: load_twitter_accounts] ERROR: twitter_accounts.json not found", "error")
            return {"twitter_accounts": [], "twitter_settings": {}}

        with open(data_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        debug_log(f"[NODE: load_twitter_accounts] Loaded {len(data.get('accounts', []))} accounts")

        # Extract settings
        settings: TwitterSettings = data.get("settings", {
            "scrape_delay_seconds": 30,
            "max_age_hours": 24,
        })

        # Filter accounts
        twitter_accounts: list[TwitterAccountInfo] = []

        for account in data.get("accounts", []):
            handle = account.get("handle", "")
            if not handle:
                continue

            # Apply handle filter if specified
            if handle_filter:
                # Check if handle matches any filter (case-insensitive)
                handle_lower = handle.lower()
                if not any(f.lower() in handle_lower for f in handle_filter):
                    continue

            account_info: TwitterAccountInfo = {
                "handle": handle,
                "category": account.get("category", ""),
            }
            twitter_accounts.append(account_info)

        debug_log(f"[NODE: load_twitter_accounts] Found {len(twitter_accounts)} accounts to scrape")
        debug_log(f"[NODE: load_twitter_accounts] Output: {[a['handle'] for a in twitter_accounts]}")

        return {
            "twitter_accounts": twitter_accounts,
            "twitter_settings": settings,
        }
