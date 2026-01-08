"""
Load Scrapable Sources Node

Loads sources marked as "scrapable" with full config from html_availability.json
for HTML Layer 2 content scraping.
"""

import json
from pathlib import Path
from typing import TypedDict, Optional

from src.config import get_data_dir
from src.tracking import debug_log, track_time


class ScrapableSource(TypedDict):
    """Information about a scrapable source with full extraction config."""
    url: str
    source_name: str  # Derived from URL
    article_url_pattern: str
    sample_urls: list[str]
    title_selector: str
    content_selector: str
    date_selector: Optional[str]
    date_format: Optional[str]
    author_selector: Optional[str]
    approach: str  # "http_simple" or "playwright"
    confidence: float


def load_scrapable_sources(state: dict) -> dict:
    """
    Load sources marked as "scrapable" with full config from html_availability.json.

    Only loads sources that have both listing_page AND article_page configs.

    Args:
        state: Pipeline state with optional 'url_filter'

    Returns:
        Dict with 'scrapable_sources' list
    """
    with track_time("load_scrapable_sources"):
        debug_log("[NODE: load_scrapable_sources] Entering")

        url_filter = state.get("url_filter")

        # Load html_availability.json
        html_file = get_data_dir() / "html_availability.json"
        if not html_file.exists():
            debug_log("[NODE: load_scrapable_sources] html_availability.json not found", "error")
            return {"scrapable_sources": []}

        with open(html_file) as f:
            html_data = json.load(f)

        results = html_data.get("results", [])
        debug_log(f"[NODE: load_scrapable_sources] Loaded {len(results)} total sources")

        # Filter to scrapable with full config
        scrapable_sources: list[ScrapableSource] = []
        skipped_partial = 0

        for source in results:
            url = source.get("url", "")
            status = source.get("status", "")

            # Must be scrapable
            if status != "scrapable":
                continue

            # Must have listing_page config
            listing_page = source.get("listing_page")
            if not listing_page:
                debug_log(f"[NODE: load_scrapable_sources] Skipping {url} - no listing_page config")
                skipped_partial += 1
                continue

            # Must have article_page config
            article_page = source.get("article_page")
            if not article_page:
                debug_log(f"[NODE: load_scrapable_sources] Skipping {url} - no article_page config")
                skipped_partial += 1
                continue

            # Must have required selectors
            if not article_page.get("title_selector") or not article_page.get("content_selector"):
                debug_log(f"[NODE: load_scrapable_sources] Skipping {url} - missing required selectors")
                skipped_partial += 1
                continue

            # Apply optional URL filter
            if url_filter:
                if not any(f.lower() in url.lower() for f in url_filter):
                    continue

            # Extract source name from URL
            source_name = _extract_source_name(url)

            recommendation = source.get("recommendation", {})

            scrapable_sources.append(ScrapableSource(
                url=url,
                source_name=source_name,
                article_url_pattern=listing_page.get("article_url_pattern", ""),
                sample_urls=listing_page.get("sample_urls", []),
                title_selector=article_page.get("title_selector", ""),
                content_selector=article_page.get("content_selector", ""),
                date_selector=article_page.get("date_selector"),
                date_format=article_page.get("date_format"),
                author_selector=article_page.get("author_selector"),
                approach=recommendation.get("approach", "http_simple"),
                confidence=recommendation.get("confidence", 0.0),
            ))

        debug_log(f"[NODE: load_scrapable_sources] Skipped {skipped_partial} sources with partial config")
        debug_log(f"[NODE: load_scrapable_sources] Scrapable sources with full config: {len(scrapable_sources)}")

        for source in scrapable_sources:
            debug_log(f"[NODE: load_scrapable_sources]   - {source['source_name']} ({source['url']}) confidence={source['confidence']}")

        return {"scrapable_sources": scrapable_sources}


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
