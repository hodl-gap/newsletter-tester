"""
Fetch Twitter Content Node

Scrapes tweets from Twitter/X accounts using Playwright to intercept
GraphQL API responses. Implements rate limiting between accounts.

Uses persistent browser context to maintain session state and avoid
being detected as a bot by Twitter.
"""

import os
import random
import time
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import TypedDict, Optional

from playwright.sync_api import sync_playwright, Response

from src.tracking import debug_log, track_time


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


# Default delay between scraping accounts (seconds)
DEFAULT_SCRAPE_DELAY_MIN = 55
DEFAULT_SCRAPE_DELAY_MAX = 65

# Playwright timeout (ms)
PAGE_TIMEOUT = 30000
WAIT_FOR_API = 5000
API_RESPONSE_TIMEOUT = 15000  # Timeout for expect_response

# Retry configuration
MAX_RETRIES = 2
RETRY_DELAY = 10

# Persistent browser data directory (relative to project root)
BROWSER_DATA_DIR = Path(__file__).parent.parent.parent / "chrome_data"
COOKIES_FILE = BROWSER_DATA_DIR / "twitter_cookies.json"


def _load_cookies() -> list[dict]:
    """Load saved Twitter cookies from JSON file."""
    if COOKIES_FILE.exists():
        try:
            import json
            with open(COOKIES_FILE, 'r') as f:
                cookies = json.load(f)
            debug_log(f"[NODE: fetch_twitter_content] Loaded {len(cookies)} cookies from {COOKIES_FILE}")
            return cookies
        except Exception as e:
            debug_log(f"[NODE: fetch_twitter_content] Failed to load cookies: {e}", "warning")
    return []


def fetch_twitter_content(state: dict) -> dict:
    """
    Fetch tweets from Twitter accounts using Playwright.

    Args:
        state: Pipeline state with 'twitter_accounts' and 'twitter_settings'

    Returns:
        Dict with 'raw_tweets' list (adapted for filter_business_news compatibility)
    """
    with track_time("fetch_twitter_content"):
        debug_log("[NODE: fetch_twitter_content] Entering")

        twitter_accounts = state.get("twitter_accounts", [])
        settings = state.get("twitter_settings", {})
        scrape_delay_min = settings.get("scrape_delay_min", DEFAULT_SCRAPE_DELAY_MIN)
        scrape_delay_max = settings.get("scrape_delay_max", DEFAULT_SCRAPE_DELAY_MAX)

        debug_log(f"[NODE: fetch_twitter_content] Processing {len(twitter_accounts)} accounts")
        debug_log(f"[NODE: fetch_twitter_content] Delay between accounts: {scrape_delay_min}-{scrape_delay_max}s (randomized)")

        if not twitter_accounts:
            return {"raw_tweets": []}

        all_tweets: list[RawTweet] = []

        for i, account in enumerate(twitter_accounts):
            handle = account.get("handle", "")
            debug_log(f"[NODE: fetch_twitter_content] Scraping {handle} ({i+1}/{len(twitter_accounts)})")

            tweets = _scrape_account_with_retry(handle)
            all_tweets.extend(tweets)

            debug_log(f"[NODE: fetch_twitter_content] Got {len(tweets)} tweets from {handle}")

            # Rate limit delay (skip for last account)
            if i < len(twitter_accounts) - 1:
                delay = random.uniform(scrape_delay_min, scrape_delay_max)
                debug_log(f"[NODE: fetch_twitter_content] Waiting {delay:.1f}s before next account...")
                time.sleep(delay)

        # Deduplicate by tweet_id
        seen_ids = set()
        unique_tweets = []
        for tweet in all_tweets:
            if tweet["tweet_id"] not in seen_ids:
                seen_ids.add(tweet["tweet_id"])
                unique_tweets.append(tweet)

        debug_log(f"[NODE: fetch_twitter_content] Total tweets: {len(unique_tweets)} (after dedup)")
        debug_log(f"[NODE: fetch_twitter_content] Output: {len(unique_tweets)} raw_tweets")

        return {"raw_tweets": unique_tweets}


def _scrape_account_with_retry(handle: str) -> list[RawTweet]:
    """
    Scrape a single Twitter account with retry logic.

    Args:
        handle: Twitter handle (e.g., "@a16z")

    Returns:
        List of RawTweet dicts
    """
    for attempt in range(MAX_RETRIES + 1):
        try:
            return _scrape_single_account(handle)
        except Exception as e:
            if attempt < MAX_RETRIES:
                debug_log(f"[NODE: fetch_twitter_content] Attempt {attempt + 1} failed for {handle}: {e}", "warning")
                debug_log(f"[NODE: fetch_twitter_content] Retrying in {RETRY_DELAY}s...", "warning")
                time.sleep(RETRY_DELAY)
            else:
                debug_log(f"[NODE: fetch_twitter_content] Max retries reached for {handle}: {e}", "error")
                return []

    return []


