"""
Adapt Browser-Use to Articles Node

Converts extracted browser-use articles to RSSArticle format for compatibility
with the existing Layer 2 pipeline (filter, metadata, summaries).
"""

from typing import TypedDict, Optional

from src.tracking import debug_log, track_time


class RSSArticle(TypedDict):
    """Article format expected by L2 pipeline."""
    feed_url: str
    source_name: str
    title: str
    link: str
    pub_date: str
    description: str
    full_content: Optional[str]
    categories: list[str]
    author: Optional[str]


def adapt_browser_use_to_articles(state: dict) -> dict:
    """
    Convert extracted browser-use articles to RSSArticle format.

    This makes browser-use articles compatible with the existing L2 pipeline.

    Args:
        state: Pipeline state with 'extracted_articles'

    Returns:
        Dict with 'raw_articles' list (same key as RSS pipeline)
    """
    with track_time("adapt_browser_use_to_articles"):
        debug_log("[NODE: adapt_browser_use_to_articles] Entering")

        extracted_articles = state.get("extracted_articles", [])
        debug_log(f"[NODE: adapt_browser_use_to_articles] Adapting {len(extracted_articles)} articles")

        raw_articles: list[RSSArticle] = []
        skipped = 0

        for article in extracted_articles:
            # Skip articles without required fields
            if not article.get("title"):
                debug_log(f"[NODE: adapt_browser_use_to_articles] Skipping article without title: {article.get('url', 'unknown')}")
                skipped += 1
                continue

            # Content may be sparse from browser-use (just snippets from listing page)
            # That's okay - we'll still try to process them
            content = article.get("content", "")
            description = content[:500] + "..." if len(content) > 500 else content

            # Convert to RSSArticle format
            rss_article = RSSArticle(
                feed_url=article.get("source_url", ""),  # Use source URL as feed URL
                source_name=article.get("source_name", "Unknown"),
                title=article["title"],
                link=article.get("url", ""),
                pub_date=article.get("date", ""),  # May be empty or None
                description=description,
                full_content=content if content else None,
                categories=[],  # Browser-use doesn't extract categories
                author=None,
            )

            raw_articles.append(rss_article)

        debug_log(f"[NODE: adapt_browser_use_to_articles] Adapted {len(raw_articles)} articles, skipped {skipped}")

        # Log per-source breakdown
        by_source: dict[str, int] = {}
        for article in raw_articles:
            source = article["source_name"]
            by_source[source] = by_source.get(source, 0) + 1

        for source, count in by_source.items():
            debug_log(f"[NODE: adapt_browser_use_to_articles]   {source}: {count} articles")

        return {"raw_articles": raw_articles}
