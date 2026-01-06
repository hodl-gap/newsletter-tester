"""
Check URL Duplicates Node

Filters raw articles by checking if their URLs already exist in the
database (from previous runs). This runs BEFORE LLM-based filtering
to reduce API costs by skipping already-processed articles.
"""

from src.database import ArticleDatabase
from src.tracking import debug_log, track_time


def check_url_duplicates(state: dict) -> dict:
    """
    Check articles against stored URLs and drop exact duplicates.

    Queries the SQLite database to find URLs that were processed in
    previous runs. Duplicates are logged and dropped before LLM processing.

    Args:
        state: Pipeline state with 'raw_articles'

    Returns:
        Dict with:
        - 'raw_articles': Filtered list (duplicates removed)
        - 'url_duplicates_dropped': Count of dropped duplicates
    """
    with track_time("check_url_duplicates"):
        debug_log("[NODE: check_url_duplicates] Entering")

        raw_articles = state.get("raw_articles", [])

        debug_log(f"[NODE: check_url_duplicates] Input: {len(raw_articles)} articles")

        if not raw_articles:
            return {"raw_articles": [], "url_duplicates_dropped": 0}

        # Initialize database
        db = ArticleDatabase()

        # Check if database is empty (first run)
        if db.is_empty():
            debug_log("[NODE: check_url_duplicates] Database empty (first run) - skipping URL check")
            return {"raw_articles": raw_articles, "url_duplicates_dropped": 0}

        # Get all URLs from articles
        urls = [article.get("link", "") for article in raw_articles if article.get("link")]

        # Batch check against database
        existing_urls = db.get_existing_urls(urls)

        debug_log(f"[NODE: check_url_duplicates] Found {len(existing_urls)} existing URLs in database")

        # Filter out duplicates
        kept_articles = []
        dropped_count = 0

        for article in raw_articles:
            url = article.get("link", "")

            if url in existing_urls:
                # Log the duplicate
                db.log_dedup(
                    original_url=url,
                    dedup_type="url_exact"
                )
                dropped_count += 1
            else:
                kept_articles.append(article)

        debug_log(f"[NODE: check_url_duplicates] Kept: {len(kept_articles)}, Dropped (URL dupe): {dropped_count}")

        return {
            "raw_articles": kept_articles,
            "url_duplicates_dropped": dropped_count
        }
