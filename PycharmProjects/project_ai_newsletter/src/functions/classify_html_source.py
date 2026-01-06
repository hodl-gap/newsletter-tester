"""
Classify HTML Source Node

Determines the recommended scraping approach for each source
based on accessibility and analysis results.
"""

from typing import TypedDict

from src.tracking import debug_log, track_time


class SourceClassification(TypedDict):
    """Classification result for a source."""
    url: str
    status: str  # "scrapable", "requires_js", "blocked", "not_scrapable"
    source_type: str  # "news", "blog", "aggregator", "unknown"
    recommended_approach: str  # "http_simple", "http_with_js", "playwright", "not_recommended"
    confidence: float
    notes: str | None


def classify_html_source(state: dict) -> dict:
    """
    Classify sources and determine recommended scraping approach.

    Args:
        state: Pipeline state with 'accessibility_results', 'listing_analyses', 'article_analyses'

    Returns:
        Dict with 'source_classifications' list
    """
    with track_time("classify_html_source"):
        debug_log("[NODE: classify_html_source] Entering")

        accessibility_results = state.get("accessibility_results", [])
        listing_analyses = state.get("listing_analyses", [])
        article_analyses = state.get("article_analyses", [])

        # Build lookup dicts
        accessibility_by_url = {r["url"]: r for r in accessibility_results}
        listing_by_url = {a["url"]: a for a in listing_analyses}
        article_by_url = {a["url"]: a for a in article_analyses}

        # Get all URLs
        all_urls = set(accessibility_by_url.keys())

        classifications: list[SourceClassification] = []

        for url in all_urls:
            access = accessibility_by_url.get(url, {})
            listing = listing_by_url.get(url, {})
            article = article_by_url.get(url, {})

            classification = _classify_source(url, access, listing, article)
            classifications.append(classification)

            debug_log(f"[NODE: classify_html_source] {url}")
            debug_log(f"[NODE: classify_html_source]   status: {classification['status']}")
            debug_log(f"[NODE: classify_html_source]   approach: {classification['recommended_approach']}")

        # Summary
        status_counts = {}
        for c in classifications:
            status = c["status"]
            status_counts[status] = status_counts.get(status, 0) + 1

        debug_log(f"[NODE: classify_html_source] Summary: {status_counts}")

        return {"source_classifications": classifications}


def _classify_source(
    url: str,
    access: dict,
    listing: dict,
    article: dict,
) -> SourceClassification:
    """
    Classify a single source based on all analysis results.

    Args:
        url: Source URL
        access: Accessibility test result
        listing: Listing page analysis
        article: Article page analysis

    Returns:
        SourceClassification
    """
    # Check if blocked
    if access.get("blocked_by"):
        blocked_by = access["blocked_by"]
        return SourceClassification(
            url=url,
            status="blocked",
            source_type="unknown",
            recommended_approach="not_recommended",
            confidence=1.0,
            notes=f"Blocked by {blocked_by}",
        )

    # Check if requires JavaScript
    if access.get("requires_javascript"):
        # Even if it requires JS, we might have some info from listing/article analysis
        has_articles = listing.get("has_article_links", False)
        has_content = article.get("has_full_content", False)

        if has_articles and has_content:
            return SourceClassification(
                url=url,
                status="requires_js",
                source_type=_infer_source_type(listing),
                recommended_approach="playwright",
                confidence=0.7,
                notes="Requires JavaScript rendering but structure is analyzable",
            )
        else:
            return SourceClassification(
                url=url,
                status="requires_js",
                source_type="unknown",
                recommended_approach="playwright",
                confidence=0.4,
                notes="Requires JavaScript, limited analysis possible",
            )

    # Check if not accessible at all
    if not access.get("accessible"):
        error = access.get("error", "Unknown error")
        return SourceClassification(
            url=url,
            status="not_scrapable",
            source_type="unknown",
            recommended_approach="not_recommended",
            confidence=1.0,
            notes=f"Not accessible: {error}",
        )

    # Source is accessible via HTTP - check analysis quality
    has_articles = listing.get("has_article_links", False)
    has_content = article.get("has_full_content", False)
    listing_confidence = listing.get("confidence", 0)
    article_confidence = article.get("confidence", 0)

    if has_articles and has_content:
        # Best case: fully scrapable
        avg_confidence = (listing_confidence + article_confidence) / 2
        return SourceClassification(
            url=url,
            status="scrapable",
            source_type=_infer_source_type(listing),
            recommended_approach="http_simple",
            confidence=avg_confidence,
            notes="Full article content accessible via HTTP",
        )
    elif has_articles and not has_content:
        # Has article links but content extraction uncertain
        return SourceClassification(
            url=url,
            status="scrapable",
            source_type=_infer_source_type(listing),
            recommended_approach="http_simple",
            confidence=listing_confidence * 0.6,
            notes="Article links found but content extraction uncertain",
        )
    elif not has_articles:
        # No article links found
        return SourceClassification(
            url=url,
            status="not_scrapable",
            source_type="unknown",
            recommended_approach="not_recommended",
            confidence=0.7,
            notes="No article links found on listing page",
        )
    else:
        # Fallback
        return SourceClassification(
            url=url,
            status="not_scrapable",
            source_type="unknown",
            recommended_approach="not_recommended",
            confidence=0.5,
            notes="Could not determine scraping approach",
        )


def _infer_source_type(listing: dict) -> str:
    """Infer source type from listing analysis."""
    listing_type = listing.get("listing_type", "unknown")

    if listing_type in ["blog"]:
        return "blog"
    elif listing_type in ["news_grid", "magazine", "feed"]:
        return "news"
    else:
        return "unknown"
