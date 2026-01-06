"""
Analyze Account Activity Node

Analyzes scraped tweet data to determine account activity status.
Calculates metrics like last_tweet_date, tweets_per_day, activity_score.
Marks accounts as "active" or "inactive" based on posting frequency.
"""

from datetime import datetime, timedelta
from typing import TypedDict, Optional
from collections import defaultdict

from src.tracking import debug_log, track_time


class AccountActivityResult(TypedDict):
    """Activity analysis result for a single account."""
    handle: str
    category: str
    status: str  # "active", "inactive", "error"
    last_tweet_date: Optional[str]
    tweets_in_window: int
    avg_tweets_per_day: float
    notes: Optional[str]
    last_checked: str


# Default inactivity threshold (days without tweets)
DEFAULT_INACTIVITY_THRESHOLD_DAYS = 14


def analyze_account_activity(state: dict) -> dict:
    """
    Analyze account activity based on scraped tweets.

    Args:
        state: Pipeline state with:
            - 'raw_tweets': List of RawTweet dicts
            - 'twitter_accounts': List of account dicts with handle/category
            - 'twitter_settings': Settings dict with inactivity_threshold_days

    Returns:
        Dict with 'activity_results' list of AccountActivityResult
    """
    with track_time("analyze_account_activity"):
        debug_log("[NODE: analyze_account_activity] Entering")

        raw_tweets = state.get("raw_tweets", [])
        twitter_accounts = state.get("twitter_accounts", [])
        settings = state.get("twitter_settings", {})

        inactivity_threshold = settings.get(
            "inactivity_threshold_days",
            DEFAULT_INACTIVITY_THRESHOLD_DAYS
        )

        debug_log(f"[NODE: analyze_account_activity] Analyzing {len(twitter_accounts)} accounts")
        debug_log(f"[NODE: analyze_account_activity] Inactivity threshold: {inactivity_threshold} days")
        debug_log(f"[NODE: analyze_account_activity] Total tweets to analyze: {len(raw_tweets)}")

        # Build lookup map for account categories
        account_categories = {
            acc["handle"]: acc.get("category", "unknown")
            for acc in twitter_accounts
        }

        # Group tweets by handle
        tweets_by_handle: dict[str, list[dict]] = defaultdict(list)
        for tweet in raw_tweets:
            handle = tweet.get("handle", "")
            if handle:
                tweets_by_handle[handle].append(tweet)

        # Analyze each account
        now = datetime.now()
        cutoff_date = now - timedelta(days=inactivity_threshold)
        last_checked = now.isoformat(timespec="seconds") + "Z"

        activity_results: list[AccountActivityResult] = []
        active_count = 0
        inactive_count = 0
        error_count = 0

        for account in twitter_accounts:
            handle = account.get("handle", "")
            category = account.get("category", "unknown")
            tweets = tweets_by_handle.get(handle, [])

            result = _analyze_single_account(
                handle=handle,
                category=category,
                tweets=tweets,
                cutoff_date=cutoff_date,
                inactivity_threshold=inactivity_threshold,
                last_checked=last_checked,
            )

            activity_results.append(result)

            if result["status"] == "active":
                active_count += 1
            elif result["status"] == "inactive":
                inactive_count += 1
            else:
                error_count += 1

            debug_log(
                f"[NODE: analyze_account_activity] {handle}: "
                f"{result['status']} (tweets: {result['tweets_in_window']}, "
                f"last: {result['last_tweet_date'] or 'N/A'})"
            )

        debug_log(f"[NODE: analyze_account_activity] Results: "
                  f"active={active_count}, inactive={inactive_count}, error={error_count}")

        return {"activity_results": activity_results}


def _analyze_single_account(
    handle: str,
    category: str,
    tweets: list[dict],
    cutoff_date: datetime,
    inactivity_threshold: int,
    last_checked: str,
) -> AccountActivityResult:
    """
    Analyze a single account's activity.

    Args:
        handle: Twitter handle
        category: Account category
        tweets: List of tweets for this account
        cutoff_date: Date threshold for "active" status
        inactivity_threshold: Days threshold for inactivity
        last_checked: ISO timestamp of analysis

    Returns:
        AccountActivityResult dict
    """
    # No tweets captured = error (scraping may have failed)
    if not tweets:
        return AccountActivityResult(
            handle=handle,
            category=category,
            status="error",
            last_tweet_date=None,
            tweets_in_window=0,
            avg_tweets_per_day=0.0,
            notes="No tweets captured - scraping may have failed or account is empty",
            last_checked=last_checked,
        )

    # Parse tweet dates and find metrics
    tweet_dates: list[datetime] = []
    for tweet in tweets:
        pub_date = tweet.get("pub_date", "")
        if pub_date:
            try:
                dt = datetime.strptime(pub_date, "%Y-%m-%d")
                tweet_dates.append(dt)
            except ValueError:
                pass

    if not tweet_dates:
        return AccountActivityResult(
            handle=handle,
            category=category,
            status="error",
            last_tweet_date=None,
            tweets_in_window=0,
            avg_tweets_per_day=0.0,
            notes="No parseable dates in tweets",
            last_checked=last_checked,
        )

    # Calculate metrics
    last_tweet_dt = max(tweet_dates)
    last_tweet_date = last_tweet_dt.strftime("%Y-%m-%d")

    # Count tweets within the activity window
    tweets_in_window = sum(1 for dt in tweet_dates if dt >= cutoff_date)

    # Calculate avg tweets per day (within window)
    avg_tweets_per_day = round(tweets_in_window / inactivity_threshold, 2)

    # Determine status
    is_active = last_tweet_dt >= cutoff_date

    if is_active:
        return AccountActivityResult(
            handle=handle,
            category=category,
            status="active",
            last_tweet_date=last_tweet_date,
            tweets_in_window=tweets_in_window,
            avg_tweets_per_day=avg_tweets_per_day,
            notes=None,
            last_checked=last_checked,
        )
    else:
        days_since_last = (datetime.now() - last_tweet_dt).days
        return AccountActivityResult(
            handle=handle,
            category=category,
            status="inactive",
            last_tweet_date=last_tweet_date,
            tweets_in_window=tweets_in_window,
            avg_tweets_per_day=avg_tweets_per_day,
            notes=f"No tweets in {days_since_last} days",
            last_checked=last_checked,
        )
