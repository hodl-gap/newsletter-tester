"""
Parse Article Content Node

Extracts article content from HTML using CSS selectors discovered in HTML Layer 1.
"""

import re
from datetime import datetime
from typing import TypedDict, Optional

from bs4 import BeautifulSoup

from src.tracking import debug_log, track_time


class ParsedArticle(TypedDict):
    """Parsed article content."""
    url: str
    source_name: str
    source_url: str
    title: Optional[str]
    content: Optional[str]
    date: Optional[str]  # ISO format YYYY-MM-DD
    author: Optional[str]
    parse_errors: list[str]


def parse_article_content(state: dict) -> dict:
    """
    Parse article content from fetched HTML using CSS selectors.

    Args:
        state: Pipeline state with 'fetched_articles'

    Returns:
        Dict with 'parsed_articles' list
    """
    with track_time("parse_article_content"):
        debug_log("[NODE: parse_article_content] Entering")

        fetched_articles = state.get("fetched_articles", [])
        debug_log(f"[NODE: parse_article_content] Parsing {len(fetched_articles)} articles")

        parsed_articles: list[ParsedArticle] = []
        success_count = 0
        skip_count = 0

        for article in fetched_articles:
            if not article.get("html"):
                skip_count += 1
                continue

            parsed = _parse_article(article)
            parsed_articles.append(parsed)

            # Count success (has title and content)
            if parsed["title"] and parsed["content"]:
                success_count += 1

        debug_log(f"[NODE: parse_article_content] Parsed {success_count}/{len(parsed_articles)} articles successfully")
        debug_log(f"[NODE: parse_article_content] Skipped {skip_count} articles (no HTML)")

        return {"parsed_articles": parsed_articles}


def _parse_article(article: dict) -> ParsedArticle:
    """
    Parse a single article.

    Args:
        article: FetchedArticle dict with HTML and selectors

    Returns:
        ParsedArticle with extracted content
    """
    html = article["html"]
    url = article["url"]
    source_name = article["source_name"]
    errors: list[str] = []

    soup = BeautifulSoup(html, "html.parser")

    # Extract title
    title = _extract_title(soup, article.get("title_selector", ""))
    if not title:
        errors.append("title_not_found")

    # Extract content
    content = _extract_content(soup, article.get("content_selector", ""))
    if not content:
        errors.append("content_not_found")

    # Extract date
    date = None
    if article.get("date_selector"):
        date = _extract_date(
            soup,
            article["date_selector"],
            article.get("date_format"),
        )
        if not date:
            errors.append("date_not_found")

    # Extract author
    author = None
    if article.get("author_selector"):
        author = _extract_author(soup, article["author_selector"])

    return ParsedArticle(
        url=url,
        source_name=source_name,
        source_url=article["source_url"],
        title=title,
        content=content,
        date=date,
        author=author,
        parse_errors=errors,
    )


def _extract_title(soup: BeautifulSoup, selector: str) -> Optional[str]:
    """
    Extract title using CSS selector.

    Handles special cases like meta tags.

    Args:
        soup: BeautifulSoup object
        selector: CSS selector for title

    Returns:
        Cleaned title text or None
    """
    if not selector:
        return None

    # Handle meta tag selectors
    if selector.startswith("meta["):
        elem = soup.select_one(selector)
        if elem:
            return _clean_text(elem.get("content", ""))
        return None

    # Try multiple selectors (comma-separated)
    selectors = [s.strip() for s in selector.split(",")]
    for sel in selectors:
        elem = soup.select_one(sel)
        if elem:
            return _clean_text(elem.get_text())

    return None


def _extract_content(soup: BeautifulSoup, selector: str) -> Optional[str]:
    """
    Extract article content using CSS selector.

    Args:
        soup: BeautifulSoup object
        selector: CSS selector for content

    Returns:
        Cleaned content text or None
    """
    if not selector:
        return None

    elem = soup.select_one(selector)
    if not elem:
        return None

    # Remove unwanted elements
    for tag in elem.select("script, style, noscript, nav, aside, .ad, .advertisement"):
        tag.decompose()

    text = elem.get_text(separator=" ", strip=True)
    return _clean_text(text)