def _scrape_single_account(handle: str) -> list[RawTweet]:
    """
    Scrape tweets from a single Twitter account using Playwright.

    Uses persistent browser context and expect_response pattern
    for reliable GraphQL API interception.

    Args:
        handle: Twitter handle (e.g., "@a16z")

    Returns:
        List of RawTweet dicts
    """
    # Remove @ prefix for URL
    username = handle.lstrip("@")
    profile_url = f"https://x.com/{username}"

    # Ensure browser data directory exists
    browser_data_dir = str(BROWSER_DATA_DIR.resolve())
    os.makedirs(browser_data_dir, exist_ok=True)

    debug_log(f"[NODE: fetch_twitter_content] Launching Playwright for {profile_url}")
    debug_log(f"[NODE: fetch_twitter_content] Using persistent context: {browser_data_dir}")

    captured_responses: list[dict] = []

    with sync_playwright() as p:
        # Use persistent context to maintain cookies/session state
        # This is the key difference - Twitter serves different content to fresh vs returning browsers
        context = p.chromium.launch_persistent_context(
            user_data_dir=browser_data_dir,
            headless=True,
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            # Hide automation signals
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--no-first-run",
                "--no-default-browser-check",
            ],
            ignore_default_args=["--enable-automation"],
        )
        page = context.new_page()

        # Load saved cookies (from CDP login)
        cookies = _load_cookies()
        if cookies:
            context.add_cookies(cookies)
            debug_log(f"[NODE: fetch_twitter_content] Injected {len(cookies)} cookies")

        try:
            # Use expect_response to explicitly wait for UserTweets API response
            # This is more reliable than passive listening
            with page.expect_response(
                lambda response: "UserTweets" in response.url and response.status == 200,
                timeout=API_RESPONSE_TIMEOUT
            ) as response_info:
                # Navigate with domcontentloaded (faster, doesn't wait for all resources)
                page.goto(profile_url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)

            # Get the captured response
            response = response_info.value
            debug_log(f"[NODE: fetch_twitter_content] Captured UserTweets response: {response.url[:80]}...")

            try:
                json_data = response.json()
                captured_responses.append({
                    "url": response.url,
                    "data": json_data
                })
            except Exception as e:
                debug_log(f"[NODE: fetch_twitter_content] Failed to parse response JSON: {e}", "warning")

        except Exception as e:
            debug_log(f"[NODE: fetch_twitter_content] expect_response failed: {e}", "warning")
            # Fallback: try passive capture if expect_response times out
            debug_log("[NODE: fetch_twitter_content] Falling back to passive response capture...")
            captured_responses = _fallback_passive_capture(page, profile_url)

        context.close()

    # Parse captured responses
    tweets = _parse_twitter_responses(captured_responses, handle)

    return tweets


def _fallback_passive_capture(page, profile_url: str) -> list[dict]:
    """
    Fallback method using passive response capture.
    Used when expect_response times out.
    """
    captured: list[dict] = []

    def handle_response(response: Response):
        url = response.url
        if "UserTweets" in url:
            try:
                if response.status == 200:
                    content_type = response.headers.get("content-type", "")
                    if "json" in content_type:
                        body = response.json()
                        captured.append({"url": url, "data": body})
                        debug_log(f"[NODE: fetch_twitter_content] Fallback captured: {url[:80]}...")
            except Exception:
                pass

    page.on("response", handle_response)

    try:
        page.goto(profile_url, wait_until="networkidle", timeout=PAGE_TIMEOUT)
        page.wait_for_timeout(WAIT_FOR_API)
    except Exception as e:
        debug_log(f"[NODE: fetch_twitter_content] Fallback navigation note: {e}", "warning")

    return captured


def _parse_twitter_responses(responses: list[dict], handle: str) -> list[RawTweet]:
    """
    Parse captured Twitter API responses to extract tweets.

    Args:
        responses: List of captured API responses
        handle: Twitter handle for this account

    Returns:
        List of RawTweet dicts
    """
    tweets: list[RawTweet] = []

    for resp in responses:
        if "UserTweets" not in resp.get("url", ""):
            continue

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

        except Exception as e:
            debug_log(f"[NODE: fetch_twitter_content] Error parsing response: {e}", "warning")

    return tweets


def _parse_tweet_entry(entry: dict, handle: str) -> Optional[RawTweet]:
    """
    Parse a single tweet entry from the timeline.

    Args:
        entry: Tweet entry from API response
        handle: Twitter handle

    Returns:
        RawTweet dict or None if not a valid tweet
    """
    if not entry:
        return None

    content = entry.get("content", {})
    if content.get("entryType") != "TimelineTimelineItem":
        return None

    item = content.get("itemContent", {})
    if item.get("itemType") != "TimelineTweet":
        return None

    tweet_result = item.get("tweet_results", {}).get("result", {})
    if not tweet_result:
        return None

    # Handle tombstone (deleted/unavailable tweets)
    if tweet_result.get("__typename") == "TweetTombstone":
        return None

    # Extract tweet data
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

    # Parse date
    pub_date = _parse_twitter_date(created_at)

    # Construct tweet URL
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
        # Compatibility fields for filter_business_news
        "link": url,
        "title": full_text,
        "description": quoted_text if is_quote_tweet else "",
        "source_name": handle,
    }

    return tweet


def _parse_twitter_date(created_at: str) -> str:
    """
    Parse Twitter date format to YYYY-MM-DD.

    Args:
        created_at: Twitter date format (e.g., "Tue Dec 30 11:54:33 +0000 2025")

    Returns:
        Date string in YYYY-MM-DD format, or empty string on failure
    """
    if not created_at:
        return ""

    try:
        dt = parsedate_to_datetime(created_at)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return ""
