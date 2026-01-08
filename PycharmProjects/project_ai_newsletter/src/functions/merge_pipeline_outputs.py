"""
Merge Pipeline Outputs Node

Merges articles from RSS, HTML, and Twitter Layer 2 pipelines
into a single list for deduplication.
"""

import json
from pathlib import Path

from src.config import get_data_dir
from src.tracking import debug_log, track_time


def _get_input_files() -> dict:
    """Get input file paths for each pipeline (priority order: RSS > HTML > Twitter)."""
    data_dir = get_data_dir()
    return {
        "rss": data_dir / "aggregated_news.json",
        "html": data_dir / "html_news.json",
        "twitter": data_dir / "twitter_news.json",
    }


# =============================================================================
# Main Function
# =============================================================================

def merge_pipeline_outputs(state: dict) -> dict:
    """
    Merge articles from RSS, HTML, and Twitter pipelines.

    - Adds 'source_type' field to each article ("rss", "html", "twitter")
    - Performs URL deduplication at merge point (priority: RSS > HTML > Twitter)
    - Handles missing/empty files gracefully

    Args:
        state: Pipeline state with optional 'input_sources' list
               to select which pipelines to include.
               Default: ["rss", "html", "twitter"]

    Returns:
        Dict with:
            - 'articles_to_check': Merged article list
            - 'merge_stats': Statistics about merged sources
    """
    with track_time("merge_pipeline_outputs"):
        debug_log("[NODE: merge_pipeline_outputs] Entering")

        # Get configured input sources (default: all three)
        input_sources = state.get("input_sources", ["rss", "html", "twitter"])
        debug_log(f"[NODE: merge_pipeline_outputs] Input sources: {input_sources}")

        input_files = _get_input_files()

        # Track statistics
        stats = {
            "by_source_type": {},
            "url_collisions": 0,
            "total_before_dedup": 0,
            "total_after_dedup": 0,
        }

        # Collect all articles with source_type
        all_articles = []
        seen_urls = set()

        # Process in priority order: RSS > HTML > Twitter
        for source_type in ["rss", "html", "twitter"]:
            if source_type not in input_sources:
                continue

            file_path = input_files.get(source_type)
            if not file_path:
                continue

            articles = _load_articles_from_file(file_path, source_type)
            stats["by_source_type"][source_type] = {
                "loaded": len(articles),
                "kept": 0,
                "url_collisions": 0,
            }

            for article in articles:
                url = article.get("url", "")
                stats["total_before_dedup"] += 1

                if url in seen_urls:
                    # URL collision - skip (lower priority source)
                    stats["url_collisions"] += 1
                    stats["by_source_type"][source_type]["url_collisions"] += 1
                    debug_log(
                        f"[NODE: merge_pipeline_outputs] URL collision (skipped): {url[:60]}..."
                    )
                else:
                    seen_urls.add(url)
                    all_articles.append(article)
                    stats["by_source_type"][source_type]["kept"] += 1

        stats["total_after_dedup"] = len(all_articles)

        debug_log(
            f"[NODE: merge_pipeline_outputs] Merged {stats['total_after_dedup']} articles "
            f"({stats['url_collisions']} URL collisions removed)"
        )

        # Log per-source stats
        for source_type, source_stats in stats["by_source_type"].items():
            debug_log(
                f"[NODE: merge_pipeline_outputs]   {source_type}: "
                f"{source_stats['loaded']} loaded, {source_stats['kept']} kept"
            )

        return {
            "articles_to_check": all_articles,
            "merge_stats": stats,
        }


def _load_articles_from_file(file_path: Path, source_type: str) -> list[dict]:
    """
    Load articles from a JSON file and add source_type field.

    Args:
        file_path: Path to the JSON file.
        source_type: Source type to add ("rss", "html", "twitter").

    Returns:
        List of articles with source_type field added.
    """
    if not file_path.exists():
        debug_log(
            f"[NODE: merge_pipeline_outputs] File not found (skipped): {file_path.name}"
        )
        return []

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        debug_log(
            f"[NODE: merge_pipeline_outputs] Error reading {file_path.name}: {e}",
            "error"
        )
        return []

    articles = data.get("articles", [])

    if not articles:
        debug_log(
            f"[NODE: merge_pipeline_outputs] No articles in {file_path.name}"
        )
        return []

    # Add source_type to each article
    for article in articles:
        article["source_type"] = source_type

    debug_log(
        f"[NODE: merge_pipeline_outputs] Loaded {len(articles)} articles from {file_path.name}"
    )

    return articles
