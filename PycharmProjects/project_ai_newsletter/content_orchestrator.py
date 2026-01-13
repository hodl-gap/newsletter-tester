"""
Content Orchestrator - Layer 2 Pipeline

This orchestrator aggregates content from RSS feeds discovered in Layer 1.
It fetches articles, filters for business news, extracts metadata,
generates English summaries, and outputs a structured DataFrame.

Pipeline Flow:
    load_available_feeds -> fetch_rss_content -> check_url_duplicates ->
    filter_by_date -> filter_business_news -> extract_metadata ->
    generate_summaries -> build_output_dataframe -> save_aggregated_content
"""

from typing import TypedDict, Optional

from langgraph.graph import StateGraph, START, END

from src.config import set_config, DEFAULT_CONFIG
from src.tracking import debug_log, reset_cost_tracker, cost_tracker

# Import node functions
from src.functions.load_available_feeds import load_available_feeds
from src.functions.fetch_rss_content import fetch_rss_content
from src.functions.filter_business_news import filter_business_news
from src.functions.extract_metadata import extract_metadata
from src.functions.generate_summaries import generate_summaries
from src.functions.build_output_dataframe import build_output_dataframe
from src.functions.save_aggregated_content import save_aggregated_content
from src.functions.filter_by_date import filter_by_date
from src.functions.check_url_duplicates import check_url_duplicates
from src.functions.load_rss_cache import load_rss_cache
from src.functions.archive_rss_cache import archive_rss_cache


# =============================================================================
# State Definition
# =============================================================================

class ContentAggregationState(TypedDict):
    """
    State object passed between nodes in the content aggregation pipeline.
    """
    # Optional: filter for specific sources
    source_filter: Optional[list[str]]

    # Optional: maximum article age in hours (default: 24)
    max_age_hours: Optional[int]

    # From load_available_feeds
    available_feeds: list[dict]

    # From fetch_rss_content
    raw_articles: list[dict]

    # From check_url_duplicates
    url_duplicates_dropped: Optional[int]

    # From filter_business_news
    filtered_articles: list[dict]
    discarded_articles: list[dict]

    # From extract_metadata (and generate_summaries updates this)
    enriched_articles: list[dict]

    # From build_output_dataframe
    output_data: list[dict]

    # From save_aggregated_content
    save_status: dict

    # From archive_rss_cache (when using --from-cache)
    archive_status: Optional[dict]


# =============================================================================
# Graph Definition
# =============================================================================

def build_graph(from_cache: bool = False) -> StateGraph:
    """
    Build and return the content aggregation LangGraph workflow.

    Args:
        from_cache: If True, load from RSS cache instead of fetching live.
                   Also archives cache after successful processing.

    Returns:
        Compiled StateGraph ready to invoke.
    """
    # Initialize the graph with state schema
    graph = StateGraph(ContentAggregationState)

    # Add nodes based on mode
    if from_cache:
        # Cache mode: load from cache, process, then archive
        graph.add_node("load_rss_cache", load_rss_cache)
    else:
        # Live mode: fetch from RSS feeds
        graph.add_node("load_available_feeds", load_available_feeds)
        graph.add_node("fetch_rss_content", fetch_rss_content)

    # Common processing nodes
    graph.add_node("check_url_duplicates", check_url_duplicates)
    graph.add_node("filter_by_date", filter_by_date)
    graph.add_node("filter_business_news", filter_business_news)
    graph.add_node("extract_metadata", extract_metadata)
    graph.add_node("generate_summaries", generate_summaries)
    graph.add_node("build_output_dataframe", build_output_dataframe)
    graph.add_node("save_aggregated_content", save_aggregated_content)

    if from_cache:
        graph.add_node("archive_rss_cache", archive_rss_cache)

    # Define edges based on mode
    if from_cache:
        graph.add_edge(START, "load_rss_cache")
        graph.add_edge("load_rss_cache", "check_url_duplicates")
    else:
        graph.add_edge(START, "load_available_feeds")
        graph.add_edge("load_available_feeds", "fetch_rss_content")
        graph.add_edge("fetch_rss_content", "check_url_duplicates")

    # Common edges
    graph.add_edge("check_url_duplicates", "filter_by_date")
    graph.add_edge("filter_by_date", "filter_business_news")
    graph.add_edge("filter_business_news", "extract_metadata")
    graph.add_edge("extract_metadata", "generate_summaries")
    graph.add_edge("generate_summaries", "build_output_dataframe")
    graph.add_edge("build_output_dataframe", "save_aggregated_content")

    if from_cache:
        graph.add_edge("save_aggregated_content", "archive_rss_cache")
        graph.add_edge("archive_rss_cache", END)
    else:
        graph.add_edge("save_aggregated_content", END)

    # Compile the graph
    return graph.compile()


