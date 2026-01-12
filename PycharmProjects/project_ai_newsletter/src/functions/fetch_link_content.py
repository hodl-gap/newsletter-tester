"""
Fetch Link Content Node

Detects link-only tweets (minimal text with URL) and fetches the URL content
to provide better context for filtering and summarization.

Detection: Tweet text (minus URL) < 50 characters
Success: Populates 'description' and 'full_text' with fetched content
Failure: Moves tweet to discarded_tweets with reason
"""

import re
from typing import Optional

import requests
from bs4 import BeautifulSoup

from src.tracking import debug_log, track_time


# URL pattern to match http/https URLs
URL_PATTERN = re.compile(r'https?://\S+')

# Threshold for detecting link-only tweets
LINK_ONLY_THRESHOLD = 50

# Request timeout in seconds
REQUEST_TIMEOUT = 5

# User agent for requests
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def _extract_urls(text: str) -> list[str]:
    """Extract all URLs from text."""
    return URL_PATTERN.findall(text)


def _get_text_without_urls(text: str) -> str:
    """Remove URLs from text and return remaining content."""
    return URL_PATTERN.sub('', text).strip()


def _is_link_only_tweet(full_text: str) -> bool:
    """
    Detect if a tweet is link-only (minimal text with URL).

    A tweet is considered link-only if the text without URLs
    is less than LINK_ONLY_THRESHOLD characters.
    """
    text_without_urls = _get_text_without_urls(full_text)
    return len(text_without_urls) < LINK_ONLY_THRESHOLD


def _expand_url(short_url: str) -> str:
    """
    Expand shortened URLs (like t.co) by following redirects.

    Returns the final URL after redirects, or the original URL on failure.
    """
    try:
        response = requests.head(
            short_url,
            allow_redirects=True,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT}
        )
        return response.url
    except Exception as e:
        debug_log(f"[fetch_link_content] Failed to expand URL {short_url}: {e}", "warning")
        return short_url


def _fetch_page_content(url: str) -> Optional[dict]:
    """
    Fetch page and extract title and description.

    Returns:
        Dict with 'title' and 'description' on success, None on failure.
    """
    try:
        response = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT}
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # Extract title
        title = ""
        title_tag = soup.find('title')
        if title_tag:
            title = title_tag.get_text(strip=True)

        # Try og:title if regular title is empty
        if not title:
            og_title = soup.find('meta', property='og:title')
            if og_title and og_title.get('content'):
                title = og_title['content']

        # Extract description from meta tags
        description = ""

        # Try og:description first (usually better quality)
        og_desc = soup.find('meta', property='og:description')
        if og_desc and og_desc.get('content'):
            description = og_desc['content']

        # Fall back to meta description
        if not description:
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            if meta_desc and meta_desc.get('content'):
                description = meta_desc['content']

        # Fall back to first paragraph if no meta description
        if not description:
            first_p = soup.find('p')
            if first_p:
                description = first_p.get_text(strip=True)[:500]

        # Need at least title or description to be useful
        if not title and not description:
            return None

        return {
            "title": title,
            "description": description,
        }

    except requests.exceptions.Timeout:
        debug_log(f"[fetch_link_content] Timeout fetching {url}", "warning")
        return None
    except requests.exceptions.RequestException as e:
        debug_log(f"[fetch_link_content] Request error for {url}: {e}", "warning")
        return None
    except Exception as e:
        debug_log(f"[fetch_link_content] Error parsing {url}: {e}", "warning")
        return None


def fetch_link_content(state: dict) -> dict:
    """
    Detect link-only tweets and fetch URL content.

    For tweets where text (minus URL) is < 50 chars:
    - Expand shortened URLs (t.co -> actual URL)
    - Fetch page content (title, description)
    - Update tweet's 'description' and 'full_text' fields
    - On failure, move to discarded_tweets

    Args:
        state: Pipeline state with 'raw_tweets'

    Returns:
        Dict with updated 'raw_tweets' and 'discarded_tweets'
    """
    with track_time("fetch_link_content"):
        debug_log("[NODE: fetch_link_content] Entering")

        raw_tweets = state.get("raw_tweets", [])
        discarded_tweets = state.get("discarded_tweets", [])

        debug_log(f"[NODE: fetch_link_content] Processing {len(raw_tweets)} tweets")

        if not raw_tweets:
            return {"raw_tweets": [], "discarded_tweets": discarded_tweets}

        # Process tweets
        processed_tweets = []
        link_only_count = 0
        fetched_count = 0
        failed_count = 0

        for tweet in raw_tweets:
            full_text = tweet.get("full_text", "")

            # Check if this is a link-only tweet
            if not _is_link_only_tweet(full_text):
                # Not link-only, keep as-is
                processed_tweets.append(tweet)
                continue

            link_only_count += 1

            # Extract URLs from tweet
            urls = _extract_urls(full_text)
            if not urls:
                # No URLs found (shouldn't happen for link-only, but handle it)
                processed_tweets.append(tweet)
                continue

            # Try to fetch content from the first URL
            url = urls[0]

            # Expand shortened URL
            expanded_url = _expand_url(url)
            debug_log(f"[NODE: fetch_link_content] Expanded {url} -> {expanded_url}")

            # Fetch page content
            content = _fetch_page_content(expanded_url)

            if content:
                # Success - update tweet fields
                fetched_title = content.get("title", "")
                fetched_desc = content.get("description", "")

                # Build combined content for full_text
                combined_content = f"{fetched_title}. {fetched_desc}" if fetched_desc else fetched_title

                # Update tweet
                tweet["description"] = fetched_desc
                tweet["full_text"] = combined_content
                tweet["title"] = combined_content  # title is same as full_text for adapter
                tweet["content_fetched"] = True
                tweet["fetched_url"] = expanded_url

                processed_tweets.append(tweet)
                fetched_count += 1

                debug_log(
                    f"[NODE: fetch_link_content] Fetched content for @{tweet.get('handle', '?')}: "
                    f"{fetched_title[:50]}..."
                )
            else:
                # Failed - move to discarded
                failed_count += 1

                discarded_tweet = {
                    "url": tweet.get("url", ""),
                    "title": full_text,
                    "source": tweet.get("handle", ""),
                    "pub_date": tweet.get("pub_date", ""),
                    "discard_reason": "url_fetch_failed",
                    "fetched_url": expanded_url,
                }
                discarded_tweets.append(discarded_tweet)

                debug_log(
                    f"[NODE: fetch_link_content] Failed to fetch for @{tweet.get('handle', '?')}: {url}",
                    "warning"
                )

        debug_log(
            f"[NODE: fetch_link_content] Results: "
            f"link_only={link_only_count}, fetched={fetched_count}, failed={failed_count}"
        )

        return {
            "raw_tweets": processed_tweets,
            "discarded_tweets": discarded_tweets,
        }
