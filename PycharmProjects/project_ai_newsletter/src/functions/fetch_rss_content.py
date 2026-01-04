"""
Fetch RSS Content Node

Fetches and parses RSS XML from all available feeds,
extracting article metadata and content.
"""

import re
import time
from datetime import datetime
from typing import TypedDict, Optional
from email.utils import parsedate_to_datetime

import httpx
import feedparser

from src.tracking import debug_log, track_time


# Retry configuration
MAX_RETRIES = 2       # Number of retry attempts after initial failure
RETRY_DELAY = 5       # Seconds to wait between retries
REQUEST_TIMEOUT = 20  # Seconds to wait for response (increased from 15)


class RSSArticle(TypedDict):
    """Raw article from RSS feed."""
    feed_url: str
    source_name: str
    title: str
    link: str
    pub_date: str               # ISO format date string
    description: str            # RSS description field
    full_content: Optional[str] # content:encoded if available
    categories: list[str]       # RSS category tags
    author: Optional[str]


def fetch_rss_content(state: dict) -> dict:
    """
    Fetch and parse RSS content from all available feeds.

    Args:
        state: Pipeline state with 'available_feeds'

    Returns:
        Dict with 'raw_articles' list
    """
    with track_time("fetch_rss_content"):
        debug_log("[NODE: fetch_rss_content] Entering")

        available_feeds = state.get("available_feeds", [])
        debug_log(f"[NODE: fetch_rss_content] Processing {len(available_feeds)} feeds")

        all_articles: list[RSSArticle] = []
        seen_urls: set[str] = set()  # For deduplication

        for feed_info in available_feeds:
            feed_url = feed_info.get("feed_url", "")
            source_name = feed_info.get("source_name", "Unknown")

            debug_log(f"[NODE: fetch_rss_content] Fetching: {source_name} ({feed_url})")

            # Retry loop for resilience against timeouts
            for attempt in range(MAX_RETRIES + 1):
                try:
                    articles = _fetch_single_feed(feed_url, source_name)

                    # Deduplicate by URL
                    for article in articles:
                        if article["link"] not in seen_urls:
                            seen_urls.add(article["link"])
                            all_articles.append(article)

                    debug_log(f"[NODE: fetch_rss_content] Got {len(articles)} articles from {source_name}")
                    break  # Success, exit retry loop

                except Exception as e:
                    if attempt < MAX_RETRIES:
                        debug_log(f"[NODE: fetch_rss_content] Attempt {attempt + 1} failed for {source_name}: {e}. Retrying in {RETRY_DELAY}s...", "warning")
                        time.sleep(RETRY_DELAY)
                    else:
                        debug_log(f"[NODE: fetch_rss_content] ERROR fetching {source_name} after {MAX_RETRIES + 1} attempts: {e}", "error")

            # Rate limiting: 1 second between requests
            time.sleep(1)

        debug_log(f"[NODE: fetch_rss_content] Total articles: {len(all_articles)} (deduplicated)")

        return {"raw_articles": all_articles}


def _fetch_single_feed(feed_url: str, source_name: str) -> list[RSSArticle]:
    """
    Fetch and parse a single RSS feed.

    Args:
        feed_url: URL of the RSS feed
        source_name: Name of the source

    Returns:
        List of RSSArticle dicts
    """
    # Fetch with httpx for better control
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; AINewsBot/1.0)",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    }

    response = httpx.get(
        feed_url,
        headers=headers,
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )
    response.raise_for_status()

    # Parse with feedparser
    feed = feedparser.parse(response.text)

    if feed.bozo and not feed.entries:
        raise ValueError(f"Invalid feed: {feed.bozo_exception}")

    articles: list[RSSArticle] = []

    for entry in feed.entries:
        article = _parse_entry(entry, feed_url, source_name)
        if article:
            articles.append(article)

    return articles


def _parse_entry(entry: dict, feed_url: str, source_name: str) -> Optional[RSSArticle]:
    """
    Parse a single feed entry into RSSArticle.

    Args:
        entry: feedparser entry dict
        feed_url: URL of the feed
        source_name: Name of the source

    Returns:
        RSSArticle or None if parsing fails
    """
    # Title is required
    title = entry.get("title", "").strip()
    if not title:
        return None

    # Link is required
    link = entry.get("link", "").strip()
    if not link:
        return None

    # Parse publication date
    pub_date = _parse_date(entry)

    # Get description/summary
    description = ""
    if "summary" in entry:
        description = _clean_html(entry.summary)
    elif "description" in entry:
        description = _clean_html(entry.description)

    # Get full content if available
    full_content = None
    if "content" in entry and entry.content:
        # content is usually a list
        content_item = entry.content[0] if isinstance(entry.content, list) else entry.content
        if isinstance(content_item, dict):
            full_content = content_item.get("value", "")
        else:
            full_content = str(content_item)

    # Get categories/tags
    categories = []
    if "tags" in entry:
        for tag in entry.tags:
            if isinstance(tag, dict):
                term = tag.get("term", "")
                if term:
                    categories.append(term)
            else:
                categories.append(str(tag))

    # Get author
    author = entry.get("author") or entry.get("dc_creator")

    return RSSArticle(
        feed_url=feed_url,
        source_name=source_name,
        title=title,
        link=link,
        pub_date=pub_date,
        description=description,
        full_content=full_content,
        categories=categories,
        author=author,
    )


def _parse_date(entry: dict) -> str:
    """
    Parse entry date to ISO format string.

    Args:
        entry: feedparser entry dict

    Returns:
        ISO format date string (YYYY-MM-DD) or empty string
    """
    # Try different date fields
    date_str = entry.get("published") or entry.get("updated") or entry.get("created")

    if not date_str:
        # Check for parsed time tuple
        if "published_parsed" in entry and entry.published_parsed:
            try:
                dt = datetime(*entry.published_parsed[:6])
                return dt.strftime("%Y-%m-%d")
            except Exception:
                pass
        return ""

    # Try to parse RFC 2822 date
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        pass

    # Try ISO format
    try:
        # Handle various ISO formats
        date_str = date_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(date_str[:19])
        return dt.strftime("%Y-%m-%d")
    except Exception:
        pass

    return ""


def _clean_html(text: str) -> str:
    """
    Remove HTML tags from text.

    Args:
        text: Text possibly containing HTML

    Returns:
        Cleaned plain text
    """
    if not text:
        return ""

    # Remove CDATA wrappers
    text = re.sub(r'<!\[CDATA\[|\]\]>', '', text)

    # Remove HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)

    # Decode common entities
    text = text.replace("&nbsp;", " ")
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&quot;", '"')
    text = text.replace("&#39;", "'")

    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)

    return text.strip()
