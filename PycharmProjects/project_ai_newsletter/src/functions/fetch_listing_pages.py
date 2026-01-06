"""
Fetch Listing Pages Node

Fetches the listing/homepage for each scrapable source to extract article URLs.
"""

import time
from typing import TypedDict, Optional

import httpx

from src.tracking import debug_log, track_time


# Request configuration
REQUEST_TIMEOUT = 20
DELAY_BETWEEN_REQUESTS = 1  # seconds

# Browser-like headers
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


class ListingPageResult(TypedDict):
    """Result of fetching a listing page."""
    url: str
    source_name: str
    html: Optional[str]
    status_code: Optional[int]
    error: Optional[str]
    # Carry forward config for next nodes
    article_url_pattern: str
    title_selector: str
    content_selector: str
    date_selector: Optional[str]
    date_format: Optional[str]
    author_selector: Optional[str]


def fetch_listing_pages(state: dict) -> dict:
    """
    Fetch listing pages for all scrapable sources.

    Args:
        state: Pipeline state with 'scrapable_sources'

    Returns:
        Dict with 'listing_pages' list
    """
    with track_time("fetch_listing_pages"):
        debug_log("[NODE: fetch_listing_pages] Entering")

        scrapable_sources = state.get("scrapable_sources", [])
        debug_log(f"[NODE: fetch_listing_pages] Fetching {len(scrapable_sources)} listing pages")

        listing_pages: list[ListingPageResult] = []

        for i, source in enumerate(scrapable_sources):
            url = source["url"]
            source_name = source["source_name"]

            debug_log(f"[NODE: fetch_listing_pages] [{i+1}/{len(scrapable_sources)}] Fetching: {source_name} ({url})")

            result = _fetch_page(url, source_name, source)
            listing_pages.append(result)

            if result["error"]:
                debug_log(f"[NODE: fetch_listing_pages] ERROR: {result['error']}", "error")
            else:
                html_len = len(result["html"]) if result["html"] else 0
                debug_log(f"[NODE: fetch_listing_pages] Success: {html_len} chars")

            # Rate limiting
            if i < len(scrapable_sources) - 1:
                time.sleep(DELAY_BETWEEN_REQUESTS)

        success_count = sum(1 for r in listing_pages if r["html"])
        debug_log(f"[NODE: fetch_listing_pages] Fetched {success_count}/{len(listing_pages)} listing pages")

        return {"listing_pages": listing_pages}


def _fetch_page(url: str, source_name: str, source: dict) -> ListingPageResult:
    """
    Fetch a single listing page.

    Args:
        url: URL to fetch
        source_name: Name of the source
        source: Full source config dict

    Returns:
        ListingPageResult with HTML or error
    """
    try:
        response = httpx.get(
            url,
            headers=BROWSER_HEADERS,
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
        )

        # Check for Cloudflare/bot protection
        if response.status_code == 403:
            return ListingPageResult(
                url=url,
                source_name=source_name,
                html=None,
                status_code=403,
                error="Blocked (403 Forbidden)",
                article_url_pattern=source["article_url_pattern"],
                title_selector=source["title_selector"],
                content_selector=source["content_selector"],
                date_selector=source.get("date_selector"),
                date_format=source.get("date_format"),
                author_selector=source.get("author_selector"),
            )

        if response.status_code != 200:
            return ListingPageResult(
                url=url,
                source_name=source_name,
                html=None,
                status_code=response.status_code,
                error=f"HTTP {response.status_code}",
                article_url_pattern=source["article_url_pattern"],
                title_selector=source["title_selector"],
                content_selector=source["content_selector"],
                date_selector=source.get("date_selector"),
                date_format=source.get("date_format"),
                author_selector=source.get("author_selector"),
            )

        html = response.text

        # Check for Cloudflare challenge
        if "just a moment" in html.lower() and ("cloudflare" in html.lower() or "cf-" in html.lower()):
            return ListingPageResult(
                url=url,
                source_name=source_name,
                html=None,
                status_code=response.status_code,
                error="Cloudflare challenge detected",
                article_url_pattern=source["article_url_pattern"],
                title_selector=source["title_selector"],
                content_selector=source["content_selector"],
                date_selector=source.get("date_selector"),
                date_format=source.get("date_format"),
                author_selector=source.get("author_selector"),
            )

        return ListingPageResult(
            url=url,
            source_name=source_name,
            html=html,
            status_code=response.status_code,
            error=None,
            article_url_pattern=source["article_url_pattern"],
            title_selector=source["title_selector"],
            content_selector=source["content_selector"],
            date_selector=source.get("date_selector"),
            date_format=source.get("date_format"),
            author_selector=source.get("author_selector"),
        )

    except httpx.TimeoutException:
        return ListingPageResult(
            url=url,
            source_name=source_name,
            html=None,
            status_code=None,
            error="Request timeout",
            article_url_pattern=source["article_url_pattern"],
            title_selector=source["title_selector"],
            content_selector=source["content_selector"],
            date_selector=source.get("date_selector"),
            date_format=source.get("date_format"),
            author_selector=source.get("author_selector"),
        )
    except Exception as e:
        return ListingPageResult(
            url=url,
            source_name=source_name,
            html=None,
            status_code=None,
            error=f"Error: {str(e)[:100]}",
            article_url_pattern=source["article_url_pattern"],
            title_selector=source["title_selector"],
            content_selector=source["content_selector"],
            date_selector=source.get("date_selector"),
            date_format=source.get("date_format"),
            author_selector=source.get("author_selector"),
        )
