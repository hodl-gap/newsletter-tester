"""
Load Unavailable Sources Node

Loads sources marked as "unavailable" from rss_availability.json
for HTML scraping analysis.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import TypedDict

from src.config import get_data_dir, load_config_settings
from src.tracking import debug_log, track_time


class SourceInfo(TypedDict):
    """Information about a source to test."""
    url: str
    notes: str | None


def filter_recently_checked_html(urls: list[str], refresh_days: int) -> tuple[list[str], list[str]]:
    """
    Filter out URLs that were checked within the refresh period.

    Args:
        urls: List of URLs to filter
        refresh_days: Number of days before re-checking a source

    Returns:
        Tuple of (urls_to_process, skipped_urls)
    """
    output_path = get_data_dir() / "html_availability.json"

    if not output_path.exists():
        debug_log("[filter_recently_checked_html] No existing results file, processing all URLs")
        return urls, []

    try:
        with open(output_path, "r") as f:
            existing_data = json.load(f)
        existing_results = existing_data.get("results", [])
    except (json.JSONDecodeError, KeyError):
        debug_log("[filter_recently_checked_html] Could not parse existing results, processing all URLs")
        return urls, []

    # Build lookup map of URL -> analyzed_at timestamp
    analyzed_at_map = {}
    for result in existing_results:
        url = result.get("url")
        analyzed_at = result.get("analyzed_at")
        if url:
            analyzed_at_map[url] = analyzed_at

    # Calculate cutoff date
    cutoff_date = datetime.now() - timedelta(days=refresh_days)

    urls_to_process = []
    skipped_urls = []

    for url in urls:
        analyzed_at_str = analyzed_at_map.get(url)

        if analyzed_at_str is None:
            # New URL or entry without analyzed_at, needs processing
            urls_to_process.append(url)
            debug_log(f"[filter_recently_checked_html] {url}: PROCESS (new or no timestamp)")
        else:
            try:
                analyzed_at_dt = datetime.fromisoformat(analyzed_at_str)
                if analyzed_at_dt < cutoff_date:
                    # Stale entry, needs re-check
                    urls_to_process.append(url)
                    days_ago = (datetime.now() - analyzed_at_dt).days
                    debug_log(f"[filter_recently_checked_html] {url}: PROCESS (stale, {days_ago} days ago)")
                else:
                    # Recently checked, skip
                    skipped_urls.append(url)
                    days_ago = (datetime.now() - analyzed_at_dt).days
                    debug_log(f"[filter_recently_checked_html] {url}: SKIP (fresh, {days_ago} days ago)")
            except ValueError:
                # Invalid date format, re-check
                urls_to_process.append(url)
                debug_log(f"[filter_recently_checked_html] {url}: PROCESS (invalid timestamp)")

    return urls_to_process, skipped_urls


def load_unavailable_sources(state: dict) -> dict:
    """
    Load sources marked as "unavailable" from rss_availability.json.

    Incremental mode (default): Skips sources checked within refresh_days.
    Use full_rescan=True to force re-checking all sources.

    Args:
        state: Pipeline state with optional 'url_filter', 'full_rescan', 'refresh_days'

    Returns:
        Dict with 'sources_to_test' and 'skipped_urls' lists
    """
    with track_time("load_unavailable_sources"):
        debug_log("[NODE: load_unavailable_sources] Entering")

        url_filter = state.get("url_filter")
        full_rescan = state.get("full_rescan", False)
        refresh_days = state.get("refresh_days", 7)

        # Load exclusions from config
        config_settings = load_config_settings()
        html_exclusions = config_settings.get("html_exclusions", [])
        excluded_domains = [e["domain"] for e in html_exclusions]
        debug_log(f"[NODE: load_unavailable_sources] Loaded {len(excluded_domains)} exclusions from config")

        # Load rss_availability.json
        rss_file = get_data_dir() / "rss_availability.json"
        if not rss_file.exists():
            debug_log("[NODE: load_unavailable_sources] rss_availability.json not found", "error")
            return {"sources_to_test": [], "skipped_urls": []}

        with open(rss_file) as f:
            rss_data = json.load(f)

        results = rss_data.get("results", [])
        debug_log(f"[NODE: load_unavailable_sources] Loaded {len(results)} total sources")

        # Filter to unavailable only
        unavailable = [r for r in results if r.get("status") == "unavailable"]
        debug_log(f"[NODE: load_unavailable_sources] Found {len(unavailable)} unavailable sources")

        # Apply exclusion criteria
        candidate_sources: list[SourceInfo] = []
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

            candidate_sources.append(SourceInfo(
                url=url,
                notes=source.get("notes"),
            ))

        debug_log(f"[NODE: load_unavailable_sources] Excluded {excluded_count} sources")
        debug_log(f"[NODE: load_unavailable_sources] Candidate sources: {len(candidate_sources)}")

        # Apply incremental filtering (skip recently-checked URLs)
        skipped_urls = []
        if not full_rescan:
            candidate_urls = [s["url"] for s in candidate_sources]
            urls_to_process, skipped_urls = filter_recently_checked_html(candidate_urls, refresh_days)
            # Filter candidate_sources to only include urls_to_process
            urls_to_process_set = set(urls_to_process)
            sources_to_test = [s for s in candidate_sources if s["url"] in urls_to_process_set]
            debug_log(f"[NODE: load_unavailable_sources] Incremental mode: {len(sources_to_test)} to process, {len(skipped_urls)} skipped (refresh_days={refresh_days})")
        else:
            sources_to_test = candidate_sources
            debug_log("[NODE: load_unavailable_sources] Full rescan mode: processing all sources")

        debug_log(f"[NODE: load_unavailable_sources] Sources to test: {len(sources_to_test)}")

        for source in sources_to_test:
            debug_log(f"[NODE: load_unavailable_sources]   - {source['url']}")

        return {"sources_to_test": sources_to_test, "skipped_urls": skipped_urls}
