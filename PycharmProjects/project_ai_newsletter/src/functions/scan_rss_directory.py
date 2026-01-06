"""
Scan RSS Directory Pages

Scans common RSS directory pages (e.g., /about/rss, /feeds) to discover
topic-specific feeds that use non-standard URL patterns.
"""

import re
from typing import TypedDict, Optional
from urllib.parse import urljoin, urlparse
import httpx

from src.tracking import debug_log, track_time
from src.functions.test_rss_preset import is_valid_rss, extract_latest_date, BROWSER_HEADERS


# Common RSS directory page paths
RSS_DIRECTORY_PATHS = [
    "/about/rss",
    "/about/feeds",
    "/feeds",
    "/help/rss",
    "/help/feeds",
    "/rss-feeds",
    "/support/rss",
]

# Topic keywords to match against link text and URLs
TOPIC_KEYWORDS = {
    "tech": ["tech", "technology", "digital", "cyber", "computer", "gadget"],
    "ai": ["ai", "artificial-intelligence", "machine-learning", "ml", "artificial intelligence"],
    "science": ["science", "research", "innovation"],
}

# Timeout for HTTP requests (seconds)
REQUEST_TIMEOUT = 10


class RSSDirectoryResult(TypedDict):
    """Result from scanning RSS directory pages."""
    url: str                          # Original source URL
    directory_page_url: Optional[str] # URL where feeds were discovered
    tech_feed_url: Optional[str]      # Technology-specific feed
    ai_feed_url: Optional[str]        # AI-specific feed
    science_feed_url: Optional[str]   # Science-specific feed
    all_feeds: list[dict]             # All discovered feeds: [{url, topic, link_text}]


def extract_feed_links(html: str, base_url: str) -> list[dict]:
    """
    Extract RSS/feed links from HTML page.

    Args:
        html: HTML content of the page.
        base_url: Base URL for resolving relative links.

    Returns:
        List of dicts with 'url', 'link_text' keys.
    """
    feeds = []

    # Pattern to find <a> tags with href containing feed-like URLs
    # Matches: .xml, /feed, /rss, atom
    link_pattern = re.compile(
        r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>([^<]*)</a>',
        re.IGNORECASE
    )

    for match in link_pattern.finditer(html):
        href = match.group(1).strip()
        link_text = match.group(2).strip()

        # Check if URL looks like a feed
        href_lower = href.lower()
        is_feed_url = any([
            '.xml' in href_lower,
            '/feed' in href_lower,
            '/rss' in href_lower,
            '/atom' in href_lower,
            'feed=' in href_lower,
        ])

        if is_feed_url:
            # Resolve relative URLs
            full_url = urljoin(base_url, href)
            feeds.append({
                'url': full_url,
                'link_text': link_text,
            })

    return feeds


def categorize_feed(url: str, link_text: str) -> Optional[str]:
    """
    Categorize a feed URL by topic based on URL and link text.

    Args:
        url: Feed URL.
        link_text: Text of the link.

    Returns:
        Topic category ('tech', 'ai', 'science') or None.
    """
    combined = (url + ' ' + link_text).lower()

    # Check each topic using word boundary matching
    for topic, keywords in TOPIC_KEYWORDS.items():
        for keyword in keywords:
            # Use word boundary pattern to avoid false positives
            # e.g., "ai" should not match "latest" or "mail"
            pattern = r'(?:^|[/\-_.\s])' + re.escape(keyword) + r'(?:$|[/\-_.\s])'
            if re.search(pattern, combined):
                return topic

    return None


def validate_feed_url(url: str) -> tuple[bool, Optional[str]]:
    """
    Validate that a URL returns valid RSS/Atom content.

    Args:
        url: Feed URL to validate.

    Returns:
        Tuple of (is_valid, latest_date).
    """
    try:
        response = httpx.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0 (compatible; RSSBot/1.0)"},
            follow_redirects=True,
        )

        if response.status_code == 200 and is_valid_rss(response.text):
            latest_date = extract_latest_date(response.text)
            return True, latest_date

    except Exception:
        pass

    return False, None


