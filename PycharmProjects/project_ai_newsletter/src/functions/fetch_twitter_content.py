"""
Fetch Twitter Content Node

Fetches tweets from Twitter/X accounts using direct HTTP requests to
Twitter's internal GraphQL API. Uses session cookies for authentication.

Previous approach used Playwright browser automation to intercept GraphQL
responses. This HTTP-based approach eliminates browser fingerprinting
(the main bot detection vector), is 10-50x faster, and supports
cursor-based pagination for fetching multiple pages of tweets.

Account pool support: multiple accounts can be rotated to distribute
rate limits. Configure accounts in chrome_data/twitter_accounts.json.
"""

import random
import time
from email.utils import parsedate_to_datetime
from typing import TypedDict, Optional

from src.tracking import debug_log, track_time
from src.twitter_client import (
    TwitterClient,
    AccountPool,
    CookieExpiredError,
    RateLimitError,
)


class RawTweet(TypedDict):
    """Raw tweet data from Twitter API."""
    tweet_id: str               # rest_id from API
    handle: str                 # @username
    full_text: str              # Tweet content
    created_at: str             # Original Twitter format
    pub_date: str               # Parsed to YYYY-MM-DD
    url: str                    # Tweet URL
    views: int
    likes: int
    retweets: int
    replies: int
    is_retweet: bool
    is_quote_tweet: bool
    quoted_text: Optional[str]
    # Fields for compatibility with filter_business_news
    link: str                   # Same as url
    title: str                  # Same as full_text
    description: str            # Quoted text or empty
    source_name: str            # Same as handle


# Delay between scraping different accounts (seconds)
# Much shorter than browser-based approach since HTTP has no fingerprint to detect
DEFAULT_SCRAPE_DELAY_MIN = 3
DEFAULT_SCRAPE_DELAY_MAX = 8

# Retry configuration
MAX_RETRIES = 2
RETRY_DELAY = 10

# Pagination: how many pages of tweets to fetch per account
DEFAULT_MAX_PAGES = 1


# Module-level client (initialized once per pipeline run)
_client: Optional[TwitterClient] = None


def _get_client() -> TwitterClient:
    """Get or create the shared TwitterClient instance."""
    global _client
    if _client is None:
        pool = AccountPool()
        _client = TwitterClient(pool)
    return _client


def fetch_twitter_content(state: dict) -> dict:
    """
    Fetch tweets from Twitter accounts using HTTP GraphQL API.

    Args:
        state: Pipeline state with 'twitter_accounts' and 'twitter_settings'

    Returns:
        Dict with 'raw_tweets' list (adapted for filter_business_news compatibility)
    """
    with track_time("fetch_twitter_content"):
        debug_log("[NODE: fetch_twitter_content] Entering (HTTP mode)")

        twitter_accounts = state.get("twitter_accounts", [])
        settings = state.get("twitter_settings", {})
        scrape_delay_min = settings.get("scrape_delay_min", DEFAULT_SCRAPE_DELAY_MIN)
        scrape_delay_max = settings.get("scrape_delay_max", DEFAULT_SCRAPE_DELAY_MAX)
        max_pages = settings.get("max_pages", DEFAULT_MAX_PAGES)

        debug_log(f"[NODE: fetch_twitter_content] Processing {len(twitter_accounts)} accounts")
        debug_log(f"[NODE: fetch_twitter_content] Delay between accounts: {scrape_delay_min}-{scrape_delay_max}s")
        debug_log(f"[NODE: fetch_twitter_content] Max pages per account: {max_pages}")

        if not twitter_accounts:
            return {"raw_tweets": []}

        client = _get_client()
        all_tweets: list[RawTweet] = []
        failed_accounts: list[str] = []

        for i, account in enumerate(twitter_accounts):
            handle = account.get("handle", "")
            debug_log(f"[NODE: fetch_twitter_content] Scraping {handle} ({i+1}/{len(twitter_accounts)})")

            tweets = _scrape_account_with_retry(client, handle, max_pages)
            all_tweets.extend(tweets)

            debug_log(f"[NODE: fetch_twitter_content] Got {len(tweets)} tweets from {handle}")

            if not tweets:
                failed_accounts.append(handle)

            # Delay between accounts (skip for last account)
            if i < len(twitter_accounts) - 1:
                delay = random.uniform(scrape_delay_min, scrape_delay_max)
                debug_log(f"[NODE: fetch_twitter_content] Waiting {delay:.1f}s before next account...")
                time.sleep(delay)

        # Save account pool state (usage stats, rate limit info)
        client.pool.save()

        # Deduplicate by tweet_id
        seen_ids = set()
        unique_tweets = []
        for tweet in all_tweets:
            if tweet["tweet_id"] not in seen_ids:
                seen_ids.add(tweet["tweet_id"])
                unique_tweets.append(tweet)

        debug_log(f"[NODE: fetch_twitter_content] Total tweets: {len(unique_tweets)} (after dedup)")
        if failed_accounts:
            debug_log(f"[NODE: fetch_twitter_content] Failed accounts: {failed_accounts}", "warning")
        debug_log(f"[NODE: fetch_twitter_content] Output: {len(unique_tweets)} raw_tweets")

        return {"raw_tweets": unique_tweets}


