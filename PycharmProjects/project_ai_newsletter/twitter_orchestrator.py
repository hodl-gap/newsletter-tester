"""
Twitter Orchestrator - Twitter/X Scraping Pipeline

This orchestrator scrapes tweets from specified Twitter accounts and
produces structured output in the same format as the RSS pipeline.

Pipeline Flow:
    load_twitter_accounts -> fetch_twitter_content -> filter_by_date_twitter ->
    adapt_tweets_to_articles -> filter_business_news -> extract_metadata ->
    generate_summaries -> build_twitter_output -> save_twitter_content
"""

from typing import TypedDict, Optional

from langgraph.graph import StateGraph, START, END

from src.tracking import debug_log, reset_cost_tracker, cost_tracker, track_time

# Import Twitter-specific node functions
from src.functions.load_twitter_accounts import load_twitter_accounts
from src.functions.fetch_twitter_content import fetch_twitter_content
from src.functions.filter_by_date_twitter import filter_by_date_twitter
from src.functions.build_twitter_output import build_twitter_output
from src.functions.save_twitter_content import save_twitter_content

# Import reusable node functions from RSS pipeline
from src.functions.filter_business_news import filter_business_news
from src.functions.extract_metadata import extract_metadata
from src.functions.generate_summaries import generate_summaries


# =============================================================================
# State Definition
# =============================================================================

class TwitterAggregationState(TypedDict):
    """
    State object passed between nodes in the Twitter aggregation pipeline.
    """
    # Optional: filter for specific handles
    handle_filter: Optional[list[str]]

    # Optional: maximum tweet age in hours (default: 24)
    max_age_hours: Optional[int]

    # From load_twitter_accounts
    twitter_accounts: list[dict]
    twitter_settings: dict

    # From fetch_twitter_content
    raw_tweets: list[dict]

    # For compatibility with filter_business_news (adapter copies raw_tweets here)
    raw_articles: list[dict]

    # From filter_business_news
    filtered_articles: list[dict]
    discarded_articles: list[dict]

    # From extract_metadata (and generate_summaries updates this)
    enriched_articles: list[dict]

    # From build_twitter_output
    output_data: list[dict]

    # From save_twitter_content
    save_status: dict


# =============================================================================
# Adapter Node
# =============================================================================

def adapt_tweets_to_articles(state: dict) -> dict:
    """
    Adapter node that copies raw_tweets to raw_articles for compatibility
    with the reused filter_business_news node.

    The RawTweet type already includes compatibility fields:
    - link (same as url)
    - title (same as full_text)
    - description (quoted_text or empty)
    - source_name (same as handle)
    """
    with track_time("adapt_tweets_to_articles"):
        debug_log("[NODE: adapt_tweets_to_articles] Entering")

        raw_tweets = state.get("raw_tweets", [])
        debug_log(f"[NODE: adapt_tweets_to_articles] Adapting {len(raw_tweets)} tweets to article format")

        return {"raw_articles": raw_tweets}


# =============================================================================
# Graph Definition
# =============================================================================

def build_graph() -> StateGraph:
    """
    Build and return the Twitter aggregation LangGraph workflow.

    Returns:
        Compiled StateGraph ready to invoke.
    """
    # Initialize the graph with state schema
    graph = StateGraph(TwitterAggregationState)

    # Add nodes
    graph.add_node("load_twitter_accounts", load_twitter_accounts)
    graph.add_node("fetch_twitter_content", fetch_twitter_content)
    graph.add_node("filter_by_date_twitter", filter_by_date_twitter)
    graph.add_node("adapt_tweets_to_articles", adapt_tweets_to_articles)
    graph.add_node("filter_business_news", filter_business_news)
    graph.add_node("extract_metadata", extract_metadata)
    graph.add_node("generate_summaries", generate_summaries)
    graph.add_node("build_twitter_output", build_twitter_output)
    graph.add_node("save_twitter_content", save_twitter_content)

    # Define edges (linear pipeline)
    graph.add_edge(START, "load_twitter_accounts")
    graph.add_edge("load_twitter_accounts", "fetch_twitter_content")
    graph.add_edge("fetch_twitter_content", "filter_by_date_twitter")
    graph.add_edge("filter_by_date_twitter", "adapt_tweets_to_articles")
    graph.add_edge("adapt_tweets_to_articles", "filter_business_news")
    graph.add_edge("filter_business_news", "extract_metadata")
    graph.add_edge("extract_metadata", "generate_summaries")
    graph.add_edge("generate_summaries", "build_twitter_output")
    graph.add_edge("build_twitter_output", "save_twitter_content")
    graph.add_edge("save_twitter_content", END)

    # Compile the graph
    return graph.compile()


# =============================================================================
# Entry Point
# =============================================================================

def run(handle_filter: Optional[list[str]] = None, max_age_hours: int = 24) -> dict:
    """
    Run the Twitter aggregation pipeline.

    Args:
        handle_filter: Optional list of Twitter handles to filter for.
                      If None, all configured accounts are used.
        max_age_hours: Maximum tweet age in hours. Tweets older than this
                      are dropped before LLM filtering. Default: 24.

    Returns:
        Final state with aggregated content.
    """
    debug_log("=" * 60)
    debug_log("STARTING TWITTER AGGREGATION PIPELINE")
    if handle_filter:
        debug_log(f"HANDLE FILTER: {handle_filter}")
    debug_log(f"MAX AGE HOURS: {max_age_hours}")
    debug_log("=" * 60)

    # Reset cost tracker
    reset_cost_tracker()

    # Build and run graph
    app = build_graph()

    # Initialize empty state
    initial_state: TwitterAggregationState = {
        "handle_filter": handle_filter,
        "max_age_hours": max_age_hours,
        "twitter_accounts": [],
        "twitter_settings": {},
        "raw_tweets": [],
        "raw_articles": [],
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
