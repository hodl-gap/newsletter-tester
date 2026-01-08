"""
Build Twitter Output Node

Assembles the final output data for Twitter in DataFrame-ready format
with the required columns. Mirrors build_output_dataframe.py but
adapted for Twitter-specific fields.
"""

import re
from typing import TypedDict

from src.tracking import debug_log, track_time


# Patterns that indicate a failed/error summary from the LLM
FAILED_SUMMARY_PATTERNS = [
    r"^Unable to (?:process|summarize|generate)",
    r"insufficient (?:content|information)",
    r"(?:corrupted|encrypted|unreadable)",
    r"^This page contains only",
    r"making summarization impossible",
]


class OutputRecord(TypedDict):
    """Final output record for DataFrame."""
    date: str           # YYYY-MM-DD
    source: str         # Twitter handle (e.g., "@a16z")
    region: str         # Geographic region
    category: str       # News category
    layer: str          # AI value chain layer
    contents: str       # Tweet summary
    url: str            # Tweet URL
    title: str          # Korean headline
    full_content: str   # Original tweet text (for re-processing)


def _is_failed_summary(contents: str) -> bool:
    """
    Check if summary is an LLM error message rather than actual content.

    The LLM sometimes generates error messages like "Unable to process: ..."
    when tweet content is corrupted or insufficient. These should be
    filtered out and moved to discarded articles.

    Args:
        contents: The summary text to check

    Returns:
        True if the summary appears to be a failure/error message
    """
    if not contents or len(contents.strip()) < 10:
        return True
    for pattern in FAILED_SUMMARY_PATTERNS:
        if re.search(pattern, contents, re.IGNORECASE):
            return True
    return False


def build_twitter_output(state: dict) -> dict:
    """
    Build the final output data in DataFrame-ready format.

    Args:
        state: Pipeline state with 'enriched_articles' and 'discarded_articles'

    Returns:
        Dict with 'output_data' list of OutputRecord and updated 'discarded_articles'
    """
    with track_time("build_twitter_output"):
        debug_log("[NODE: build_twitter_output] Entering")

        enriched_articles = state.get("enriched_articles", [])
        existing_discards = state.get("discarded_articles", [])

        debug_log(f"[NODE: build_twitter_output] Processing {len(enriched_articles)} tweets")

        output_data: list[OutputRecord] = []
        failed_summary_discards: list[dict] = []

        for tweet in enriched_articles:
            contents = tweet.get("contents", "")

            # Check for failed summaries (LLM error messages)
            if _is_failed_summary(contents):
                failed_summary_discards.append({
                    "source_name": tweet.get("handle", tweet.get("source_name", "Unknown")),
                    "title": tweet.get("full_text", tweet.get("title", ""))[:100],
                    "url": tweet.get("url", tweet.get("link", "")),
                    "pub_date": tweet.get("pub_date", ""),
                    "discard_reason": f"failed_summary: {contents[:100]}..." if len(contents) > 100 else f"failed_summary: {contents}",
                })
                continue  # Skip adding to output

            # Use LLM-generated Korean title
            title = tweet.get("title", "")

            record: OutputRecord = {
                "date": tweet.get("pub_date", ""),
                "source": tweet.get("handle", tweet.get("source_name", "Unknown")),
                "region": _format_region(tweet.get("region", "unknown")),
                "category": _format_category(tweet.get("category", "other")),
                "layer": _format_layer(tweet.get("layer", "b2b_apps")),
                "contents": contents,
                "url": tweet.get("url", tweet.get("link", "")),
                "title": title,
                "full_content": tweet.get("full_text", tweet.get("description", "")),
            }
            output_data.append(record)

        # Sort by date (newest first)
        output_data.sort(key=lambda x: x["date"], reverse=True)

        # Log discards
        if failed_summary_discards:
            debug_log(f"[NODE: build_twitter_output] Discarded {len(failed_summary_discards)} tweets with failed summaries")

        debug_log(f"[NODE: build_twitter_output] Output: {len(output_data)} records")

        # Log summary statistics
        _log_summary(output_data)

        # Combine with existing discards
        all_discards = existing_discards + failed_summary_discards

        return {
            "output_data": output_data,
            "discarded_articles": all_discards,
        }


def _format_region(region: str) -> str:
    """Format region for display."""
    region_map = {
        "north_america": "North America",
        "latin_america": "Latin America",
        "europe": "Europe",
        "middle_east": "Middle East",
        "africa": "Africa",
        "south_asia": "South Asia",
        "southeast_asia": "Southeast Asia",
        "east_asia": "East Asia",
        "oceania": "Oceania",
        "global": "Global",
        "unknown": "Unknown",
    }
    return region_map.get(region.lower(), region.title())


def _format_category(category: str) -> str:
    """Format category for display."""
    category_map = {
        "funding": "Funding",
        "acquisition": "Acquisition",
        "product_launch": "Product Launch",
        "partnership": "Partnership",
        "earnings": "Earnings",
        "expansion": "Expansion",
        "executive": "Executive",
        "ipo": "IPO",
        "layoff": "Layoff",
        "other": "Other",
    }
    return category_map.get(category.lower(), category.title())


def _format_layer(layer: str) -> str:
    """Format layer for display."""
    layer_map = {
        "chips_infra": "Chips & Infrastructure",
        "foundation_models": "Foundation Models",
        "finetuning_mlops": "Fine-tuning & MLOps",
        "b2b_apps": "B2B Applications",
        "consumer_apps": "Consumer Applications",
    }
    return layer_map.get(layer.lower(), layer.title())


def _log_summary(data: list[OutputRecord]) -> None:
    """Log summary statistics."""
    if not data:
        return

    # Count by region
    region_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {}
    layer_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}

    for record in data:
        region = record["region"]
        category = record["category"]
        layer = record["layer"]
        source = record["source"]

        region_counts[region] = region_counts.get(region, 0) + 1
        category_counts[category] = category_counts.get(category, 0) + 1
        layer_counts[layer] = layer_counts.get(layer, 0) + 1
        source_counts[source] = source_counts.get(source, 0) + 1

    debug_log(f"[NODE: build_twitter_output] By Region: {region_counts}")
    debug_log(f"[NODE: build_twitter_output] By Category: {category_counts}")
    debug_log(f"[NODE: build_twitter_output] By Layer: {layer_counts}")
    debug_log(f"[NODE: build_twitter_output] By Handle: {source_counts}")
