"""
Twitter HTTP Client

Direct HTTP access to Twitter's internal GraphQL API using session cookies.
Replaces Playwright-based browser scraping with pure HTTP requests.

Features:
- No browser fingerprint to detect (eliminates bot detection)
- Cursor-based pagination (fetch multiple pages of tweets)
- Account pool support (rotate across multiple accounts)
- Cookie expiry detection (fail fast on 401/403)
- Rate limit handling from response headers

Usage:
    from src.twitter_client import TwitterClient, AccountPool

    pool = AccountPool()
    client = TwitterClient(pool)
    tweets = client.fetch_user_tweets("elonmusk", max_pages=3)
"""

import json
import time
import random
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

from src.tracking import debug_log

# Twitter's public bearer token (embedded in web client JS, same across all scrapers)
BEARER_TOKEN = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs"
    "%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)

# GraphQL query IDs (these change when Twitter updates their client)
QUERY_IDS = {
    "UserByScreenName": "xmU6X_CKVnQ5lSrCbAmJsg",
    "UserTweets": "QWF3SzpHmykQHsQMixG0cg",
}

# GraphQL features required by Twitter's API
GQL_FEATURES = {
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "tweetypie_unmention_optimization_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "tweet_awards_web_tipping_enabled": False,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": True,
    "rweb_video_timestamps_enabled": True,
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "responsive_web_media_download_video_enabled": False,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_enhance_cards_enabled": False,
}

# Default user agent (keep updated to a recent Chrome version)
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/133.0.0.0 Safari/537.36"
)

# Default data directory
_PROJECT_ROOT = Path(__file__).parent.parent
ACCOUNTS_FILE = _PROJECT_ROOT / "chrome_data" / "twitter_accounts.json"
COOKIES_FILE = _PROJECT_ROOT / "chrome_data" / "twitter_cookies.json"


class CookieExpiredError(Exception):
    """Raised when Twitter session cookies have expired."""
    pass


class RateLimitError(Exception):
    """Raised when Twitter rate limit is hit."""
    def __init__(self, reset_at: float, message: str = "Rate limited"):
        self.reset_at = reset_at
        super().__init__(message)


class Account:
    """A Twitter account with cookies and usage tracking."""

    def __init__(
        self,
        name: str,
        cookies: dict[str, str],
        proxy: Optional[str] = None,
        user_agent: str = DEFAULT_USER_AGENT,
    ):
        self.name = name
        self.cookies = cookies  # {"ct0": "...", "auth_token": "..."}
        self.proxy = proxy
        self.user_agent = user_agent
        self.active = True
        self.error_msg: Optional[str] = None
        self.last_used: Optional[str] = None
        self.total_requests = 0
        self.rate_limit_reset: Optional[float] = None  # Unix timestamp

    @property
    def ct0(self) -> str:
        return self.cookies.get("ct0", "")

    @property
    def auth_token(self) -> str:
        return self.cookies.get("auth_token", "")

    def is_available(self) -> bool:
        """Check if this account is available for use."""
        if not self.active:
            return False
        if self.rate_limit_reset and time.time() < self.rate_limit_reset:
            return False
        return True

    def mark_used(self):
        self.last_used = datetime.now(timezone.utc).isoformat()
        self.total_requests += 1

    def mark_rate_limited(self, reset_at: float):
        self.rate_limit_reset = reset_at
        debug_log(
            f"[TwitterClient] Account '{self.name}' rate limited until "
            f"{datetime.fromtimestamp(reset_at, tz=timezone.utc).isoformat()}",
            "warning",
        )

    def mark_expired(self, reason: str):
        self.active = False
        self.error_msg = reason
        debug_log(f"[TwitterClient] Account '{self.name}' deactivated: {reason}", "error")

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "cookies": self.cookies,
            "proxy": self.proxy,
            "user_agent": self.user_agent,
            "active": self.active,
            "error_msg": self.error_msg,
            "last_used": self.last_used,
            "total_requests": self.total_requests,
        }


