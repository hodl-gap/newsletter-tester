"""
Test RSS Preset URLs

This node tests preset RSS feed URLs for a given base URL.
Tries common RSS paths like /feed, /rss, /feed.xml, etc.
"""

import re
from typing import TypedDict, Optional
import httpx
from urllib.parse import urljoin

from src.tracking import debug_log, track_time


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

# Browser-like headers for HTTP fetch testing
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


class RSSTestResult(TypedDict):
    url: str
    status: str  # "available", "paywalled", "unavailable"
    feed_url: Optional[str]
    method: str  # "preset"
    notes: Optional[str]
    article_titles: list[str]  # Sample article titles for classification
    has_full_content: bool  # Whether RSS has content:encoded
    http_fetch_works: Optional[bool]  # Whether article URLs are fetchable (None if not tested)


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


def has_full_content(content: str) -> bool:
    """
    Check if RSS feed contains full article content (content:encoded).

    Args:
        content: Raw RSS/Atom XML content.

    Returns:
        True if feed has content:encoded or substantial content fields.
    """
    content_lower = content.lower()
    # Check for content:encoded (common in WordPress)
    if '<content:encoded' in content_lower:
        return True
    # Check for Atom content (not just summaries)
    if '<content type=' in content_lower:
        return True
    return False


def extract_first_article_url(content: str) -> Optional[str]:
    """
    Extract the first article URL from RSS/Atom feed.

    Args:
        content: Raw RSS/Atom XML content.

    Returns:
        First article URL or None.
    """
    # Try RSS <link> inside <item>
    match = re.search(r'<item[^>]*>.*?<link[^>]*>([^<]+)</link>', content, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()

    # Try Atom <link href="...">
    match = re.search(r'<entry[^>]*>.*?<link[^>]*href=["\']([^"\']+)["\']', content, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()

    return None


def test_http_fetch(url: str) -> bool:
    """
    Test if an article URL is fetchable without Cloudflare blocking.

    Args:
        url: Article URL to test.

    Returns:
        True if URL returns actual content, False if blocked or error.
    """
    try:
        response = httpx.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers=BROWSER_HEADERS,
            follow_redirects=True,
        )
        if response.status_code != 200:
            return False

        text = response.text.lower()
        # Check for Cloudflare challenge page
        if 'just a moment' in text and ('cloudflare' in text or 'cf-' in text):
            return False

        # Check we got actual content (not empty or error page)
        return len(response.text) > 1000

    except Exception:
        return False


def test_rss_preset(url: str) -> RSSTestResult:
    """
    Test preset RSS paths for a given base URL.

    Args:
        url: Base URL to test (e.g., "https://example.com")

    Returns:
        RSSTestResult with status and feed_url if found.
    """
    with track_time("test_rss_preset"):
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
            "has_full_content": False,
            "http_fetch_works": None,
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

                        # Check for full content availability
                        result["has_full_content"] = has_full_content(content)
                        debug_log(f"[NODE: test_rss_preset] has_full_content: {result['has_full_content']}")

                        # If no full content, test HTTP fetch on first article
                        if not result["has_full_content"]:
                            first_url = extract_first_article_url(content)
                            if first_url:
                                debug_log(f"[NODE: test_rss_preset] Testing HTTP fetch: {first_url}")
                                result["http_fetch_works"] = test_http_fetch(first_url)
                                debug_log(f"[NODE: test_rss_preset] http_fetch_works: {result['http_fetch_works']}")

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
