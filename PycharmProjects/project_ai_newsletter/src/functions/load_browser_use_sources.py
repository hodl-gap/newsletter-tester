"""
Load Browser-Use Sources Node

Loads enabled sources from config.json["browser_use_sources"] for
browser-use Agent-based content scraping.
"""

import json
from pathlib import Path
from typing import TypedDict, Optional

from src.config import get_config_path
from src.tracking import debug_log, track_time


class BrowserUseSource(TypedDict):
    """Information about a browser-use source."""
    url: str
    name: str
    enabled: bool


class BrowserUseSettings(TypedDict):
    """Browser-use settings from config."""
    headless: bool
    max_articles_per_source: int
    model: str


def load_browser_use_sources(state: dict) -> dict:
    """
    Load enabled browser-use sources from config.json.

    Args:
        state: Pipeline state with optional 'url_filter'

    Returns:
        Dict with:
            - 'browser_use_sources': List of enabled sources
            - 'browser_use_settings': Settings dict
    """
    with track_time("load_browser_use_sources"):
        debug_log("[NODE: load_browser_use_sources] Entering")

        url_filter = state.get("url_filter")

        # Load config.json
        config_file = get_config_path() / "config.json"
        if not config_file.exists():
            debug_log("[NODE: load_browser_use_sources] config.json not found", "error")
            return {"browser_use_sources": [], "browser_use_settings": {}}

        with open(config_file) as f:
            config_data = json.load(f)

        # Get browser_use_sources
        all_sources = config_data.get("browser_use_sources", [])
        debug_log(f"[NODE: load_browser_use_sources] Found {len(all_sources)} configured sources")

        # Get settings with defaults
        settings = config_data.get("browser_use_settings", {})
        browser_use_settings = BrowserUseSettings(
            headless=settings.get("headless", False),
            max_articles_per_source=settings.get("max_articles_per_source", 5),
            model=settings.get("model", "claude-sonnet-4-20250514"),
        )

        # Filter to enabled sources
        enabled_sources: list[BrowserUseSource] = []

        for source in all_sources:
            url = source.get("url", "")
            enabled = source.get("enabled", False)
            name = source.get("name", _extract_source_name(url))

            if not enabled:
                debug_log(f"[NODE: load_browser_use_sources] Skipping disabled: {name}")
                continue

            # Apply optional URL filter
            if url_filter:
                if not any(f.lower() in url.lower() for f in url_filter):
                    continue

            enabled_sources.append(BrowserUseSource(
                url=url,
                name=name,
                enabled=enabled,
            ))

        debug_log(f"[NODE: load_browser_use_sources] Enabled sources: {len(enabled_sources)}")
        for source in enabled_sources:
            debug_log(f"[NODE: load_browser_use_sources]   - {source['name']} ({source['url']})")

        return {
            "browser_use_sources": enabled_sources,
            "browser_use_settings": browser_use_settings,
        }


def _extract_source_name(url: str) -> str:
    """
    Extract a readable source name from URL.

    Args:
        url: Full URL of the source

    Returns:
        Human-readable source name
    """
    # Remove protocol
    name = url.replace("https://", "").replace("http://", "")

    # Remove www.
    name = name.replace("www.", "")

    # Remove trailing slash and path
    name = name.split("/")[0]

    # Remove .com, .ai, etc. for cleaner name
    parts = name.split(".")
    if len(parts) >= 2:
        # Use first part as name, capitalize
        name = parts[0].replace("-", " ").replace("_", " ").title()

    return name