class AccountPool:
    """
    Manages a pool of Twitter accounts for rotation.

    Accounts are stored in a JSON file. Starts with a single account
    (loaded from existing cookies), more can be added later.
    """

    def __init__(self, accounts_file: Optional[Path] = None, cookies_file: Optional[Path] = None):
        self.accounts_file = accounts_file or ACCOUNTS_FILE
        self.cookies_file = cookies_file or COOKIES_FILE
        self.accounts: list[Account] = []
        self._load()

    def _load(self):
        """Load accounts from file, falling back to legacy cookie file."""
        if self.accounts_file.exists():
            try:
                with open(self.accounts_file) as f:
                    data = json.load(f)
                for entry in data:
                    account = Account(
                        name=entry["name"],
                        cookies=entry["cookies"],
                        proxy=entry.get("proxy"),
                        user_agent=entry.get("user_agent", DEFAULT_USER_AGENT),
                    )
                    account.active = entry.get("active", True)
                    account.error_msg = entry.get("error_msg")
                    account.last_used = entry.get("last_used")
                    account.total_requests = entry.get("total_requests", 0)
                    self.accounts.append(account)
                debug_log(f"[AccountPool] Loaded {len(self.accounts)} accounts from {self.accounts_file}")
                return
            except Exception as e:
                debug_log(f"[AccountPool] Failed to load accounts file: {e}", "warning")

        # Fall back to legacy single-cookie file (Playwright format)
        if self.cookies_file.exists():
            cookies = self._load_legacy_cookies()
            if cookies:
                account = Account(name="default", cookies=cookies)
                self.accounts.append(account)
                debug_log("[AccountPool] Loaded 1 account from legacy cookies file")
                self.save()
                return

        debug_log("[AccountPool] No accounts available", "error")

    def _load_legacy_cookies(self) -> dict[str, str]:
        """Convert Playwright-format cookies to simple dict."""
        try:
            with open(self.cookies_file) as f:
                playwright_cookies = json.load(f)

            cookies = {}
            for c in playwright_cookies:
                name = c.get("name", "")
                if name in ("ct0", "auth_token", "twid"):
                    cookies[name] = c["value"]

            if "auth_token" not in cookies:
                debug_log("[AccountPool] Legacy cookies missing 'auth_token'", "error")
                return {}

            if "ct0" not in cookies:
                debug_log("[AccountPool] Legacy cookies missing 'ct0'", "error")
                return {}

            return cookies
        except Exception as e:
            debug_log(f"[AccountPool] Failed to load legacy cookies: {e}", "error")
            return {}

    def save(self):
        """Persist account pool to disk."""
        self.accounts_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.accounts_file, "w") as f:
            json.dump([a.to_dict() for a in self.accounts], f, indent=2)

    def get_account(self) -> Account:
        """
        Get an available account, preferring least-recently-used.

        Raises:
            RuntimeError: If no accounts are available.
        """
        available = [a for a in self.accounts if a.is_available()]
        if not available:
            # Check if any are just rate-limited (not expired)
            rate_limited = [
                a for a in self.accounts
                if a.active and a.rate_limit_reset and time.time() < a.rate_limit_reset
            ]
            if rate_limited:
                # Find the one that unlocks soonest
                soonest = min(rate_limited, key=lambda a: a.rate_limit_reset)
                wait_seconds = soonest.rate_limit_reset - time.time()
                raise RateLimitError(
                    soonest.rate_limit_reset,
                    f"All accounts rate limited. Next available in {wait_seconds:.0f}s",
                )

            expired = [a for a in self.accounts if not a.active]
            raise CookieExpiredError(
                f"No active accounts. {len(expired)} account(s) have expired cookies. "
                "Re-run twitter_cdp_login.py to refresh."
            )

        # Sort by last_used (None first = never used), then by total_requests
        available.sort(key=lambda a: (a.last_used or "", a.total_requests))
        return available[0]

    def add_account(self, name: str, cookies: dict[str, str], proxy: Optional[str] = None):
        """Add a new account to the pool."""
        # Remove existing account with same name
        self.accounts = [a for a in self.accounts if a.name != name]
        self.accounts.append(Account(name=name, cookies=cookies, proxy=proxy))
        self.save()
        debug_log(f"[AccountPool] Added account '{name}'")


