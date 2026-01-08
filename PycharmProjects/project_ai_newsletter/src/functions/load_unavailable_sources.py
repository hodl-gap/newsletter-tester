"""
Load Unavailable Sources Node

Loads sources marked as "unavailable" from rss_availability.json
for HTML scraping analysis.
"""

import json
from pathlib import Path
from typing import TypedDict

from src.config import get_data_dir, load_config_settings
from src.tracking import debug_log, track_time


class SourceInfo(TypedDict):
    """Information about a source to test."""
    url: str
    notes: str | None


def load_unavailable_sources(state: dict) -> dict:
    """
    Load sources marked as "unavailable" from rss_availability.json.

    Args:
        state: Pipeline state with optional 'url_filter'

    Returns:
        Dict with 'sources_to_test' list
    """
    with track_time("load_unavailable_sources"):
        debug_log("[NODE: load_unavailable_sources] Entering")

        url_filter = state.get("url_filter")

        # Load exclusions from config
        config_settings = load_config_settings()
        html_exclusions = config_settings.get("html_exclusions", [])
        excluded_domains = [e["domain"] for e in html_exclusions]
        debug_log(f"[NODE: load_unavailable_sources] Loaded {len(excluded_domains)} exclusions from config")

        # Load rss_availability.json
        rss_file = get_data_dir() / "rss_availability.json"
        if not rss_file.exists():
            debug_log("[NODE: load_unavailable_sources] rss_availability.json not found", "error")
            return {"sources_to_test": []}

        with open(rss_file) as f:
            rss_data = json.load(f)

        results = rss_data.get("results", [])
        debug_log(f"[NODE: load_unavailable_sources] Loaded {len(results)} total sources")

        # Filter to unavailable only
        unavailable = [r for r in results if r.get("status") == "unavailable"]
        debug_log(f"[NODE: load_unavailable_sources] Found {len(unavailable)} unavailable sources")

        # Apply exclusion criteria
        sources_to_test: list[SourceInfo] = []
        excluded_count = 0

        for source in unavailable:
            url = source.get("url", "")

            # Check if source should be excluded (based on config)
            is_excluded = any(excl in url.lower() for excl in excluded_domains)
            if is_excluded:
                excluded_count += 1
                debug_log(f"[NODE: load_unavailable_sources] Excluding: {url}")
                continue

            # Apply optional URL filter
            if url_filter:
                if not any(f.lower() in url.lower() for f in url_filter):
                    continue

            sources_to_test.append(SourceInfo(
                url=url,
                notes=source.get("notes"),
            ))

        debug_log(f"[NODE: load_unavailable_sources] Excluded {excluded_count} sources")
        debug_log(f"[NODE: load_unavailable_sources] Sources to test: {len(sources_to_test)}")

        for source in sources_to_test:
            debug_log(f"[NODE: load_unavailable_sources]   - {source['url']}")

        return {"sources_to_test": sources_to_test}
