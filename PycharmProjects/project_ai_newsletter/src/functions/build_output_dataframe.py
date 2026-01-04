"""
Build Output DataFrame Node

Assembles the final output data in DataFrame-ready format
with the required columns.
"""

from typing import TypedDict

from src.tracking import debug_log, track_time


class OutputRecord(TypedDict):
    """Final output record for DataFrame."""
    date: str           # YYYY-MM-DD
    source: str         # Publication name
    region: str         # Geographic region
    category: str       # News category
    layer: str          # AI value chain layer
    contents: str       # Article summary
    url: str            # Article URL
    title: str          # Article title (bonus field)


def build_output_dataframe(state: dict) -> dict:
    """
    Build the final output data in DataFrame-ready format.

    Args:
        state: Pipeline state with 'enriched_articles'

    Returns:
        Dict with 'output_data' list of OutputRecord
    """
    with track_time("build_output_dataframe"):
        debug_log("[NODE: build_output_dataframe] Entering")

        enriched_articles = state.get("enriched_articles", [])
        debug_log(f"[NODE: build_output_dataframe] Processing {len(enriched_articles)} articles")

        output_data: list[OutputRecord] = []

        for article in enriched_articles:
            record: OutputRecord = {
                "date": article.get("pub_date", ""),
                "source": article.get("source_name", "Unknown"),
                "region": _format_region(article.get("region", "unknown")),
                "category": _format_category(article.get("category", "other")),
                "layer": _format_layer(article.get("layer", "b2b_apps")),
                "contents": article.get("contents", article.get("description", "")),
                "url": article.get("link", ""),
                "title": article.get("title", ""),
            }
            output_data.append(record)

        # Sort by date (newest first)
        output_data.sort(key=lambda x: x["date"], reverse=True)

        debug_log(f"[NODE: build_output_dataframe] Output: {len(output_data)} records")

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

    debug_log(f"[NODE: build_output_dataframe] By Region: {region_counts}")
    debug_log(f"[NODE: build_output_dataframe] By Category: {category_counts}")
    debug_log(f"[NODE: build_output_dataframe] By Layer: {layer_counts}")
    debug_log(f"[NODE: build_output_dataframe] Top Sources: {dict(sorted(source_counts.items(), key=lambda x: -x[1])[:5])}")
