"""
Store Articles Node

Stores unique articles with their embeddings to the SQLite database.
Also logs deduplication actions for audit trail.
"""

from datetime import datetime

from src.database import ArticleDatabase
from src.tracking import debug_log, track_time


def store_articles(state: dict) -> dict:
    """
    Store unique articles to the database.

    Inserts all confirmed unique articles with their embeddings.
    Also logs all deduplication decisions to the audit table.

    Args:
        state: Pipeline state with:
            - 'confirmed_unique': Articles confirmed as unique
            - 'confirmed_duplicates': Articles confirmed as duplicates
            - 'is_first_run': True if seeding the database

    Returns:
        Dict with:
        - 'stored_count': Number of articles stored
        - 'final_unique': Articles that were stored
    """
    with track_time("store_articles"):
        debug_log("[NODE: store_articles] Entering")

        unique_articles = state.get("confirmed_unique", [])
        duplicate_articles = state.get("confirmed_duplicates", [])
        is_first_run = state.get("is_first_run", False)

        debug_log(
            f"[NODE: store_articles] Input: {len(unique_articles)} unique, "
            f"{len(duplicate_articles)} duplicates, first_run={is_first_run}"
        )

        # Initialize database
        db = ArticleDatabase()

        # Get run timestamp for logging
        run_timestamp = datetime.now().isoformat()

        # Store unique articles
        embeddings = [
            article.get("embedding") for article in unique_articles
        ]

        stored_count = db.insert_articles_batch(unique_articles, embeddings)

        debug_log(f"[NODE: store_articles] Stored {stored_count} articles to database")

        # Log deduplication decisions for duplicates
        if duplicate_articles:
            dedup_entries = []

            for dup in duplicate_articles:
                article = dup.get("article", dup)
                url = article.get("url", article.get("link", ""))
                duplicate_of = dup.get("duplicate_of", {})
                duplicate_of_url = duplicate_of.get("url", duplicate_of.get("link", ""))

                entry = {
                    "original_url": url,
                    "duplicate_of_url": duplicate_of_url,
                    "dedup_type": "semantic_llm" if dup.get("llm_confirmed") else "semantic_auto",
                    "similarity_score": dup.get("similarity"),
                    "llm_confirmed": dup.get("llm_confirmed")
                }
                dedup_entries.append(entry)

            db.log_dedup_batch(dedup_entries, run_timestamp)

            debug_log(f"[NODE: store_articles] Logged {len(dedup_entries)} dedup entries")

        return {
            "stored_count": stored_count,
            "final_unique": unique_articles
        }
