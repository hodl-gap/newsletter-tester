"""
Adapt HTML to Articles Node

Converts parsed HTML articles to RSSArticle format for compatibility
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


def adapt_html_to_articles(state: dict) -> dict:
    """
    Convert parsed HTML articles to RSSArticle format.

    This makes scraped articles compatible with the existing L2 pipeline.

    Args:
        state: Pipeline state with 'parsed_articles'

    Returns:
        Dict with 'raw_articles' list (same key as RSS pipeline)
    """
    with track_time("adapt_html_to_articles"):
        debug_log("[NODE: adapt_html_to_articles] Entering")

        parsed_articles = state.get("parsed_articles", [])
        debug_log(f"[NODE: adapt_html_to_articles] Adapting {len(parsed_articles)} articles")

        raw_articles: list[RSSArticle] = []
        skipped = 0

        for article in parsed_articles:
            # Skip articles without required fields
            if not article.get("title"):
                debug_log(f"[NODE: adapt_html_to_articles] Skipping article without title: {article.get('url', 'unknown')}")
                skipped += 1
                continue

            if not article.get("content"):
                debug_log(f"[NODE: adapt_html_to_articles] Skipping article without content: {article.get('url', 'unknown')}")
                skipped += 1
                continue

            # Create description from content (first ~500 chars)
            content = article["content"]
            description = content[:500] + "..." if len(content) > 500 else content

            # Convert to RSSArticle format
            rss_article = RSSArticle(
                feed_url=article.get("source_url", ""),  # Use source URL as feed URL
                source_name=article.get("source_name", "Unknown"),
                title=article["title"],
                link=article.get("url", ""),
                pub_date=article.get("date", ""),  # May be empty
                description=description,
                full_content=content,
                categories=[],  # HTML scraping doesn't extract categories
                author=article.get("author"),
            )

            raw_articles.append(rss_article)

        debug_log(f"[NODE: adapt_html_to_articles] Adapted {len(raw_articles)} articles, skipped {skipped}")

        # Log per-source breakdown
        by_source: dict[str, int] = {}
        for article in raw_articles:
            source = article["source_name"]
            by_source[source] = by_source.get(source, 0) + 1

        for source, count in by_source.items():
            debug_log(f"[NODE: adapt_html_to_articles]   {source}: {count} articles")

        return {"raw_articles": raw_articles}
