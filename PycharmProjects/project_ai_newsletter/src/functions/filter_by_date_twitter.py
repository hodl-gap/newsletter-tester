"""
Filter Tweets by Date Node

Filters raw tweets by publication date, removing tweets older than
a configurable threshold. This runs BEFORE LLM-based filtering to
reduce API costs.
"""

from datetime import datetime, timedelta

from src.tracking import debug_log, track_time


def filter_by_date_twitter(state: dict) -> dict:
    """
    Filter tweets by publication date.

    Tweets older than max_age_hours are silently dropped.
    Tweets with missing/unparseable dates are kept.

    Args:
        state: Pipeline state with 'raw_tweets' and optional 'max_age_hours'

    Returns:
        Dict with updated 'raw_tweets' list
    """
    with track_time("filter_by_date_twitter"):
        debug_log("[NODE: filter_by_date_twitter] Entering")

        raw_tweets = state.get("raw_tweets", [])
        settings = state.get("twitter_settings", {})
        max_age_hours = state.get("max_age_hours", settings.get("max_age_hours", 24))

        debug_log(f"[NODE: filter_by_date_twitter] Input: {len(raw_tweets)} tweets, max_age_hours={max_age_hours}")

        if not raw_tweets:
            return {"raw_tweets": []}

        # Calculate cutoff date
        today = datetime.now().date()
        cutoff_date = today - timedelta(days=max_age_hours / 24)

        debug_log(f"[NODE: filter_by_date_twitter] Cutoff date: {cutoff_date.isoformat()}")

        # Filter tweets
        kept_tweets = []
        dropped_count = 0

        for tweet in raw_tweets:
            pub_date_str = tweet.get("pub_date", "")

            # Keep tweets with missing dates (conservative approach)
            if not pub_date_str:
                kept_tweets.append(tweet)
                continue

            # Parse the date
            try:
                pub_date = datetime.strptime(pub_date_str, "%Y-%m-%d").date()
            except ValueError:
                # Keep tweets with unparseable dates
                debug_log(
                    f"[NODE: filter_by_date_twitter] Unparseable date '{pub_date_str}': {tweet.get('full_text', '')[:50]}",
                    "warning"
                )
                kept_tweets.append(tweet)
                continue

            # Apply cutoff filter
            if pub_date >= cutoff_date:
                kept_tweets.append(tweet)
            else:
                dropped_count += 1

        debug_log(f"[NODE: filter_by_date_twitter] Kept: {len(kept_tweets)}, Dropped (old): {dropped_count}")

        return {"raw_tweets": kept_tweets}