# =============================================================================
# Entry Point
# =============================================================================

def run(
    source_filter: Optional[list[str]] = None,
    max_age_hours: int = 24,
    config: str = DEFAULT_CONFIG,
    from_cache: bool = False
) -> dict:
    """
    Run the content aggregation pipeline.

    Args:
        source_filter: Optional list of source names/URLs to filter for.
                      If None, all available sources are used.
        max_age_hours: Maximum article age in hours. Articles older than this
                      are dropped before LLM filtering. Default: 24.
        config: Configuration name (default: business_news).
        from_cache: If True, load articles from RSS cache instead of fetching live.
                   After processing, cache is archived and cleared.

    Returns:
        Final state with aggregated content.
    """
    # Set active configuration
    set_config(config)

    debug_log("=" * 60)
    debug_log("STARTING CONTENT AGGREGATION PIPELINE")
    debug_log(f"CONFIG: {config}")
    debug_log(f"MODE: {'from-cache' if from_cache else 'live-fetch'}")
    if source_filter:
        debug_log(f"SOURCE FILTER: {source_filter}")
    debug_log(f"MAX AGE HOURS: {max_age_hours}")
    debug_log("=" * 60)

    # Reset cost tracker
    reset_cost_tracker()

    # Build and run graph
    app = build_graph(from_cache=from_cache)

    # Initialize empty state
    initial_state: ContentAggregationState = {
        "source_filter": source_filter,
        "max_age_hours": max_age_hours,
        "available_feeds": [],
        "raw_articles": [],
        "url_duplicates_dropped": 0,
        "filtered_articles": [],
        "discarded_articles": [],
        "enriched_articles": [],
        "output_data": [],
        "save_status": {},
        "archive_status": None,
    }

    result = app.invoke(initial_state)

    # Print cost summary
    debug_log("=" * 60)
    debug_log("PIPELINE COMPLETE")
    cost_tracker.print_summary()
    if from_cache and result.get("archive_status"):
        archive_status = result["archive_status"]
        debug_log(f"Cache archived: {archive_status.get('archived', 0)} articles")
    debug_log("=" * 60)

    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run content aggregation pipeline (Layer 2)")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="Config to use (default: business_news)")
    parser.add_argument("--source-filter", nargs="*", help="Filter for specific sources")
    parser.add_argument("--max-age-hours", type=int, default=24, help="Max article age in hours (default: 24)")
    parser.add_argument("--from-cache", action="store_true",
                       help="Load articles from RSS cache instead of fetching live. "
                            "Use with rss_fetch_orchestrator.py for separated fetch/process workflow.")

    args = parser.parse_args()

    result = run(
        config=args.config,
        source_filter=args.source_filter,
        max_age_hours=args.max_age_hours,
        from_cache=args.from_cache
    )

    # Print quick summary
    save_status = result.get("save_status", {})
    print(f"\nOutput saved to:")
    print(f"  JSON: {save_status.get('json_path', 'N/A')}")
    print(f"  CSV:  {save_status.get('csv_path', 'N/A')}")
    print(f"  Records: {save_status.get('record_count', 0)}")

    if args.from_cache:
        archive_status = result.get("archive_status", {})
        print(f"\nCache archived: {archive_status.get('archived', 0)} articles")
        print(f"Cache cleared: {archive_status.get('cleared', False)}")
