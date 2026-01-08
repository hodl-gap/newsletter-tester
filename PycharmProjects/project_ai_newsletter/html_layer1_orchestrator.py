"""
HTML Layer 1 Orchestrator - Scrapability Discovery

This orchestrator analyzes "unavailable" sources from RSS Layer 1
to determine if they can be scraped via HTTP.

Pipeline: Load Unavailable -> Test HTTP -> Analyze Listing -> Analyze Article ->
          Classify -> Merge -> Save

Input: data/rss_availability.json (filters status="unavailable")
Output: data/html_availability.json
"""

from typing import TypedDict, Any

from langgraph.graph import StateGraph, START, END

from src.config import set_config, DEFAULT_CONFIG
from src.functions.load_unavailable_sources import load_unavailable_sources, SourceInfo
from src.functions.test_http_accessibility import test_http_accessibility, AccessibilityResult
from src.functions.analyze_listing_page import analyze_listing_page, ListingAnalysis
from src.functions.analyze_article_page import analyze_article_page, ArticleAnalysis
from src.functions.classify_html_source import classify_html_source, SourceClassification
from src.functions.merge_html_results import merge_html_results, HTMLAvailabilityResult
from src.functions.save_html_availability import save_html_availability
from src.tracking import track_time, cost_tracker, reset_cost_tracker, debug_log


# =============================================================================
# State Definition
# =============================================================================

class HTMLDiscoveryState(TypedDict):
    """State for HTML Layer 1 pipeline."""
    url_filter: list[str] | None  # Optional filter for URLs (substring match)
    sources_to_test: list[SourceInfo]
    accessibility_results: list[AccessibilityResult]
    listing_analyses: list[ListingAnalysis]
    article_analyses: list[ArticleAnalysis]
    source_classifications: list[SourceClassification]
    final_results: list[HTMLAvailabilityResult]
    output_file: str | None


# =============================================================================
# Graph Definition
# =============================================================================

def build_graph() -> StateGraph:
    """Build and return the HTML discovery graph."""
    graph = StateGraph(HTMLDiscoveryState)

    # Add nodes
    graph.add_node("load_unavailable_sources", load_unavailable_sources)
    graph.add_node("test_http_accessibility", test_http_accessibility)
    graph.add_node("analyze_listing_page", analyze_listing_page)
    graph.add_node("analyze_article_page", analyze_article_page)
    graph.add_node("classify_html_source", classify_html_source)
    graph.add_node("merge_html_results", merge_html_results)
    graph.add_node("save_html_availability", save_html_availability)

    # Define edges (linear pipeline)
    graph.add_edge(START, "load_unavailable_sources")
    graph.add_edge("load_unavailable_sources", "test_http_accessibility")
    graph.add_edge("test_http_accessibility", "analyze_listing_page")
    graph.add_edge("analyze_listing_page", "analyze_article_page")
    graph.add_edge("analyze_article_page", "classify_html_source")
    graph.add_edge("classify_html_source", "merge_html_results")
    graph.add_edge("merge_html_results", "save_html_availability")
    graph.add_edge("save_html_availability", END)

    return graph.compile()


# =============================================================================
# Entry Point
# =============================================================================

def run(url_filter: list[str] | None = None, config: str = DEFAULT_CONFIG) -> dict:
    """
    Run the HTML scrapability discovery pipeline.

    Analyzes "unavailable" sources from RSS Layer 1 to determine
    if they can be scraped via HTTP.

    Args:
        url_filter: Optional list of URL substrings to filter sources.
                   Only sources containing any of these substrings will be tested.
                   Example: ['pulsenews', 'rundown']
        config: Configuration name (default: business_news).

    Returns:
        Final pipeline state with results.
    """
    # Set active configuration
    set_config(config)

    with track_time("html_layer1_pipeline"):
        debug_log("=" * 60)
        debug_log("HTML LAYER 1: SCRAPABILITY DISCOVERY")
        debug_log(f"CONFIG: {config}")
        debug_log("=" * 60)

        # Reset cost tracker
        reset_cost_tracker()

        # Build and run graph
        graph = build_graph()

        initial_state: HTMLDiscoveryState = {
            "url_filter": url_filter,
            "sources_to_test": [],
            "accessibility_results": [],
            "listing_analyses": [],
            "article_analyses": [],
            "source_classifications": [],
            "final_results": [],
            "output_file": None,
        }

        # Run pipeline
        final_state = graph.invoke(initial_state)

        # Print cost summary
        debug_log("")
        debug_log("=" * 60)
        debug_log("PIPELINE COMPLETE")
        debug_log("=" * 60)
        cost_tracker.print_summary()

        return final_state


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run HTML scrapability discovery (HTML Layer 1)")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="Config to use (default: business_news)")
    parser.add_argument("--url-filter", nargs="*", help="Filter for specific URLs")

    args = parser.parse_args()

    run(config=args.config, url_filter=args.url_filter)
