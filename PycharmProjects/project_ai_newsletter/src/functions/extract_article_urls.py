"""
Extract Article URLs Node

Extracts article URLs from listing pages using regex patterns discovered in HTML Layer 1.
"""

import re
from typing import TypedDict, Optional
from urllib.parse import urljoin, urlparse

from src.tracking import debug_log, track_time


class ArticleUrlInfo(TypedDict):
    """Information about an article URL to fetch."""
    url: str
    source_name: str
    source_url: str  # Base URL of the source
    # Carry forward config for extraction
    title_selector: str
    content_selector: str
    date_selector: Optional[str]
    date_format: Optional[str]
    author_selector: Optional[str]


def extract_article_urls(state: dict) -> dict:
    """
    Extract article URLs from listing pages using regex patterns.

    Args:
        state: Pipeline state with 'listing_pages'

    Returns:
        Dict with 'article_urls' list
    """
    with track_time("extract_article_urls"):
        debug_log("[NODE: extract_article_urls] Entering")

        listing_pages = state.get("listing_pages", [])
        debug_log(f"[NODE: extract_article_urls] Processing {len(listing_pages)} listing pages")

        all_article_urls: list[ArticleUrlInfo] = []
        seen_urls: set[str] = set()

        for page in listing_pages:
            if not page.get("html"):
                debug_log(f"[NODE: extract_article_urls] Skipping {page['source_name']} - no HTML")
                continue

            source_name = page["source_name"]
            source_url = page["url"]
            pattern = page["article_url_pattern"]

            debug_log(f"[NODE: extract_article_urls] Extracting from {source_name} with pattern: {pattern}")

            urls = _extract_urls_from_html(
                html=page["html"],
                source_url=source_url,
                pattern=pattern,
            )

            # Deduplicate and create ArticleUrlInfo
            for url in urls:
                if url not in seen_urls:
                    seen_urls.add(url)
                    all_article_urls.append(ArticleUrlInfo(
                        url=url,
                        source_name=source_name,
                        source_url=source_url,
                        title_selector=page["title_selector"],
                        content_selector=page["content_selector"],
                        date_selector=page.get("date_selector"),
                        date_format=page.get("date_format"),
                        author_selector=page.get("author_selector"),
                    ))

            debug_log(f"[NODE: extract_article_urls] Found {len(urls)} URLs from {source_name}")

        debug_log(f"[NODE: extract_article_urls] Total unique article URLs: {len(all_article_urls)}")

        return {"article_urls": all_article_urls}


def _extract_urls_from_html(html: str, source_url: str, pattern: str) -> list[str]:
    """
    Extract article URLs from HTML using a regex pattern.

    Args:
        html: HTML content of listing page
        source_url: Base URL of the source for resolving relative URLs
        pattern: Regex pattern for article URLs (e.g., "/articles/[a-z0-9\\-]+")

    Returns:
        List of absolute article URLs
    """
    urls: list[str] = []

    # Parse the base URL for resolving relative paths
    parsed_base = urlparse(source_url)
    base_domain = f"{parsed_base.scheme}://{parsed_base.netloc}"

    # Find all href attributes
    href_pattern = r'href=["\']([^"\']+)["\']'
    all_hrefs = re.findall(href_pattern, html, re.IGNORECASE)

    # Compile the article pattern
    try:
        article_regex = re.compile(pattern)
    except re.error as e:
        debug_log(f"[NODE: extract_article_urls] Invalid regex pattern '{pattern}': {e}", "error")
        return []

    for href in all_hrefs:
        # Skip empty or javascript links
        if not href or href.startswith("javascript:") or href.startswith("#"):
            continue

        # Check if href matches the article pattern
        if article_regex.search(href):
            # Resolve relative URLs
            if href.startswith("//"):
                full_url = f"{parsed_base.scheme}:{href}"
            elif href.startswith("/"):
                full_url = urljoin(base_domain, href)
            elif not href.startswith("http"):
                full_url = urljoin(source_url, href)
            else:
                full_url = href

            # Normalize URL (remove trailing slash for consistency)
            full_url = full_url.rstrip("/")

            if full_url not in urls:
                urls.append(full_url)

    return urls
