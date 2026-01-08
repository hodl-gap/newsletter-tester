"""
Load Available Feeds Node

Reads the RSS availability results from Layer 1 and extracts
available feeds for content aggregation.
"""

import json
from pathlib import Path
from typing import TypedDict

from src.config import get_data_dir
from src.tracking import debug_log, track_time


class FeedInfo(TypedDict):
    """Information about an available feed."""
    url: str                    # Original source URL
    feed_url: str               # The recommended RSS feed URL
    source_name: str            # Extracted source name
    has_ai_feed: bool           # Whether it has a dedicated AI feed
    has_full_content: bool      # Whether RSS has content:encoded
    http_fetch_works: bool | None  # Whether article URLs are fetchable (None if not tested)


def load_available_feeds(state: dict) -> dict:
    """
    Load available feeds from rss_availability.json.

    Args:
        state: Pipeline state. Optional 'source_filter' list to filter sources.

    Returns:
        Dict with 'available_feeds' list
    """
    with track_time("load_available_feeds"):
        debug_log("[NODE: load_available_feeds] Entering")

        # Check for source filter
        source_filter = state.get("source_filter", None)
        if source_filter:
            debug_log(f"[NODE: load_available_feeds] Filtering for sources: {source_filter}")

        # Read RSS availability data
        data_path = get_data_dir() / "rss_availability.json"
        if not data_path.exists():
            debug_log("[NODE: load_available_feeds] ERROR: rss_availability.json not found", "error")
            return {"available_feeds": []}

        with open(data_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        debug_log(f"[NODE: load_available_feeds] Loaded {data.get('total', 0)} total sources")

        # Filter for available feeds only
        available_feeds: list[FeedInfo] = []

        for result in data.get("results", []):
            if result.get("status") != "available":
                continue

            feed_url = result.get("recommended_feed_url")
            if not feed_url:
                continue

            # Extract source name from URL
            source_name = _extract_source_name(result.get("url", ""))

            # Apply source filter if specified
            if source_filter:
                # Check if source matches any filter (case-insensitive)
                source_lower = source_name.lower()
                url_lower = result.get("url", "").lower()
                if not any(f.lower() in source_lower or f.lower() in url_lower for f in source_filter):
                    continue

            feed_info: FeedInfo = {
                "url": result.get("url", ""),
                "feed_url": feed_url,
                "source_name": source_name,
                "has_ai_feed": result.get("ai_feed_url") is not None,
                "has_full_content": result.get("has_full_content", False),
                "http_fetch_works": result.get("http_fetch_works"),
            }
            available_feeds.append(feed_info)

        debug_log(f"[NODE: load_available_feeds] Found {len(available_feeds)} available feeds")
        debug_log(f"[NODE: load_available_feeds] Output: {[f['source_name'] for f in available_feeds]}")

        return {"available_feeds": available_feeds}


def _extract_source_name(url: str) -> str:
    """
    Extract a readable source name from URL.

    Examples:
        https://techcrunch.com/ -> TechCrunch
        https://news.crunchbase.com/ -> Crunchbase News
    """
    if not url:
        return "Unknown"

    # Remove protocol and www
    name = url.replace("https://", "").replace("http://", "")
    name = name.replace("www.", "")

    # Get the domain part
    name = name.split("/")[0]

    # Remove common TLDs
    name = name.replace(".com", "").replace(".eu", "").replace(".io", "")
    name = name.replace(".co.kr", "").replace(".kr", "")

    # Handle subdomains
    if "." in name:
        parts = name.split(".")
        # news.crunchbase -> Crunchbase News
        if parts[0] in ("news", "tech", "biz"):
            name = f"{parts[1].title()} {parts[0].title()}"
        else:
            name = parts[0]

    # Title case and clean up
    name = name.replace("-", " ").replace("_", " ")

    # Special cases
    name_map = {
        "techcrunch": "TechCrunch",
        "venturebeat": "VentureBeat",
        "kdnuggets": "KDnuggets",
        "cbinsights": "CB Insights",
        "aibusiness": "AI Business",
        "inc42": "Inc42",
        "36kr": "36Kr",
        "ft": "Financial Times",
        "bbc": "BBC",
        "forbes": "Forbes",
        "fortune": "Fortune",
        "sifted": "Sifted",
        "wamda": "Wamda",
        "agbi": "AGBI",
        "rfi": "RFI",
        "itnewsafrica": "IT News Africa",
        "analyticsindiamag": "Analytics India Mag",
    }

    lower_name = name.lower().replace(" ", "")
    if lower_name in name_map:
        return name_map[lower_name]

    return name.title()
