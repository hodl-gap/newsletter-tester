"""
Load Historical Embeddings Node

Loads articles from the last N hours from the SQLite database
for semantic similarity comparison.
"""

from src.database import ArticleDatabase
from src.tracking import debug_log, track_time


def load_historical_embeddings(state: dict) -> dict:
    """
    Load historical articles with embeddings from the database.

    Retrieves articles from the last N hours (default: 48) for
    comparison against new articles.

    Args:
        state: Pipeline state with optional 'lookback_hours'

    Returns:
        Dict with:
        - 'historical_articles': List of articles with embeddings
        - 'is_first_run': True if database is empty
    """
    with track_time("load_historical_embeddings"):
        debug_log("[NODE: load_historical_embeddings] Entering")

        lookback_hours = state.get("lookback_hours", 48)

        # Initialize database
        db = ArticleDatabase()

        # Check if this is the first run
        if db.is_empty():
            debug_log("[NODE: load_historical_embeddings] Database empty (first run)")
            return {
                "historical_articles": [],
                "is_first_run": True
            }

        # Load recent articles with embeddings
        historical_articles = db.get_recent_articles(
            hours=lookback_hours,
            with_embeddings=True
        )

        # Filter out articles without embeddings
        articles_with_embeddings = [
            article for article in historical_articles
            if article.get("embedding") is not None
        ]

        debug_log(
            f"[NODE: load_historical_embeddings] Loaded {len(articles_with_embeddings)} "
            f"articles with embeddings from last {lookback_hours}h"
        )

        return {
            "historical_articles": articles_with_embeddings,
            "is_first_run": False
        }
