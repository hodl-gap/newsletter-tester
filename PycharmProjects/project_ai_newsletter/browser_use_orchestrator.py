"""
Browser-Use Orchestrator - Scraping Blocked Sources

This orchestrator uses browser-use Agent (LLM-driven browsing) to scrape content
from sources blocked by CAPTCHA/Cloudflare. It bypasses anti-bot protection by
using a real browser controlled by Claude Sonnet.

Pipeline Flow:
    load_browser_use_sources -> fetch_with_browser_agent -> adapt_browser_use_to_articles ->
    filter_by_date -> filter_business_news -> extract_metadata ->
    generate_summaries -> build_output_dataframe -> save_browser_use_content

Input: configs/{config}/config.json["browser_use_sources"]
Output: data/{config}/browser_use_news.json, browser_use_news.csv, browser_use_failures.json
"""

from typing import TypedDict, Optional

from langgraph.graph import StateGraph, START, END

from src.config import set_config, DEFAULT_CONFIG
from src.tracking import debug_log, reset_cost_tracker, cost_tracker, track_time

# Browser-use specific nodes
from src.functions.load_browser_use_sources import load_browser_use_sources
from src.functions.fetch_with_browser_agent import fetch_with_browser_agent_sync
from src.functions.adapt_browser_use_to_articles import adapt_browser_use_to_articles
from src.functions.save_browser_use_content import save_browser_use_content

# Reused from RSS/HTML Layer 2
from src.functions.filter_by_date import filter_by_date
from src.functions.filter_business_news import filter_business_news
from src.functions.extract_metadata import extract_metadata
from src.functions.generate_summaries import generate_summaries
from src.functions.build_output_dataframe import build_output_dataframe


# =============================================================================
# State Definition
# =============================================================================

class BrowserUseState(TypedDict):
    """State for browser-use pipeline."""
    # Optional: filter for specific URLs (substring match)
    url_filter: Optional[list[str]]

    # Optional: maximum article age in hours (default: 24)
    max_age_hours: Optional[int]

    # From load_browser_use_sources
    browser_use_sources: list[dict]
    browser_use_settings: dict

    # From fetch_with_browser_agent
    extracted_articles: list[dict]
    browser_use_failures: list[dict]

    # From adapt_browser_use_to_articles (same format as RSS pipeline)
    raw_articles: list[dict]

    # From filter_business_news
    filtered_articles: list[dict]
    discarded_articles: list[dict]

    # From extract_metadata (and generate_summaries updates this)
    enriched_articles: list[dict]

    # From build_output_dataframe
    output_data: list[dict]

    # From save_browser_use_content
    save_status: dict


# =============================================================================
# Graph Definition
# =============================================================================

def build_graph() -> StateGraph:
    """
    Build and return the browser-use scraping workflow.

    Returns:
        Compiled StateGraph ready to invoke.
    """
    graph = StateGraph(BrowserUseState)

    # Add browser-use specific nodes
    graph.add_node("load_browser_use_sources", load_browser_use_sources)
    graph.add_node("fetch_with_browser_agent", fetch_with_browser_agent_sync)
    graph.add_node("adapt_browser_use_to_articles", adapt_browser_use_to_articles)

    # Add reused L2 nodes
    graph.add_node("filter_by_date", filter_by_date)
    graph.add_node("filter_business_news", filter_business_news)
    graph.add_node("extract_metadata", extract_metadata)
    graph.add_node("generate_summaries", generate_summaries)
    graph.add_node("build_output_dataframe", build_output_dataframe)
    graph.add_node("save_browser_use_content", save_browser_use_content)

    # Define edges (linear pipeline)
    graph.add_edge(START, "load_browser_use_sources")
    graph.add_edge("load_browser_use_sources", "fetch_with_browser_agent")
    graph.add_edge("fetch_with_browser_agent", "adapt_browser_use_to_articles")
    graph.add_edge("adapt_browser_use_to_articles", "filter_by_date")
    graph.add_edge("filter_by_date", "filter_business_news")
    graph.add_edge("filter_business_news", "extract_metadata")
    graph.add_edge("extract_metadata", "generate_summaries")
    graph.add_edge("generate_summaries", "build_output_dataframe")
    graph.add_edge("build_output_dataframe", "save_browser_use_content")
    graph.add_edge("save_browser_use_content", END)

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
    Run the browser-use content scraping pipeline.

    Scrapes articles from sources in browser_use_sources config using
    LLM-driven browser automation, then runs them through the standard
    L2 pipeline for filtering and enrichment.

    Args:
        url_filter: Optional list of URL substrings to filter sources.
                   Example: ['economictimes', 'scmp']
        max_age_hours: Maximum article age in hours. Articles older than this
                      are dropped before LLM filtering. Default: 24.
        config: Configuration name (default: business_news).

    Returns:
        Final state with scraped and enriched content.
    """
    # Set active configuration
    set_config(config)

    with track_time("browser_use_pipeline"):
        debug_log("=" * 60)
        debug_log("BROWSER-USE LAYER 2: BLOCKED SOURCES SCRAPING")
        debug_log(f"CONFIG: {config}")
        debug_log("=" * 60)
        if url_filter:
            debug_log(f"URL FILTER: {url_filter}")
        debug_log(f"MAX AGE HOURS: {max_age_hours}")

        # Reset cost tracker
        reset_cost_tracker()

        # Build and run graph
        app = build_graph()

        initial_state: BrowserUseState = {
            "url_filter": url_filter,
            "max_age_hours": max_age_hours,
            "browser_use_sources": [],
            "browser_use_settings": {},
            "extracted_articles": [],
            "browser_use_failures": [],
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

    parser = argparse.ArgumentParser(description="Run browser-use scraping for blocked sources")
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
    print(f"  Failures: {save_status.get('failure_count', 0)}")