class TwitterClient:
    """
    HTTP client for Twitter's internal GraphQL API.

    Uses httpx to make direct HTTP requests with session cookies,
    bypassing the need for browser automation entirely.
    """

    def __init__(self, pool: AccountPool, request_delay: tuple[float, float] = (1.0, 3.0)):
        """
        Args:
            pool: Account pool for cookie/auth management.
            request_delay: (min, max) seconds between paginated requests.
        """
        self.pool = pool
        self.request_delay = request_delay
        self._user_id_cache: dict[str, str] = {}

    def _build_headers(self, account: Account) -> dict[str, str]:
        """Build request headers mimicking Twitter's web client."""
        return {
            "authorization": f"Bearer {BEARER_TOKEN}",
            "x-csrf-token": account.ct0,
            "x-twitter-auth-type": "OAuth2Session",
            "x-twitter-active-user": "yes",
            "x-twitter-client-language": "en",
            "content-type": "application/json",
            "user-agent": account.user_agent,
            "referer": "https://x.com/",
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
        }

    def _build_cookies(self, account: Account) -> dict[str, str]:
        """Build cookie dict for httpx."""
        return account.cookies

    def _make_request(
        self, url: str, account: Account, params: Optional[dict] = None
    ) -> dict:
        """
        Make an authenticated GET request to Twitter's API.

        Handles rate limiting and cookie expiry detection.
        """
        headers = self._build_headers(account)
        cookies = self._build_cookies(account)

        transport = None
        if account.proxy:
            transport = httpx.HTTPTransport(proxy=account.proxy)

        with httpx.Client(
            headers=headers,
            cookies=cookies,
            transport=transport,
            timeout=30.0,
            follow_redirects=True,
        ) as client:
            response = client.get(url, params=params)

        account.mark_used()

        # Check for cookie expiry
        if response.status_code in (401, 403):
            account.mark_expired(f"HTTP {response.status_code} — cookies expired")
            self.pool.save()
            raise CookieExpiredError(
                f"Account '{account.name}' returned {response.status_code}. "
                "Cookies have expired. Re-run twitter_cdp_login.py to refresh."
            )

        # Check rate limiting
        rate_remaining = response.headers.get("x-rate-limit-remaining")
        rate_reset = response.headers.get("x-rate-limit-reset")

        if response.status_code == 429:
            reset_at = float(rate_reset) if rate_reset else time.time() + 900
            account.mark_rate_limited(reset_at)
            self.pool.save()
            raise RateLimitError(reset_at, f"Account '{account.name}' rate limited")

        if rate_remaining is not None and int(rate_remaining) <= 1 and rate_reset:
            account.mark_rate_limited(float(rate_reset))

        response.raise_for_status()

        data = response.json()

        # Check for API-level errors
        if "errors" in data and not data.get("data"):
            error_msgs = [e.get("message", "") for e in data["errors"]]
            if any("Could not authenticate" in m for m in error_msgs):
                account.mark_expired(f"API auth error: {error_msgs}")
                self.pool.save()
                raise CookieExpiredError(
                    f"Account '{account.name}' authentication failed: {error_msgs}"
                )
            debug_log(f"[TwitterClient] API errors (non-fatal): {error_msgs}", "warning")

        return data

    def _gql_url(self, operation: str) -> str:
        """Build GraphQL endpoint URL."""
        query_id = QUERY_IDS.get(operation)
        if not query_id:
            raise ValueError(f"Unknown GraphQL operation: {operation}")
        return f"https://x.com/i/api/graphql/{query_id}/{operation}"

    def resolve_user_id(self, screen_name: str) -> str:
        """
        Resolve a Twitter screen name to a numeric user ID.

        Results are cached for the lifetime of the client.
        """
        screen_name = screen_name.lstrip("@").lower()

        if screen_name in self._user_id_cache:
            return self._user_id_cache[screen_name]

        account = self.pool.get_account()
        url = self._gql_url("UserByScreenName")

        variables = json.dumps({"screen_name": screen_name, "withSafetyModeUserFields": True})
        features = json.dumps({
            "hidden_profile_subscriptions_enabled": True,
            "rweb_tipjar_consumption_enabled": True,
            "responsive_web_graphql_exclude_directive_enabled": True,
            "verified_phone_label_enabled": False,
            "subscriptions_verification_info_is_identity_verified_enabled": True,
            "subscriptions_verification_info_verified_since_enabled": True,
            "highlights_tweets_tab_ui_enabled": True,
            "responsive_web_twitter_article_notes_tab_enabled": True,
            "subscriptions_feature_can_gift_premium": True,
            "creator_subscriptions_tweet_preview_api_enabled": True,
            "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
            "responsive_web_graphql_timeline_navigation_enabled": True,
        })

        data = self._make_request(url, account, params={
            "variables": variables,
            "features": features,
        })

        user_result = data.get("data", {}).get("user", {}).get("result", {})
        user_id = user_result.get("rest_id")

        if not user_id:
            raise ValueError(f"Could not resolve user ID for @{screen_name}")

        self._user_id_cache[screen_name] = user_id
        debug_log(f"[TwitterClient] Resolved @{screen_name} -> user_id={user_id}")
        return user_id

    def fetch_user_tweets(
        self,
        screen_name: str,
        max_pages: int = 1,
        tweets_per_page: int = 20,
    ) -> list[dict]:
        """
        Fetch tweets from a user's timeline via GraphQL.

        Args:
            screen_name: Twitter handle (with or without @).
            max_pages: Maximum pages to fetch (1 = first page only).
            tweets_per_page: Tweets to request per page (Twitter may return fewer).

        Returns:
            List of raw GraphQL tweet response dicts, same structure
            as what Playwright intercepted from UserTweets.
        """
        screen_name = screen_name.lstrip("@")
        user_id = self.resolve_user_id(screen_name)

        all_responses = []
        cursor = None

        for page in range(max_pages):
            account = self.pool.get_account()

            variables = {
                "userId": user_id,
                "count": tweets_per_page,
                "includePromotedContent": False,
                "withQuickPromoteEligibilityTweetFields": True,
                "withVoice": True,
                "withV2Timeline": True,
            }
            if cursor:
                variables["cursor"] = cursor

            url = self._gql_url("UserTweets")
            params = {
                "variables": json.dumps(variables),
                "features": json.dumps(GQL_FEATURES),
            }

            debug_log(
                f"[TwitterClient] Fetching @{screen_name} page {page + 1}/{max_pages}"
                + (f" (cursor: {cursor[:20]}...)" if cursor else "")
            )

            data = self._make_request(url, account, params=params)

            # Wrap in same format as Playwright-intercepted responses
            all_responses.append({
                "url": f"{url}?...",
                "data": data,
            })

            # Extract cursor for next page
            cursor = self._extract_cursor(data)
            if not cursor:
                debug_log(f"[TwitterClient] No more pages for @{screen_name} (page {page + 1})")
                break

            # Check if we got any actual tweets this page
            tweet_count = self._count_tweet_entries(data)
            if tweet_count == 0:
                debug_log(f"[TwitterClient] Empty page for @{screen_name}, stopping")
                break

            # Delay between pages
            if page < max_pages - 1:
                delay = random.uniform(*self.request_delay)
                time.sleep(delay)

        return all_responses

    def _extract_cursor(self, data: dict) -> Optional[str]:
        """Extract the bottom cursor for pagination."""
        return self._find_cursor(data, "Bottom")

    def _find_cursor(self, obj, cursor_type: str) -> Optional[str]:
        """Recursively find a cursor of the given type in the response."""
        if isinstance(obj, dict):
            if obj.get("cursorType") == cursor_type:
                return obj.get("value")
            for value in obj.values():
                result = self._find_cursor(value, cursor_type)
                if result:
                    return result
        elif isinstance(obj, list):
            for item in obj:
                result = self._find_cursor(item, cursor_type)
                if result:
                    return result
        return None

    def _count_tweet_entries(self, data: dict) -> int:
        """Count actual tweet entries (excluding cursors and prompts)."""
        entries = self._find_timeline_entries(data)
        return sum(
            1 for e in entries
            if not e.get("entryId", "").startswith(("cursor-", "messageprompt-"))
        )

    def _find_timeline_entries(self, data: dict) -> list[dict]:
        """Extract entries from the TimelineAddEntries instruction."""
        try:
            user_result = data.get("data", {}).get("user", {}).get("result", {})
            timeline = user_result.get("timeline_v2", user_result.get("timeline", {}))
            instructions = timeline.get("timeline", {}).get("instructions", [])
            for inst in instructions:
                if inst.get("type") == "TimelineAddEntries":
                    return inst.get("entries", [])
        except Exception:
            pass
        return []
