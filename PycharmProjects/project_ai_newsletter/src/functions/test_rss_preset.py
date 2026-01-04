"""
Test RSS Preset URLs

This node tests preset RSS feed URLs for a given base URL.
Tries common RSS paths like /feed, /rss, /feed.xml, etc.
"""

import re
from typing import TypedDict, Optional
import httpx
from urllib.parse import urljoin

from src.tracking import debug_log


# Preset RSS paths to try
PRESET_RSS_PATHS = [
    "/feed",
    "/feed/",
    "/rss",
    "/rss/",
    "/feed.xml",
    "/rss.xml",
    "/atom.xml",
    "/index.xml",
    "/feeds/posts/default",  # Blogger
]

# Timeout for HTTP requests (seconds)
REQUEST_TIMEOUT = 10


class RSSTestResult(TypedDict):
    url: str
    status: str  # "available", "paywalled", "unavailable"
    feed_url: Optional[str]
    method: str  # "preset"
    notes: Optional[str]
    article_titles: list[str]  # Sample article titles for classification


def is_valid_rss(content: str) -> bool:
    """
    Check if content looks like a valid RSS/Atom feed.
    """
    content_lower = content.lower()[:1000]  # Check first 1000 chars
    return any([
        "<rss" in content_lower,
        "<feed" in content_lower,
        "<atom" in content_lower,
        "<?xml" in content_lower and "channel" in content_lower,
    ])


def extract_article_titles(content: str, max_titles: int = 10) -> list[str]:
    """
    Extract article titles from RSS/Atom feed content.

    Args:
        content: Raw RSS/Atom XML content.
        max_titles: Maximum number of titles to extract.

    Returns:
        List of article title strings.
    """
    titles = []

    # Try RSS <title> tags (skip first one which is feed title)
    rss_titles = re.findall(r'<title[^>]*>(?:<!\[CDATA\[)?([^<\]]+)(?:\]\]>)?</title>', content, re.IGNORECASE)
    if rss_titles:
        # Skip first title (feed title) and get article titles
        titles = [t.strip() for t in rss_titles[1:max_titles + 1] if t.strip()]

    # If no titles found, try Atom format
    if not titles:
        atom_titles = re.findall(r'<entry[^>]*>.*?<title[^>]*>([^<]+)</title>', content, re.IGNORECASE | re.DOTALL)
        titles = [t.strip() for t in atom_titles[:max_titles] if t.strip()]

    return titles


def test_rss_preset(url: str) -> RSSTestResult:
    """
    Test preset RSS paths for a given base URL.

    Args:
        url: Base URL to test (e.g., "https://example.com")

    Returns:
        RSSTestResult with status and feed_url if found.
    """
    debug_log(f"[NODE: test_rss_preset] Entering")
    debug_log(f"[NODE: test_rss_preset] Input URL: {url}")

    # Normalize URL
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    url = url.rstrip("/")

    result: RSSTestResult = {
        "url": url,
        "status": "unavailable",
        "feed_url": None,
        "method": "preset",
        "notes": None,
        "article_titles": [],
    }

    tried_paths = []
    status_codes = []  # Track HTTP status codes for paywall detection

    for path in PRESET_RSS_PATHS:
        feed_url = urljoin(url + "/", path.lstrip("/"))
        tried_paths.append(path)

        debug_log(f"[NODE: test_rss_preset] Trying: {feed_url}")

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
                    result["feed_url"] = feed_url
                    result["notes"] = f"Found at {path}"
                    result["article_titles"] = titles
                    debug_log(f"[NODE: test_rss_preset] SUCCESS: Found RSS at {feed_url}")
                    debug_log(f"[NODE: test_rss_preset] Titles: {titles}")
                    debug_log(f"[NODE: test_rss_preset] Output: {result}")
                    return result

            debug_log(f"[NODE: test_rss_preset] {path}: HTTP {response.status_code}")

        except httpx.TimeoutException:
            debug_log(f"[NODE: test_rss_preset] {path}: Timeout")
        except httpx.RequestError as e:
            debug_log(f"[NODE: test_rss_preset] {path}: Error - {e}")

    # Determine final status based on HTTP response codes
    # If ALL responses were 403 (Forbidden), mark as paywalled
    if status_codes and all(code == 403 for code in status_codes):
        result["status"] = "paywalled"
        result["notes"] = f"All {len(status_codes)} paths returned HTTP 403 (Forbidden) - likely requires subscription"
        debug_log(f"[NODE: test_rss_preset] PAYWALLED: All paths returned 403 Forbidden")
    else:
        result["status"] = "unavailable"
        result["notes"] = f"Tried: {', '.join(tried_paths)}"
        debug_log(f"[NODE: test_rss_preset] UNAVAILABLE: No RSS found at preset paths")

    debug_log(f"[NODE: test_rss_preset] Output: {result}")
    return result


def test_rss_preset_batch(urls: list[str]) -> list[RSSTestResult]:
    """
    Test multiple URLs for RSS feeds.

    Args:
        urls: List of base URLs to test.

    Returns:
        List of RSSTestResult for each URL.
    """
    debug_log(f"[NODE: test_rss_preset_batch] Entering")
    debug_log(f"[NODE: test_rss_preset_batch] Input: {len(urls)} URLs")

    results = []
    for url in urls:
        result = test_rss_preset(url)
        results.append(result)

    available = sum(1 for r in results if r["status"] == "available")
    debug_log(f"[NODE: test_rss_preset_batch] Output: {available}/{len(urls)} available")

    return results


if __name__ == "__main__":
    # Test with sample URLs
    test_urls = [
        "https://inc42.com",
        "https://www.bensbites.com",
        "https://www.theinformation.com",
    ]

    results = test_rss_preset_batch(test_urls)

    print("\n=== Results ===")
    for r in results:
        print(f"{r['url']}: {r['status']} -> {r['feed_url']}")
