"""
Archive RSS Cache Node

Archives processed articles and clears the active cache.
Keeps last 7 days of processed articles for debugging/recovery.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

from src.config import get_data_dir
from src.tracking import debug_log, track_time


ARCHIVE_RETENTION_DAYS = 7


def archive_rss_cache(state: dict) -> dict:
    """
    Archive processed articles and clear active cache.

    1. Load current cache
    2. Append to archive file
    3. Prune archive entries older than 7 days
    4. Clear active cache

    Args:
        state: Pipeline state (not used, but required for node signature)

    Returns:
        Dict with 'archive_status' containing archive results
    """
    with track_time("archive_rss_cache"):
        debug_log("[NODE: archive_rss_cache] Entering")

        data_dir = get_data_dir()
        cache_path = data_dir / "rss_cache.json"
        archive_path = data_dir / "rss_cache_archive.json"

        # Load current cache
        if not cache_path.exists():
            debug_log("[NODE: archive_rss_cache] No cache to archive")
            return {"archive_status": {"archived": 0, "cleared": False}}

        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cache_data = json.load(f)
        except Exception as e:
            debug_log(f"[NODE: archive_rss_cache] Error loading cache: {e}", "error")
            return {"archive_status": {"archived": 0, "cleared": False, "error": str(e)}}

        articles_to_archive = cache_data.get("articles", [])
        if not articles_to_archive:
            debug_log("[NODE: archive_rss_cache] Cache is empty, nothing to archive")
            return {"archive_status": {"archived": 0, "cleared": False}}

        # Load existing archive
        archived_articles = []
        if archive_path.exists():
            try:
                with open(archive_path, "r", encoding="utf-8") as f:
                    archive_data = json.load(f)
                    archived_articles = archive_data.get("articles", [])
            except Exception as e:
                debug_log(f"[NODE: archive_rss_cache] Error loading archive: {e}", "warning")

        # Add processed timestamp to articles being archived
        now = datetime.now()
        now_iso = now.isoformat()
        for article in articles_to_archive:
            article["processed_at"] = now_iso

        # Append new articles to archive
        archived_articles.extend(articles_to_archive)

        # Prune old entries (older than 7 days)
        cutoff = now - timedelta(days=ARCHIVE_RETENTION_DAYS)
        cutoff_iso = cutoff.isoformat()

        pruned_articles = []
        pruned_count = 0
        for article in archived_articles:
            processed_at = article.get("processed_at", article.get("cached_at", ""))
            if processed_at >= cutoff_iso:
                pruned_articles.append(article)
            else:
                pruned_count += 1

        debug_log(f"[NODE: archive_rss_cache] Pruned {pruned_count} articles older than {ARCHIVE_RETENTION_DAYS} days")

        # Save archive
        archive_data = {
            "articles": pruned_articles,
            "last_updated": now_iso,
            "total_count": len(pruned_articles),
        }

        with open(archive_path, "w", encoding="utf-8") as f:
            json.dump(archive_data, f, ensure_ascii=False, indent=2)

        debug_log(f"[NODE: archive_rss_cache] Archived {len(articles_to_archive)} articles")

        # Clear active cache
        empty_cache = {
            "articles": [],
            "last_updated": now_iso,
            "total_count": 0,
        }

        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(empty_cache, f, ensure_ascii=False, indent=2)

        debug_log(f"[NODE: archive_rss_cache] Cleared active cache")

        return {
            "archive_status": {
                "archived": len(articles_to_archive),
                "pruned": pruned_count,
                "total_in_archive": len(pruned_articles),
                "cleared": True,
            }
        }
