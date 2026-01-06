"""
Merge HTML Results Node

Combines all analysis results into final HTML availability records.
"""

from datetime import datetime
from typing import TypedDict, Any

from src.tracking import debug_log, track_time


class HTMLAvailabilityResult(TypedDict):
    """Final HTML availability result for a source."""
    url: str
    status: str  # "scrapable", "requires_js", "blocked", "not_scrapable"

    # Accessibility info
    accessibility: dict[str, Any]

    # Listing page analysis
    listing_page: dict[str, Any] | None

    # Article page analysis
    article_page: dict[str, Any] | None

    # Recommendation
    recommendation: dict[str, Any]

    # Metadata
    method: str
    analyzed_at: str


def merge_html_results(state: dict) -> dict:
    """
    Merge all analysis results into final HTML availability records.

    Args:
        state: Pipeline state with all analysis results

    Returns:
        Dict with 'final_results' list
    """
    with track_time("merge_html_results"):
        debug_log("[NODE: merge_html_results] Entering")

        accessibility_results = state.get("accessibility_results", [])
        listing_analyses = state.get("listing_analyses", [])
        article_analyses = state.get("article_analyses", [])
        source_classifications = state.get("source_classifications", [])

        # Build lookup dicts
        accessibility_by_url = {r["url"]: r for r in accessibility_results}
        listing_by_url = {a["url"]: a for a in listing_analyses}
        article_by_url = {a["url"]: a for a in article_analyses}
        classification_by_url = {c["url"]: c for c in source_classifications}

        # Get all URLs from classifications (should have all)
        all_urls = set(classification_by_url.keys())

        final_results: list[HTMLAvailabilityResult] = []
        timestamp = datetime.now().isoformat()

        for url in all_urls:
            access = accessibility_by_url.get(url, {})
            listing = listing_by_url.get(url, {})
            article = article_by_url.get(url, {})
            classification = classification_by_url.get(url, {})

            result = _build_result(url, access, listing, article, classification, timestamp)
            final_results.append(result)

        debug_log(f"[NODE: merge_html_results] Created {len(final_results)} final results")

        return {"final_results": final_results}


def _build_result(
    url: str,
    access: dict,
    listing: dict,
    article: dict,
    classification: dict,
    timestamp: str,
) -> HTMLAvailabilityResult:
    """Build a single final result record."""

    # Accessibility section
    accessibility = {
        "http_works": access.get("accessible", False),
        "status_code": access.get("status_code"),
        "blocked_by": access.get("blocked_by"),
        "requires_javascript": access.get("requires_javascript", False),
        "html_length": access.get("html_length", 0),
        "error": access.get("error"),
    }

    # Listing page section
    listing_page = None
    if listing.get("has_article_links"):
        listing_page = {
            "url": listing.get("url"),
            "has_article_links": listing.get("has_article_links", False),
            "article_url_pattern": listing.get("article_url_pattern"),
            "sample_urls": listing.get("sample_article_urls", []),
            "listing_type": listing.get("listing_type"),
            "pagination_pattern": listing.get("pagination_pattern"),
        }

    # Article page section
    article_page = None
    if article.get("has_full_content"):
        article_page = {
            "sample_article_url": article.get("sample_article_url"),
            "has_full_content": article.get("has_full_content", False),
            "title_selector": article.get("title_selector"),
            "content_selector": article.get("content_selector"),
            "date_selector": article.get("date_selector"),
            "date_format": article.get("date_format"),
            "author_selector": article.get("author_selector"),
            "sample_extracted": article.get("sample_extracted"),
        }

    # Recommendation section
    recommendation = {
        "approach": classification.get("recommended_approach", "not_recommended"),
        "source_type": classification.get("source_type", "unknown"),
        "confidence": classification.get("confidence", 0),
        "notes": classification.get("notes"),
    }

    return HTMLAvailabilityResult(
        url=url,
        status=classification.get("status", "not_scrapable"),
        accessibility=accessibility,
        listing_page=listing_page,
        article_page=article_page,
        recommendation=recommendation,
        method="llm_analysis",
        analyzed_at=timestamp,
    )