def _extract_date(soup: BeautifulSoup, selector: str, date_format: Optional[str]) -> Optional[str]:
    """
    Extract and parse publication date.

    Args:
        soup: BeautifulSoup object
        selector: CSS selector for date
        date_format: Expected date format (e.g., "MMMM D, YYYY")

    Returns:
        ISO format date string (YYYY-MM-DD) or None
    """
    if not selector:
        return None

    # Handle meta tag selectors
    if selector.startswith("meta["):
        elem = soup.select_one(selector)
        if elem:
            date_str = elem.get("content", "")
            return _parse_date_string(date_str, date_format)
        return None

    elem = soup.select_one(selector)
    if not elem:
        return None

    date_str = elem.get_text(strip=True)
    return _parse_date_string(date_str, date_format)


def _parse_date_string(date_str: str, date_format: Optional[str]) -> Optional[str]:
    """
    Parse a date string to ISO format.

    Args:
        date_str: Raw date string
        date_format: Hint about format (e.g., "MMMM D, YYYY")

    Returns:
        ISO format date (YYYY-MM-DD) or None
    """
    if not date_str:
        return None

    date_str = date_str.strip()

    # Try ISO format first (most common for meta tags)
    try:
        # Handle ISO with timezone
        if "T" in date_str:
            # Remove timezone for parsing
            clean = date_str.split("+")[0].split("Z")[0]
            dt = datetime.fromisoformat(clean[:19])
            return dt.strftime("%Y-%m-%d")
    except ValueError:
        pass

    # Try common formats based on date_format hint
    formats_to_try = []

    if date_format:
        # Convert hint to Python strptime format
        if "MMMM D, YYYY" in date_format:
            formats_to_try.append("%B %d, %Y")
            formats_to_try.append("%B %-d, %Y")  # Without leading zero
        if "YYYY.MM.DD" in date_format:
            formats_to_try.append("%Y.%m.%d %H:%M:%S")
            formats_to_try.append("%Y.%m.%d")
        if "YYYY-MM-DD" in date_format:
            formats_to_try.append("%Y-%m-%d %H:%M:%S")
            formats_to_try.append("%Y-%m-%d")

    # Add common fallback formats
    formats_to_try.extend([
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%B %d, %Y",
        "%b %d, %Y",
        "%d %B %Y",
        "%d %b %Y",
        "%Y.%m.%d",
    ])

    for fmt in formats_to_try:
        try:
            # Handle "January 5, 2026" style (may need to extract just the date part)
            dt = datetime.strptime(date_str[:len(date_str)], fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    # Try regex extraction for embedded dates
    date_patterns = [
        r"(\d{4}-\d{2}-\d{2})",  # YYYY-MM-DD
        r"(\d{4}/\d{2}/\d{2})",  # YYYY/MM/DD
        r"(\d{4}\.\d{2}\.\d{2})",  # YYYY.MM.DD
    ]

    for pattern in date_patterns:
        match = re.search(pattern, date_str)
        if match:
            extracted = match.group(1)
            # Normalize separators
            normalized = extracted.replace("/", "-").replace(".", "-")
            try:
                dt = datetime.strptime(normalized, "%Y-%m-%d")
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue

    debug_log(f"[PARSE] Could not parse date: '{date_str}' with format hint '{date_format}'", "warning")
    return None


def _extract_author(soup: BeautifulSoup, selector: str) -> Optional[str]:
    """
    Extract author using CSS selector.

    Args:
        soup: BeautifulSoup object
        selector: CSS selector for author

    Returns:
        Cleaned author name or None
    """
    if not selector:
        return None

    # Handle meta tag selectors
    if selector.startswith("meta["):
        elem = soup.select_one(selector)
        if elem:
            return _clean_text(elem.get("content", ""))
        return None

    elem = soup.select_one(selector)
    if elem:
        return _clean_text(elem.get_text())

    return None


def _clean_text(text: str) -> str:
    """
    Clean extracted text.

    Args:
        text: Raw text

    Returns:
        Cleaned text
    """
    if not text:
        return ""

    # Normalize whitespace
    text = re.sub(r"\s+", " ", text)

    # Remove common artifacts
    text = text.strip()

    return text
