"""
Load RSS Cache Node

Loads raw articles from cache file for LLM processing.
Used when running content_orchestrator with --from-cache flag.
"""

import json
from pathlib import Path

from src.config import get_data_dir
from src.tracking import debug_log, track_time


def load_rss_cache(state: dict) -> dict:
    """
    Load raw articles from RSS cache.

    Args:
        state: Pipeline state (may contain 'source_filter')

    Returns:
        Dict with 'raw_articles' list loaded from cache
    """
    with track_time("load_rss_cache"):
        debug_log("[NODE: load_rss_cache] Entering")

        cache_path = get_data_dir() / "rss_cache.json"
        source_filter = state.get("source_filter")

        if not cache_path.exists():
            debug_log("[NODE: load_rss_cache] Cache file not found", "warning")
            return {"raw_articles": []}

        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cache_data = json.load(f)
        except Exception as e:
            debug_log(f"[NODE: load_rss_cache] Error loading cache: {e}", "error")
            return {"raw_articles": []}

        articles = cache_data.get("articles", [])
        debug_log(f"[NODE: load_rss_cache] Loaded {len(articles)} articles from cache")

        # Apply source filter if provided
        if source_filter:
            filtered = []
            for article in articles:
                source_name = article.get("source_name", "").lower()
                feed_url = article.get("feed_url", "").lower()

                if any(f.lower() in source_name or f.lower() in feed_url for f in source_filter):
                    filtered.append(article)

            debug_log(f"[NODE: load_rss_cache] After source filter: {len(filtered)} articles")
            articles = filtered

        debug_log(f"[NODE: load_rss_cache] Output: {len(articles)} raw_articles")

        return {"raw_articles": articles}
