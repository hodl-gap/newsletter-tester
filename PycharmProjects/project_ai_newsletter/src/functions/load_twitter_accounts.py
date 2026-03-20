"""
Load Twitter Accounts Node

Reads Twitter account handles from configuration file for scraping.
Supports both single-config and multi-config loading.
"""

import json
from pathlib import Path
from typing import TypedDict

from src.config import get_twitter_accounts_path, CONFIGS_DIR
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


# =============================================================================
# Multi-Config Support
# =============================================================================

def load_multi_config_twitter_accounts(
    configs: list[str],
    handle_filter: list[str] | None = None,
) -> tuple[list[TwitterAccountInfo], dict[str, set[str]], TwitterSettings]:
    """
    Load and deduplicate Twitter accounts from multiple configs.

    Handles appearing in multiple configs are scraped once. First occurrence
    wins for metadata (category).

    Args:
        configs: List of config names (e.g., ["business_news", "ai_tips"])
        handle_filter: Optional filter for specific handles

    Returns:
        Tuple of:
            - deduped_accounts: List of unique account dicts (first occurrence wins)
            - config_handle_map: Dict mapping config name -> set of handles for that config
            - merged_settings: Settings merged from all configs (most conservative delays)
    """
    debug_log(f"[load_multi_config_twitter_accounts] Loading from configs: {configs}")

    deduped_accounts: list[TwitterAccountInfo] = []
    seen_handles: set[str] = set()
    config_handle_map: dict[str, set[str]] = {}

    # Collect all scrape delays to use most conservative
    all_delay_mins: list[int] = []
    all_delay_maxs: list[int] = []
    all_max_age_hours: list[int] = []

    for config_name in configs:
        config_path = CONFIGS_DIR / config_name / "twitter_accounts.json"

        if not config_path.exists():
            debug_log(
                f"[load_multi_config_twitter_accounts] No twitter_accounts.json for config '{config_name}'",
                "warning"
            )
            config_handle_map[config_name] = set()
            continue

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            debug_log(
                f"[load_multi_config_twitter_accounts] Error reading {config_path}: {e}",
                "error"
            )
            config_handle_map[config_name] = set()
            continue

        # Collect settings
        settings = data.get("settings", {})
        if "scrape_delay_min" in settings:
            all_delay_mins.append(settings["scrape_delay_min"])
        if "scrape_delay_max" in settings:
            all_delay_maxs.append(settings["scrape_delay_max"])
        if "max_age_hours" in settings:
            all_max_age_hours.append(settings["max_age_hours"])

        # Process accounts
        config_handles: set[str] = set()
        accounts = data.get("accounts", [])

        for account in accounts:
            handle = account.get("handle", "")
            if not handle:
                continue

            # Normalize handle (ensure @ prefix)
            if not handle.startswith("@"):
                handle = f"@{handle}"

            # Apply handle filter if specified
            if handle_filter:
                handle_lower = handle.lower()
                if not any(f.lower() in handle_lower for f in handle_filter):
                    continue

            # Track handle for this config
            config_handles.add(handle)

            # Add to deduped list if not seen before (first occurrence wins)
            if handle not in seen_handles:
                seen_handles.add(handle)
                account_info: TwitterAccountInfo = {
                    "handle": handle,
                    "category": account.get("category", ""),
                }
                deduped_accounts.append(account_info)
                debug_log(
                    f"[load_multi_config_twitter_accounts] Added {handle} from {config_name}"
                )
            else:
                debug_log(
                    f"[load_multi_config_twitter_accounts] Skipping duplicate {handle} "
                    f"(already added from earlier config)"
                )

        config_handle_map[config_name] = config_handles
        debug_log(
            f"[load_multi_config_twitter_accounts] Config '{config_name}': "
            f"{len(config_handles)} handles"
        )

    # Merge settings (use most conservative delays)
    merged_settings: TwitterSettings = {
        "scrape_delay_min": max(all_delay_mins) if all_delay_mins else 55,
        "scrape_delay_max": max(all_delay_maxs) if all_delay_maxs else 65,
        "max_age_hours": max(all_max_age_hours) if all_max_age_hours else 24,
        "inactivity_threshold_days": 14,
        "cache_ttl_hours": 24,
    }

    debug_log(
        f"[load_multi_config_twitter_accounts] Total: {len(deduped_accounts)} unique handles "
        f"across {len(configs)} configs"
    )
    debug_log(f"[load_multi_config_twitter_accounts] Merged settings: {merged_settings}")

    return deduped_accounts, config_handle_map, merged_settings


def load_multi_config_twitter_accounts_node(state: dict) -> dict:
    """
    LangGraph node wrapper for load_multi_config_twitter_accounts.

    Args:
        state: Pipeline state with 'configs' list and optional 'handle_filter'

    Returns:
        Dict with 'twitter_accounts', 'config_handle_map', 'twitter_settings'
    """
    with track_time("load_multi_config_twitter_accounts"):
        debug_log("[NODE: load_multi_config_twitter_accounts] Entering")

        configs = state.get("configs", [])
        handle_filter = state.get("handle_filter", None)

        if not configs:
            debug_log("[NODE: load_multi_config_twitter_accounts] No configs provided", "error")
            return {
                "twitter_accounts": [],
                "config_handle_map": {},
                "twitter_settings": {},
            }

        accounts, handle_map, settings = load_multi_config_twitter_accounts(
            configs=configs,
            handle_filter=handle_filter,
        )

        return {
            "twitter_accounts": accounts,
            "config_handle_map": handle_map,
            "twitter_settings": settings,
        }
