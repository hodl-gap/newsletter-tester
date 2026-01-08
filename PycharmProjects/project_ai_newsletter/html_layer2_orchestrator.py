"""
HTML Layer 2 Orchestrator - Content Scraping

This orchestrator scrapes content from sources discovered as "scrapable"
in HTML Layer 1. It extracts articles using CSS selectors and feeds them
into the existing Layer 2 pipeline for filtering, metadata, and summaries.

Pipeline Flow:
    load_scrapable_sources -> fetch_listing_pages -> extract_article_urls ->
    fetch_html_articles -> parse_article_content -> adapt_html_to_articles ->
    filter_by_date -> filter_business_news -> extract_metadata ->
    generate_summaries -> build_output_dataframe -> save_html_content

Input: data/html_availability.json (sources with status="scrapable" and full config)
Output: data/html_news.json, data/html_news.csv, data/html_discarded.csv
"""

from typing import TypedDict, Optional

from langgraph.graph import StateGraph, START, END

from src.config import set_config, DEFAULT_CONFIG
from src.tracking import debug_log, reset_cost_tracker, cost_tracker, track_time

# HTML Layer 2 specific nodes
from src.functions.load_scrapable_sources import load_scrapable_sources
from src.functions.fetch_listing_pages import fetch_listing_pages
from src.functions.extract_article_urls import extract_article_urls
from src.functions.fetch_html_articles import fetch_html_articles
from src.functions.parse_article_content import parse_article_content
from src.functions.adapt_html_to_articles import adapt_html_to_articles
from src.functions.save_html_content import save_html_content

# Reused from RSS Layer 2
from src.functions.filter_by_date import filter_by_date
from src.functions.filter_business_news import filter_business_news
from src.functions.extract_metadata import extract_metadata
from src.functions.generate_summaries import generate_summaries
from src.functions.build_output_dataframe import build_output_dataframe


# =============================================================================
# State Definition
# =============================================================================

class HTMLContentState(TypedDict):
    """State for HTML Layer 2 pipeline."""
    # Optional: filter for specific URLs (substring match)
    url_filter: Optional[list[str]]

    # Optional: maximum article age in hours (default: 24)
    max_age_hours: Optional[int]

    # From load_scrapable_sources
    scrapable_sources: list[dict]

    # From fetch_listing_pages
    listing_pages: list[dict]

    # From extract_article_urls
    article_urls: list[dict]

    # From fetch_html_articles
    fetched_articles: list[dict]

    # From parse_article_content
    parsed_articles: list[dict]

    # From adapt_html_to_articles (same format as RSS pipeline)
    raw_articles: list[dict]

    # From filter_business_news
    filtered_articles: list[dict]
    discarded_articles: list[dict]

    # From extract_metadata (and generate_summaries updates this)
    enriched_articles: list[dict]

    # From build_output_dataframe
    output_data: list[dict]

    # From save_html_content
    save_status: dict


# =============================================================================
# Graph Definition
# =============================================================================

def build_graph() -> StateGraph:
    """
    Build and return the HTML content scraping workflow.

    Returns:
        Compiled StateGraph ready to invoke.
    """
    graph = StateGraph(HTMLContentState)

    # Add HTML-specific nodes
    graph.add_node("load_scrapable_sources", load_scrapable_sources)
    graph.add_node("fetch_listing_pages", fetch_listing_pages)
    graph.add_node("extract_article_urls", extract_article_urls)
    graph.add_node("fetch_html_articles", fetch_html_articles)
    graph.add_node("parse_article_content", parse_article_content)
    graph.add_node("adapt_html_to_articles", adapt_html_to_articles)

    # Add reused L2 nodes
    graph.add_node("filter_by_date", filter_by_date)
    graph.add_node("filter_business_news", filter_business_news)
    graph.add_node("extract_metadata", extract_metadata)
    graph.add_node("generate_summaries", generate_summaries)
    graph.add_node("build_output_dataframe", build_output_dataframe)
    graph.add_node("save_html_content", save_html_content)

    # Define edges (linear pipeline)
    graph.add_edge(START, "load_scrapable_sources")
    graph.add_edge("load_scrapable_sources", "fetch_listing_pages")
    graph.add_edge("fetch_listing_pages", "extract_article_urls")
    graph.add_edge("extract_article_urls", "fetch_html_articles")
    graph.add_edge("fetch_html_articles", "parse_article_content")
    graph.add_edge("parse_article_content", "adapt_html_to_articles")
    graph.add_edge("adapt_html_to_articles", "filter_by_date")
    graph.add_edge("filter_by_date", "filter_business_news")
    graph.add_edge("filter_business_news", "extract_metadata")
    graph.add_edge("extract_metadata", "generate_summaries")
    graph.add_edge("generate_summaries", "build_output_dataframe")
    graph.add_edge("build_output_dataframe", "save_html_content")
    graph.add_edge("save_html_content", END)

    return graph.compile()


# =============================================================================
# Entry Point
# =============================================================================

def run(
    url_filter: Optional[list[str]] = None,
    max_age_hours: int = 24,
    config: str = DEFAULT_CONFIG
) -> dict:
    """
    Run the HTML content scraping pipeline.

    Scrapes articles from sources marked as "scrapable" in html_availability.json,
    then runs them through the standard L2 pipeline for filtering and enrichment.

    Args:
        url_filter: Optional list of URL substrings to filter sources.
                   Example: ['rundown', 'pulsenews']
        max_age_hours: Maximum article age in hours. Articles older than this
                      are dropped before LLM filtering. Default: 24.
        config: Configuration name (default: business_news).

    Returns:
        Final state with scraped and enriched content.
    """
    # Set active configuration
    set_config(config)

    with track_time("html_layer2_pipeline"):
        debug_log("=" * 60)
        debug_log("HTML LAYER 2: CONTENT SCRAPING")
        debug_log(f"CONFIG: {config}")
        debug_log("=" * 60)
        if url_filter:
            debug_log(f"URL FILTER: {url_filter}")
        debug_log(f"MAX AGE HOURS: {max_age_hours}")

        # Reset cost tracker
        reset_cost_tracker()

        # Build and run graph
        app = build_graph()

        initial_state: HTMLContentState = {
            "url_filter": url_filter,
            "max_age_hours": max_age_hours,
            "scrapable_sources": [],
            "listing_pages": [],
            "article_urls": [],
            "fetched_articles": [],
            "parsed_articles": [],
            "raw_articles": [],
            "filtered_articles": [],
            "discarded_articles": [],
            "enriched_articles": [],
            "output_data": [],
            "save_status": {},
        }

        result = app.invoke(initial_state)

        # Print cost summary
        debug_log("")
        debug_log("=" * 60)
        debug_log("PIPELINE COMPLETE")
        debug_log("=" * 60)
        cost_tracker.print_summary()

        return result


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run HTML content scraping (HTML Layer 2)")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="Config to use (default: business_news)")
    parser.add_argument("--url-filter", nargs="*", help="Filter for specific URLs")
    parser.add_argument("--max-age-hours", type=int, default=24, help="Max article age in hours (default: 24)")

    args = parser.parse_args()

    result = run(
        config=args.config,
        url_filter=args.url_filter,
        max_age_hours=args.max_age_hours
    )

    # Print quick summary
    save_status = result.get("save_status", {})
    print(f"\nOutput saved to:")
    print(f"  JSON: {save_status.get('json_path', 'N/A')}")
    print(f"  CSV:  {save_status.get('csv_path', 'N/A')}")
    print(f"  Records: {save_status.get('record_count', 0)}")
