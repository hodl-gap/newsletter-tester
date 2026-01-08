"""
Save Aggregated Content Node

Saves the final output to JSON and CSV files.
"""

import csv
import json
from datetime import datetime
from pathlib import Path

from src.config import get_data_dir
from src.database import ArticleDatabase
from src.tracking import debug_log, track_time, cost_tracker


def save_aggregated_content(state: dict) -> dict:
    """
    Save aggregated content to files.

    Args:
        state: Pipeline state with 'output_data', 'content_sufficiency', and 'discarded_articles'

    Returns:
        Dict with 'save_status' info
    """
    with track_time("save_aggregated_content"):
        debug_log("[NODE: save_aggregated_content] Entering")

        output_data = state.get("output_data", [])
        content_sufficiency = state.get("content_sufficiency", {})
        discarded_articles = state.get("discarded_articles", [])

        debug_log(f"[NODE: save_aggregated_content] Saving {len(output_data)} records")

        # Prepare output paths (get_data_dir creates the directory if needed)
        data_dir = get_data_dir()

        json_path = data_dir / "aggregated_news.json"
        csv_path = data_dir / "aggregated_news.csv"

        # Build metadata
        metadata = {
            "timestamp": datetime.now().isoformat(),
            "total_articles": len(output_data),
            "content_source": "descriptions" if content_sufficiency.get("use_descriptions", True) else "llm_summaries",
            "sufficiency_score": content_sufficiency.get("avg_score", 0),
            "cost": _get_cost_info(),
        }

        # Count by category
        category_counts: dict[str, int] = {}
        region_counts: dict[str, int] = {}
        layer_counts: dict[str, int] = {}

        for record in output_data:
            cat = record.get("category", "Other")
            reg = record.get("region", "Unknown")
            lay = record.get("layer", "B2B Applications")

            category_counts[cat] = category_counts.get(cat, 0) + 1
            region_counts[reg] = region_counts.get(reg, 0) + 1
            layer_counts[lay] = layer_counts.get(lay, 0) + 1

        metadata["by_category"] = category_counts
        metadata["by_region"] = region_counts
        metadata["by_layer"] = layer_counts

        # Save JSON
        json_output = {
            "metadata": metadata,
            "articles": output_data,
        }

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_output, f, indent=2, ensure_ascii=False)

        debug_log(f"[NODE: save_aggregated_content] Saved JSON to {json_path}")

        # Save CSV
        if output_data:
            fieldnames = ["date", "source", "region", "category", "layer", "title", "contents", "url"]

            with open(csv_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(output_data)

            debug_log(f"[NODE: save_aggregated_content] Saved CSV to {csv_path}")

        # Save discarded articles CSV
        discarded_csv_path = data_dir / "discarded_news.csv"
        if discarded_articles:
            discarded_fieldnames = ["source_name", "title", "url", "pub_date", "discard_reason"]

            with open(discarded_csv_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=discarded_fieldnames, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(discarded_articles)

            debug_log(f"[NODE: save_aggregated_content] Saved {len(discarded_articles)} discarded articles to {discarded_csv_path}")

            # Also store discarded articles in database for debugging/reference
            db = ArticleDatabase()
            db.insert_discarded_batch(discarded_articles, source_type="rss")

        # Print summary
        _print_summary(metadata, output_data, len(discarded_articles))

        return {
            "save_status": {
                "json_path": str(json_path),
                "csv_path": str(csv_path),
                "discarded_csv_path": str(discarded_csv_path),
                "record_count": len(output_data),
                "discarded_count": len(discarded_articles),
            }
        }


def _get_cost_info() -> dict:
    """Get cost tracking info."""
    try:
        return {
            "total_cost": f"${cost_tracker.total_cost:.4f}",
            "input_tokens": cost_tracker.total_input_tokens,
            "output_tokens": cost_tracker.total_output_tokens,
            "llm_calls": cost_tracker.call_count,
        }
    except Exception:
        return {"total_cost": "unknown"}


def _print_summary(metadata: dict, output_data: list, discarded_count: int = 0) -> None:
    """Print summary to console."""
    print("\n" + "=" * 60)
    print("CONTENT AGGREGATION COMPLETE")
    print("=" * 60)
    print(f"Total articles: {metadata['total_articles']}")
    print(f"Discarded articles: {discarded_count}")
    print(f"Content source: {metadata['content_source']}")
    print(f"Sufficiency score: {metadata.get('sufficiency_score', 'N/A')}")
    print()

    print("By Category:")
    for cat, count in sorted(metadata.get("by_category", {}).items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}")
    print()

    print("By Region:")
    for reg, count in sorted(metadata.get("by_region", {}).items(), key=lambda x: -x[1]):
        print(f"  {reg}: {count}")
    print()

    print("By Layer:")
    for lay, count in sorted(metadata.get("by_layer", {}).items(), key=lambda x: -x[1]):
        print(f"  {lay}: {count}")
    print()

    cost_info = metadata.get("cost", {})
    print(f"LLM Cost: {cost_info.get('total_cost', 'unknown')}")
    print(f"LLM Calls: {cost_info.get('llm_calls', 'unknown')}")
    print("=" * 60 + "\n")
