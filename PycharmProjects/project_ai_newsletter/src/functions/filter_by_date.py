"""
Filter Articles by Date Node

Filters raw articles by publication date, removing articles older than
a configurable threshold. This runs BEFORE LLM-based filtering to
reduce API costs.
"""

from datetime import datetime, timedelta

from src.tracking import debug_log, track_time


def filter_by_date(state: dict) -> dict:
    """
    Filter articles by publication date.

    Articles older than max_age_hours are silently dropped.
    Articles with missing/unparseable dates are kept.

    Args:
        state: Pipeline state with 'raw_articles' and optional 'max_age_hours'

    Returns:
        Dict with updated 'raw_articles' list
    """
    with track_time("filter_by_date"):
        debug_log("[NODE: filter_by_date] Entering")

        raw_articles = state.get("raw_articles", [])
        max_age_hours = state.get("max_age_hours", 24)

        debug_log(f"[NODE: filter_by_date] Input: {len(raw_articles)} articles, max_age_hours={max_age_hours}")

        if not raw_articles:
            return {"raw_articles": []}

        # Calculate cutoff date
        today = datetime.now().date()
        cutoff_date = today - timedelta(days=max_age_hours / 24)

        debug_log(f"[NODE: filter_by_date] Cutoff date: {cutoff_date.isoformat()}")

        # Filter articles
        kept_articles = []
        dropped_count = 0

        for article in raw_articles:
            pub_date_str = article.get("pub_date", "")

            # Keep articles with missing dates (conservative approach)
            if not pub_date_str:
                kept_articles.append(article)
                continue

            # Parse the date
            try:
                pub_date = datetime.strptime(pub_date_str, "%Y-%m-%d").date()
            except ValueError:
                # Keep articles with unparseable dates
                debug_log(
                    f"[NODE: filter_by_date] Unparseable date '{pub_date_str}': {article.get('title', '')[:50]}",
                    "warning"
                )
                kept_articles.append(article)
                continue

            # Apply cutoff filter
            if pub_date >= cutoff_date:
                kept_articles.append(article)
            else:
                dropped_count += 1

        debug_log(f"[NODE: filter_by_date] Kept: {len(kept_articles)}, Dropped (old): {dropped_count}")

        return {"raw_articles": kept_articles}
