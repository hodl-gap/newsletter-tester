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


# =============================================================================
# Graph Definition
# =============================================================================

def build_graph() -> StateGraph:
    """
    Build and return the content aggregation LangGraph workflow.

    Returns:
        Compiled StateGraph ready to invoke.
    """
    # Initialize the graph with state schema
    graph = StateGraph(ContentAggregationState)

    # Add nodes
    graph.add_node("load_available_feeds", load_available_feeds)
    graph.add_node("fetch_rss_content", fetch_rss_content)
    graph.add_node("check_url_duplicates", check_url_duplicates)
    graph.add_node("filter_by_date", filter_by_date)
    graph.add_node("filter_business_news", filter_business_news)
    graph.add_node("extract_metadata", extract_metadata)
    graph.add_node("generate_summaries", generate_summaries)
    graph.add_node("build_output_dataframe", build_output_dataframe)
    graph.add_node("save_aggregated_content", save_aggregated_content)

    # Define edges (linear pipeline)
    graph.add_edge(START, "load_available_feeds")
    graph.add_edge("load_available_feeds", "fetch_rss_content")
    graph.add_edge("fetch_rss_content", "check_url_duplicates")
    graph.add_edge("check_url_duplicates", "filter_by_date")
    graph.add_edge("filter_by_date", "filter_business_news")
    graph.add_edge("filter_business_news", "extract_metadata")
    graph.add_edge("extract_metadata", "generate_summaries")
    graph.add_edge("generate_summaries", "build_output_dataframe")
    graph.add_edge("build_output_dataframe", "save_aggregated_content")
    graph.add_edge("save_aggregated_content", END)

    # Compile the graph
    return graph.compile()


# =============================================================================
# Entry Point
# =============================================================================

def run(source_filter: Optional[list[str]] = None, max_age_hours: int = 24) -> dict:
    """
    Run the content aggregation pipeline.

    Args:
        source_filter: Optional list of source names/URLs to filter for.
                      If None, all available sources are used.
        max_age_hours: Maximum article age in hours. Articles older than this
                      are dropped before LLM filtering. Default: 24.

    Returns:
        Final state with aggregated content.
    """
    debug_log("=" * 60)
    debug_log("STARTING CONTENT AGGREGATION PIPELINE")
    if source_filter:
        debug_log(f"SOURCE FILTER: {source_filter}")
    debug_log(f"MAX AGE HOURS: {max_age_hours}")
    debug_log("=" * 60)

    # Reset cost tracker
    reset_cost_tracker()

    # Build and run graph
    app = build_graph()

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
    }

    result = app.invoke(initial_state)

    # Print cost summary
    debug_log("=" * 60)
    debug_log("PIPELINE COMPLETE")
    cost_tracker.print_summary()
    debug_log("=" * 60)

    return result


if __name__ == "__main__":
    result = run()

    # Print quick summary
    save_status = result.get("save_status", {})
    print(f"\nOutput saved to:")
    print(f"  JSON: {save_status.get('json_path', 'N/A')}")
    print(f"  CSV:  {save_status.get('csv_path', 'N/A')}")
    print(f"  Records: {save_status.get('record_count', 0)}")