def _scrape_account_with_retry(
    client: TwitterClient, handle: str, max_pages: int
) -> list[RawTweet]:
    """
    Scrape a single Twitter account with retry logic.

    Args:
        client: TwitterClient instance.
        handle: Twitter handle (e.g., "@a16z").
        max_pages: Max pages of tweets to fetch.

    Returns:
        List of RawTweet dicts.
    """
    for attempt in range(MAX_RETRIES + 1):
        try:
            return _scrape_single_account(client, handle, max_pages)
        except CookieExpiredError:
            # Don't retry on expired cookies — all accounts are likely expired
            debug_log(
                f"[NODE: fetch_twitter_content] Cookie expired for {handle}. "
                "Re-run twitter_cdp_login.py to refresh.",
                "error",
            )
            return []
        except RateLimitError as e:
            wait = e.reset_at - time.time()
            if wait > 300:  # Don't wait more than 5 minutes
                debug_log(
                    f"[NODE: fetch_twitter_content] Rate limited for {wait:.0f}s, skipping {handle}",
                    "warning",
                )
                return []
            debug_log(
                f"[NODE: fetch_twitter_content] Rate limited, waiting {wait:.0f}s...",
                "warning",
            )
            time.sleep(max(wait, 0) + 1)
            # Retry after rate limit expires
        except Exception as e:
            if attempt < MAX_RETRIES:
                debug_log(
                    f"[NODE: fetch_twitter_content] Attempt {attempt + 1} failed for {handle}: {e}",
                    "warning",
                )
                debug_log(
                    f"[NODE: fetch_twitter_content] Retrying in {RETRY_DELAY}s...",
                    "warning",
                )
                time.sleep(RETRY_DELAY)
            else:
                debug_log(
                    f"[NODE: fetch_twitter_content] Max retries reached for {handle}: {e}",
                    "error",
                )
                return []

    return []


def _scrape_single_account(
    client: TwitterClient, handle: str, max_pages: int
) -> list[RawTweet]:
    """
    Fetch tweets from a single Twitter account via HTTP.

    Args:
        client: TwitterClient instance.
        handle: Twitter handle (e.g., "@a16z").
        max_pages: Max pages of tweets to fetch.

    Returns:
        List of RawTweet dicts.
    """
    responses = client.fetch_user_tweets(
        screen_name=handle,
        max_pages=max_pages,
    )

    tweets = _parse_twitter_responses(responses, handle)
    return tweets


# =============================================================================
# Response Parsing (unchanged from Playwright version — same GraphQL structure)
# =============================================================================


