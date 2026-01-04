"""
Test AI Category RSS Feeds

This node tests AI-specific category RSS feeds for a given base URL.
Tries common AI category paths like /category/artificial-intelligence/feed/, etc.
"""

import re
from typing import TypedDict, Optional
import httpx
from urllib.parse import urljoin

from src.tracking import debug_log


# AI category preset paths to try
AI_CATEGORY_PATHS = [
    "/category/artificial-intelligence/feed/",
    "/category/ai/feed/",
    "/category/machine-learning/feed/",
    "/tag/artificial-intelligence/feed/",
    "/tag/ai/feed/",
    "/tag/machine-learning/feed/",
    "/topic/ai/feed/",
    "/topic/artificial-intelligence/feed/",
]

# Timeout for HTTP requests (seconds)
REQUEST_TIMEOUT = 10


class AIFeedResult(TypedDict):
    url: str
    status: str  # "available", "paywalled", "unavailable"
    ai_feed_url: Optional[str]
    method: str  # "preset"
    notes: Optional[str]
    article_titles: list[str]


def is_valid_rss(content: str) -> bool:
    """
    Check if content looks like a valid RSS/Atom feed.
    """
    content_lower = content.lower()[:1000]
    return any([
        "<rss" in content_lower,
        "<feed" in content_lower,
        "<atom" in content_lower,
        "<?xml" in content_lower and "channel" in content_lower,
    ])


def extract_article_titles(content: str, max_titles: int = 10) -> list[str]:
    """
    Extract article titles from RSS/Atom feed content.
    """
    titles = []

    # Try RSS <title> tags (skip first one which is feed title)
    rss_titles = re.findall(r'<title[^>]*>(?:<!\[CDATA\[)?([^<\]]+)(?:\]\]>)?</title>', content, re.IGNORECASE)
    if rss_titles:
        titles = [t.strip() for t in rss_titles[1:max_titles + 1] if t.strip()]

    # If no titles found, try Atom format
    if not titles:
        atom_titles = re.findall(r'<entry[^>]*>.*?<title[^>]*>([^<]+)</title>', content, re.IGNORECASE | re.DOTALL)
        titles = [t.strip() for t in atom_titles[:max_titles] if t.strip()]

    return titles


def test_ai_category(url: str) -> AIFeedResult:
    """
    Test AI category RSS paths for a given base URL.

    Args:
        url: Base URL to test (e.g., "https://example.com")

    Returns:
        AIFeedResult with status and ai_feed_url if found.
    """
    debug_log(f"[NODE: test_ai_category] Entering")
    debug_log(f"[NODE: test_ai_category] Input URL: {url}")

    # Normalize URL
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    url = url.rstrip("/")

    result: AIFeedResult = {
        "url": url,
        "status": "unavailable",
        "ai_feed_url": None,
        "method": "preset",
        "notes": None,
        "article_titles": [],
    }

    tried_paths = []
    status_codes = []  # Track HTTP status codes for paywall detection

    for path in AI_CATEGORY_PATHS:
        feed_url = urljoin(url + "/", path.lstrip("/"))
        tried_paths.append(path)

        debug_log(f"[NODE: test_ai_category] Trying: {feed_url}")

        try:
            response = httpx.get(
                feed_url,
                timeout=REQUEST_TIMEOUT,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (compatible; RSSBot/1.0)"}
            )

            status_codes.append(response.status_code)

            if response.status_code == 200:
                content = response.text
                if is_valid_rss(content):
                    titles = extract_article_titles(content)
                    result["status"] = "available"
                    result["ai_feed_url"] = feed_url
                    result["notes"] = f"Found AI category at {path}"
                    result["article_titles"] = titles
                    debug_log(f"[NODE: test_ai_category] SUCCESS: Found AI feed at {feed_url}")
                    debug_log(f"[NODE: test_ai_category] Titles: {titles}")
                    debug_log(f"[NODE: test_ai_category] Output: {result}")
                    return result

            debug_log(f"[NODE: test_ai_category] {path}: HTTP {response.status_code}")

        except httpx.TimeoutException:
            debug_log(f"[NODE: test_ai_category] {path}: Timeout")
        except httpx.RequestError as e:
            debug_log(f"[NODE: test_ai_category] {path}: Error - {e}")

    # Determine final status based on HTTP response codes
    # If ALL responses were 403 (Forbidden), mark as paywalled
    if status_codes and all(code == 403 for code in status_codes):
        result["status"] = "paywalled"
        result["notes"] = f"All {len(status_codes)} AI category paths returned HTTP 403 (Forbidden)"
        debug_log(f"[NODE: test_ai_category] PAYWALLED: All paths returned 403 Forbidden")
    else:
        result["status"] = "unavailable"
        result["notes"] = f"Tried: {', '.join(tried_paths)}"
        debug_log(f"[NODE: test_ai_category] No AI category feed found")

    debug_log(f"[NODE: test_ai_category] Output: {result}")
    return result


def test_ai_category_batch(urls: list[str]) -> list[AIFeedResult]:
    """
    Test multiple URLs for AI category feeds.

    Args:
        urls: List of base URLs to test.

    Returns:
        List of AIFeedResult for each URL.
    """
    debug_log(f"[NODE: test_ai_category_batch] Entering")
    debug_log(f"[NODE: test_ai_category_batch] Input: {len(urls)} URLs")

    results = []
    for url in urls:
        result = test_ai_category(url)
        results.append(result)

    available = sum(1 for r in results if r["status"] == "available")
    debug_log(f"[NODE: test_ai_category_batch] Output: {available}/{len(urls)} have AI category")

    return results


if __name__ == "__main__":
    # Test with sample URLs
    test_urls = [
        "https://techcabal.com",
        "https://inc42.com",
        "https://www.bensbites.com",
    ]

    results = test_ai_category_batch(test_urls)

    print("\n=== Results ===")
    for r in results:
        print(f"{r['url']}: {r['status']} -> {r['ai_feed_url']}")
