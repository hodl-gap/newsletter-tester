"""
Build Twitter Output Node

Assembles the final output data for Twitter in DataFrame-ready format
with the required columns. Mirrors build_output_dataframe.py but
adapted for Twitter-specific fields.
"""

from typing import TypedDict

from src.tracking import debug_log, track_time


class OutputRecord(TypedDict):
    """Final output record for DataFrame."""
    date: str           # YYYY-MM-DD
    source: str         # Twitter handle (e.g., "@a16z")
    region: str         # Geographic region
    category: str       # News category
    layer: str          # AI value chain layer
    contents: str       # Tweet summary
    url: str            # Tweet URL
    title: str          # Original tweet text


def build_twitter_output(state: dict) -> dict:
    """
    Build the final output data in DataFrame-ready format.

    Args:
        state: Pipeline state with 'enriched_articles'

    Returns:
        Dict with 'output_data' list of OutputRecord
    """
    with track_time("build_twitter_output"):
        debug_log("[NODE: build_twitter_output] Entering")

        enriched_articles = state.get("enriched_articles", [])
        debug_log(f"[NODE: build_twitter_output] Processing {len(enriched_articles)} tweets")

        output_data: list[OutputRecord] = []

        for tweet in enriched_articles:
            # Truncate tweet text for title (first 100 chars)
            full_text = tweet.get("full_text", tweet.get("title", ""))
            title = full_text[:100] + "..." if len(full_text) > 100 else full_text

            record: OutputRecord = {
                "date": tweet.get("pub_date", ""),
                "source": tweet.get("handle", tweet.get("source_name", "Unknown")),
                "region": _format_region(tweet.get("region", "unknown")),
                "category": _format_category(tweet.get("category", "other")),
                "layer": _format_layer(tweet.get("layer", "b2b_apps")),
                "contents": tweet.get("contents", ""),
                "url": tweet.get("url", tweet.get("link", "")),
                "title": title,
            }
            output_data.append(record)

        # Sort by date (newest first)
        output_data.sort(key=lambda x: x["date"], reverse=True)

        debug_log(f"[NODE: build_twitter_output] Output: {len(output_data)} records")

        # Log summary statistics
        _log_summary(output_data)

        return {"output_data": output_data}


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
