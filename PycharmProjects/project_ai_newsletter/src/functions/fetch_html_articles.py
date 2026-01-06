"""
Fetch HTML Articles Node

Fetches individual article pages for content extraction.
"""

import time
from typing import TypedDict, Optional

import httpx

from src.tracking import debug_log, track_time


# Request configuration
REQUEST_TIMEOUT = 15
DELAY_BETWEEN_REQUESTS = 0.5  # seconds (faster than listing pages)
MAX_ARTICLES_PER_SOURCE = 20  # Limit to avoid overwhelming sources


# Browser-like headers
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}


class FetchedArticle(TypedDict):
    """Result of fetching an article page."""
    url: str
    source_name: str
    source_url: str
    html: Optional[str]
    status_code: Optional[int]
    error: Optional[str]
    # Carry forward config for parsing
    title_selector: str
    content_selector: str
    date_selector: Optional[str]
    date_format: Optional[str]
    author_selector: Optional[str]


def fetch_html_articles(state: dict) -> dict:
    """
    Fetch individual article pages.

    Args:
        state: Pipeline state with 'article_urls'

    Returns:
        Dict with 'fetched_articles' list
    """
    with track_time("fetch_html_articles"):
        debug_log("[NODE: fetch_html_articles] Entering")

        article_urls = state.get("article_urls", [])
        debug_log(f"[NODE: fetch_html_articles] {len(article_urls)} article URLs to fetch")

        # Group by source to respect per-source limits
        by_source: dict[str, list] = {}
        for article in article_urls:
            source = article["source_name"]
            if source not in by_source:
                by_source[source] = []
            by_source[source].append(article)

        # Apply per-source limit
        limited_urls: list = []
        for source, articles in by_source.items():
            if len(articles) > MAX_ARTICLES_PER_SOURCE:
                debug_log(f"[NODE: fetch_html_articles] Limiting {source} from {len(articles)} to {MAX_ARTICLES_PER_SOURCE} articles")
                limited_urls.extend(articles[:MAX_ARTICLES_PER_SOURCE])
            else:
                limited_urls.extend(articles)

        debug_log(f"[NODE: fetch_html_articles] Fetching {len(limited_urls)} articles (after limits)")

        fetched_articles: list[FetchedArticle] = []

        for i, article_info in enumerate(limited_urls):
            url = article_info["url"]
            source_name = article_info["source_name"]

            if (i + 1) % 10 == 0 or i == 0:
                debug_log(f"[NODE: fetch_html_articles] [{i+1}/{len(limited_urls)}] Fetching: {url[:60]}...")

            result = _fetch_article(url, article_info)
            fetched_articles.append(result)

            # Rate limiting
            if i < len(limited_urls) - 1:
                time.sleep(DELAY_BETWEEN_REQUESTS)

        success_count = sum(1 for r in fetched_articles if r["html"])
        error_count = len(fetched_articles) - success_count

        debug_log(f"[NODE: fetch_html_articles] Fetched {success_count}/{len(fetched_articles)} articles ({error_count} errors)")

        return {"fetched_articles": fetched_articles}


def _fetch_article(url: str, article_info: dict) -> FetchedArticle:
    """
    Fetch a single article page.

    Args:
        url: Article URL to fetch
        article_info: Article info dict with config

    Returns:
        FetchedArticle with HTML or error
    """
    try:
        response = httpx.get(
            url,
            headers=BROWSER_HEADERS,
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
        )

        if response.status_code != 200:
            return FetchedArticle(
                url=url,
                source_name=article_info["source_name"],
                source_url=article_info["source_url"],
                html=None,
                status_code=response.status_code,
                error=f"HTTP {response.status_code}",
                title_selector=article_info["title_selector"],
                content_selector=article_info["content_selector"],
                date_selector=article_info.get("date_selector"),
                date_format=article_info.get("date_format"),
                author_selector=article_info.get("author_selector"),
            )

        html = response.text

        # Check for Cloudflare challenge
        if "just a moment" in html.lower() and ("cloudflare" in html.lower() or "cf-" in html.lower()):
            return FetchedArticle(
                url=url,
                source_name=article_info["source_name"],
                source_url=article_info["source_url"],
                html=None,
                status_code=response.status_code,
                error="Cloudflare challenge",
                title_selector=article_info["title_selector"],
                content_selector=article_info["content_selector"],
                date_selector=article_info.get("date_selector"),
                date_format=article_info.get("date_format"),
                author_selector=article_info.get("author_selector"),
            )

        return FetchedArticle(
            url=url,
            source_name=article_info["source_name"],
            source_url=article_info["source_url"],
            html=html,
            status_code=response.status_code,
            error=None,
            title_selector=article_info["title_selector"],
            content_selector=article_info["content_selector"],
            date_selector=article_info.get("date_selector"),
            date_format=article_info.get("date_format"),
            author_selector=article_info.get("author_selector"),
        )

    except httpx.TimeoutException:
        return FetchedArticle(
            url=url,
            source_name=article_info["source_name"],
            source_url=article_info["source_url"],
            html=None,
            status_code=None,
            error="Request timeout",
            title_selector=article_info["title_selector"],
            content_selector=article_info["content_selector"],
            date_selector=article_info.get("date_selector"),
            date_format=article_info.get("date_format"),
            author_selector=article_info.get("author_selector"),
        )
    except Exception as e:
        return FetchedArticle(
            url=url,
            source_name=article_info["source_name"],
            source_url=article_info["source_url"],
            html=None,
            status_code=None,
            error=f"Error: {str(e)[:80]}",
            title_selector=article_info["title_selector"],
            content_selector=article_info["content_selector"],
            date_selector=article_info.get("date_selector"),
            date_format=article_info.get("date_format"),
            author_selector=article_info.get("author_selector"),
        )