def _parse_twitter_responses(responses: list[dict], handle: str) -> list[RawTweet]:
    """Parse captured Twitter API responses to extract tweets."""
    tweets: list[RawTweet] = []

    for resp in responses:
        data = resp.get("data", {})

        try:
            # Navigate GraphQL structure
            user_result = data.get("data", {}).get("user", {}).get("result", {})
            timeline = user_result.get("timeline_v2", user_result.get("timeline", {}))
            timeline_data = timeline.get("timeline", {})
            instructions = timeline_data.get("instructions", [])

            for instruction in instructions:
                entries = []

                if instruction.get("type") == "TimelineAddEntries":
                    entries = instruction.get("entries", [])
                elif instruction.get("type") == "TimelinePinEntry":
                    entry = instruction.get("entry")
                    if entry:
                        entries = [entry]

                for entry in entries:
                    tweet = _parse_tweet_entry(entry, handle)
                    if tweet:
                        tweets.append(tweet)

                    module_tweets = _parse_module_entry(entry, handle)
                    tweets.extend(module_tweets)

        except Exception as e:
            debug_log(f"[NODE: fetch_twitter_content] Error parsing response: {e}", "warning")

    return tweets


def _parse_module_entry(entry: dict, handle: str) -> list[RawTweet]:
    """Parse a TimelineTimelineModule entry (conversation thread)."""
    if not entry:
        return []

    content = entry.get("content", {})
    if content.get("entryType") != "TimelineTimelineModule":
        return []

    entry_id = entry.get("entryId", "")
    if "profile-conversation" not in entry_id:
        return []

    tweets = []
    items = content.get("items", [])

    for item_wrapper in items:
        item = item_wrapper.get("item", {})
        item_content = item.get("itemContent", {})

        if item_content.get("itemType") != "TimelineTweet":
            continue

        tweet_result = item_content.get("tweet_results", {}).get("result", {})
        tweet = _extract_tweet_from_result(tweet_result, handle)
        if tweet:
            tweets.append(tweet)

    return tweets


def _parse_tweet_entry(entry: dict, handle: str) -> Optional[RawTweet]:
    """Parse a single tweet entry from the timeline."""
    if not entry:
        return None

    content = entry.get("content", {})
    if content.get("entryType") != "TimelineTimelineItem":
        return None

    item = content.get("itemContent", {})
    if item.get("itemType") != "TimelineTweet":
        return None

    tweet_result = item.get("tweet_results", {}).get("result", {})
    return _extract_tweet_from_result(tweet_result, handle)


def _extract_tweet_from_result(tweet_result: dict, handle: str) -> Optional[RawTweet]:
    """Extract tweet data from a tweet_results.result object."""
    if not tweet_result:
        return None

    if tweet_result.get("__typename") == "TweetTombstone":
        return None

    legacy = tweet_result.get("legacy", {})
    full_text = legacy.get("full_text", "")
    created_at = legacy.get("created_at", "")
    tweet_id = tweet_result.get("rest_id", "")

    if not full_text or not tweet_id:
        return None

    # Skip retweets
    if full_text.startswith("RT @"):
        debug_log(f"[NODE: fetch_twitter_content] Skipping retweet: {full_text[:50]}...")
        return None

    # Engagement metrics
    views_data = tweet_result.get("views", {})
    views = int(views_data.get("count", "0")) if views_data.get("count") else 0
    likes = legacy.get("favorite_count", 0)
    retweets = legacy.get("retweet_count", 0)
    replies = legacy.get("reply_count", 0)

    # Quote tweet handling
    quoted = tweet_result.get("quoted_status_result", {}).get("result", {})
    quoted_text = quoted.get("legacy", {}).get("full_text", "") if quoted else ""
    is_quote_tweet = bool(quoted_text)

    pub_date = _parse_twitter_date(created_at)

    username = handle.lstrip("@")
    url = f"https://x.com/{username}/status/{tweet_id}"

    tweet: RawTweet = {
        "tweet_id": tweet_id,
        "handle": handle,
        "full_text": full_text,
        "created_at": created_at,
        "pub_date": pub_date,
        "url": url,
        "views": views,
        "likes": likes,
        "retweets": retweets,
        "replies": replies,
        "is_retweet": False,
        "is_quote_tweet": is_quote_tweet,
        "quoted_text": quoted_text if is_quote_tweet else None,
        "link": url,
        "title": full_text,
        "description": quoted_text if is_quote_tweet else "",
        "source_name": handle,
    }

    return tweet


def _parse_twitter_date(created_at: str) -> str:
    """Parse Twitter date format to YYYY-MM-DD."""
    if not created_at:
        return ""

    try:
        dt = parsedate_to_datetime(created_at)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return ""