def scan_rss_directory(url: str) -> RSSDirectoryResult:
    """
    Scan RSS directory pages for topic-specific feeds.

    Args:
        url: Base URL to scan (e.g., "https://www.foxnews.com")

    Returns:
        RSSDirectoryResult with discovered feeds.
    """
    with track_time("scan_rss_directory"):
        debug_log(f"[NODE: scan_rss_directory] Entering")
        debug_log(f"[NODE: scan_rss_directory] Input URL: {url}")

        # Normalize URL
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        url = url.rstrip("/")

        result: RSSDirectoryResult = {
            "url": url,
            "directory_page_url": None,
            "tech_feed_url": None,
            "ai_feed_url": None,
            "science_feed_url": None,
            "all_feeds": [],
        }

        all_discovered_feeds = []

        for path in RSS_DIRECTORY_PATHS:
            directory_url = urljoin(url + "/", path.lstrip("/"))
            debug_log(f"[NODE: scan_rss_directory] Trying directory: {directory_url}")

            try:
                response = httpx.get(
                    directory_url,
                    timeout=REQUEST_TIMEOUT,
                    headers=BROWSER_HEADERS,
                    follow_redirects=True,
                )

                if response.status_code != 200:
                    debug_log(f"[NODE: scan_rss_directory] {path}: HTTP {response.status_code}")
                    continue

                # Check if this looks like an HTML page (not RSS)
                content_type = response.headers.get('content-type', '').lower()
                if 'xml' in content_type or is_valid_rss(response.text[:1000]):
                    debug_log(f"[NODE: scan_rss_directory] {path}: Is RSS feed, not directory page")
                    continue

                if 'html' not in content_type and 'text' not in content_type:
                    debug_log(f"[NODE: scan_rss_directory] {path}: Not HTML ({content_type})")
                    continue

                # Extract feed links from HTML
                feeds = extract_feed_links(response.text, directory_url)

                if feeds:
                    debug_log(f"[NODE: scan_rss_directory] Found {len(feeds)} feed links at {path}")
                    result["directory_page_url"] = directory_url

                    for feed in feeds:
                        topic = categorize_feed(feed['url'], feed['link_text'])
                        feed['topic'] = topic
                        all_discovered_feeds.append(feed)
                        debug_log(f"[NODE: scan_rss_directory]   - {feed['link_text']}: {feed['url']} (topic: {topic})")

                    # Found a directory page with feeds, no need to continue
                    break

            except httpx.TimeoutException:
                debug_log(f"[NODE: scan_rss_directory] {path}: Timeout")
            except httpx.RequestError as e:
                debug_log(f"[NODE: scan_rss_directory] {path}: Error - {e}")

        # Validate and categorize discovered feeds
        for feed in all_discovered_feeds:
            topic = feed.get('topic')
            feed_url = feed['url']

            # Skip if we already have a feed for this topic
            if topic == 'tech' and result['tech_feed_url']:
                continue
            if topic == 'ai' and result['ai_feed_url']:
                continue
            if topic == 'science' and result['science_feed_url']:
                continue

            # Validate the feed URL
            is_valid, latest_date = validate_feed_url(feed_url)

            if is_valid:
                feed['validated'] = True
                feed['latest_date'] = latest_date

                if topic == 'tech' and not result['tech_feed_url']:
                    result['tech_feed_url'] = feed_url
                    debug_log(f"[NODE: scan_rss_directory] Validated tech feed: {feed_url}")
                elif topic == 'ai' and not result['ai_feed_url']:
                    result['ai_feed_url'] = feed_url
                    debug_log(f"[NODE: scan_rss_directory] Validated AI feed: {feed_url}")
                elif topic == 'science' and not result['science_feed_url']:
                    result['science_feed_url'] = feed_url
                    debug_log(f"[NODE: scan_rss_directory] Validated science feed: {feed_url}")
            else:
                feed['validated'] = False
                debug_log(f"[NODE: scan_rss_directory] Invalid feed (failed validation): {feed_url}")

        result['all_feeds'] = all_discovered_feeds

        debug_log(f"[NODE: scan_rss_directory] Output: tech={result['tech_feed_url']}, ai={result['ai_feed_url']}, science={result['science_feed_url']}")
        return result


if __name__ == "__main__":
    # Test with Fox News
    test_result = scan_rss_directory("https://www.foxnews.com")

    print("\n=== RSS Directory Scan Results ===")
    print(f"URL: {test_result['url']}")
    print(f"Directory page: {test_result['directory_page_url']}")
    print(f"Tech feed: {test_result['tech_feed_url']}")
    print(f"AI feed: {test_result['ai_feed_url']}")
    print(f"Science feed: {test_result['science_feed_url']}")
    print(f"\nAll feeds found: {len(test_result['all_feeds'])}")
    for feed in test_result['all_feeds']:
        print(f"  - {feed['link_text']}: {feed['url']} (topic: {feed.get('topic')}, valid: {feed.get('validated')})")
