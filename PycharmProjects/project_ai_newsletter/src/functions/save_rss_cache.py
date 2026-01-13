"""
Save RSS Cache Node

Saves raw articles to a cache file, deduplicating by URL.
Used for frequent RSS fetching without LLM processing.
"""

import json
from datetime import datetime
from pathlib import Path

from src.config import get_data_dir
from src.tracking import debug_log, track_time


def save_rss_cache(state: dict) -> dict:
    """
    Save raw articles to RSS cache, deduplicating by URL.

    Appends new articles to existing cache, skipping duplicates.
    Each article gets a 'cached_at' timestamp.

    Args:
        state: Pipeline state with 'raw_articles'

    Returns:
        Dict with 'cache_status' containing save results
    """
    with track_time("save_rss_cache"):
        debug_log("[NODE: save_rss_cache] Entering")

        raw_articles = state.get("raw_articles", [])
        cache_path = get_data_dir() / "rss_cache.json"

        debug_log(f"[NODE: save_rss_cache] Input: {len(raw_articles)} articles")

        # Load existing cache
        existing_articles = []
        existing_urls = set()

        if cache_path.exists():
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    cache_data = json.load(f)
                    existing_articles = cache_data.get("articles", [])
                    existing_urls = {a.get("link") for a in existing_articles}
                    debug_log(f"[NODE: save_rss_cache] Loaded {len(existing_articles)} existing cached articles")
            except Exception as e:
                debug_log(f"[NODE: save_rss_cache] Error loading cache: {e}", "warning")

        # Add new articles with timestamp
        now = datetime.now().isoformat()
        new_count = 0

        for article in raw_articles:
            url = article.get("link", "")
            if url and url not in existing_urls:
                article_with_timestamp = {**article, "cached_at": now}
                existing_articles.append(article_with_timestamp)
                existing_urls.add(url)
                new_count += 1

        # Save updated cache
        cache_data = {
            "articles": existing_articles,
            "last_updated": now,
            "total_count": len(existing_articles),
        }

        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)

        debug_log(f"[NODE: save_rss_cache] Added {new_count} new articles, total: {len(existing_articles)}")
        debug_log(f"[NODE: save_rss_cache] Saved to: {cache_path}")

        return {
            "cache_status": {
                "path": str(cache_path),
                "new_articles": new_count,
                "total_articles": len(existing_articles),
                "duplicates_skipped": len(raw_articles) - new_count,
            }
        }
