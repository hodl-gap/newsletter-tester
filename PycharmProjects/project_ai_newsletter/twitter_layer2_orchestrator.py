"""
Twitter Layer 2 Orchestrator - Content Aggregation

Processes cached tweets from active accounts (discovered by Layer 1).
Uses cached tweets instead of re-scraping.

Pipeline Flow:
    load_available_accounts -> load_cached_tweets -> filter_by_date_twitter ->
    fetch_link_content -> adapt_tweets_to_articles -> filter_business_news ->
    extract_metadata -> generate_summaries -> build_twitter_output -> save_twitter_content

Input:
    - data/twitter_availability.json (from Layer 1)
    - data/twitter_raw_cache.json (from Layer 1)

Output:
    - data/twitter_news.json
    - data/twitter_news.csv
    - data/twitter_discarded.csv
"""

from typing import TypedDict, Optional

from langgraph.graph import StateGraph, START, END

from src.config import set_config, DEFAULT_CONFIG
from src.tracking import debug_log, reset_cost_tracker, cost_tracker, track_time

# Import Layer 2 specific node functions
from src.functions.load_available_twitter_accounts import load_available_twitter_accounts
from src.functions.load_cached_tweets import load_cached_tweets
from src.functions.filter_by_date_twitter import filter_by_date_twitter
from src.functions.fetch_link_content import fetch_link_content
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

    # Optional: read from shared cache instead of config-specific cache
    use_shared_cache: bool

    # From load_available_twitter_accounts
    available_accounts: list[dict]
    twitter_settings: dict

    # From load_cached_tweets
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
    graph.add_node("load_available_twitter_accounts", load_available_twitter_accounts)
    graph.add_node("load_cached_tweets", load_cached_tweets)
    graph.add_node("filter_by_date_twitter", filter_by_date_twitter)
    graph.add_node("fetch_link_content", fetch_link_content)
    graph.add_node("adapt_tweets_to_articles", adapt_tweets_to_articles)
    graph.add_node("filter_business_news", filter_business_news)
    graph.add_node("extract_metadata", extract_metadata)
    graph.add_node("generate_summaries", generate_summaries)
    graph.add_node("build_twitter_output", build_twitter_output)
    graph.add_node("save_twitter_content", save_twitter_content)

    # Define edges (linear pipeline)
    graph.add_edge(START, "load_available_twitter_accounts")
    graph.add_edge("load_available_twitter_accounts", "load_cached_tweets")
    graph.add_edge("load_cached_tweets", "filter_by_date_twitter")
    graph.add_edge("filter_by_date_twitter", "fetch_link_content")
    graph.add_edge("fetch_link_content", "adapt_tweets_to_articles")
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

def run(
    handle_filter: Optional[list[str]] = None,
    max_age_hours: int = 24,
    config: str = DEFAULT_CONFIG,
    use_shared_cache: bool = False,
) -> dict:
    """
    Run the Twitter Layer 2 aggregation pipeline.

    Requires Layer 1 to have been run first (reads from cached tweets).

    Args:
        handle_filter: Optional list of Twitter handles to filter for.
                      If None, all active accounts from L1 are processed.
        max_age_hours: Maximum tweet age in hours. Tweets older than this
                      are dropped before LLM filtering. Default: 24.
        config: Configuration name (default: business_news).
        use_shared_cache: If True, reads from data/shared/twitter_raw_cache.json
                         instead of data/{config}/twitter_raw_cache.json.
                         Use this after running twitter_multi_orchestrator.

    Returns:
        Final state with aggregated content.
    """
    # Set active configuration
    set_config(config)

    debug_log("=" * 60)
    debug_log("STARTING TWITTER LAYER 2 (CONTENT AGGREGATION)")
    debug_log(f"CONFIG: {config}")
    if handle_filter:
        debug_log(f"HANDLE FILTER: {handle_filter}")
    debug_log(f"MAX AGE HOURS: {max_age_hours}")
    debug_log(f"USE SHARED CACHE: {use_shared_cache}")
    debug_log("=" * 60)

    # Reset cost tracker
    reset_cost_tracker()

    # Build and run graph
    with track_time("twitter_layer2_total"):
        app = build_graph()

        # Initialize empty state
        initial_state: TwitterAggregationState = {
            "handle_filter": handle_filter,
            "max_age_hours": max_age_hours,
            "use_shared_cache": use_shared_cache,
            "available_accounts": [],
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
    debug_log("LAYER 2 COMPLETE")
    cost_tracker.print_summary()
    debug_log("=" * 60)

    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run Twitter content aggregation (Twitter Layer 2)")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="Config to use (default: business_news)")
    parser.add_argument("--handle-filter", nargs="*", help="Filter for specific handles")
    parser.add_argument("--max-age-hours", type=int, default=24, help="Max tweet age in hours (default: 24)")
    parser.add_argument(
        "--use-shared-cache",
        action="store_true",
        help="Read from shared cache (data/shared/) instead of config-specific cache"
    )

    args = parser.parse_args()

    result = run(
        config=args.config,
        handle_filter=args.handle_filter,
        max_age_hours=args.max_age_hours,
        use_shared_cache=args.use_shared_cache,
    )

    # Print quick summary
    save_status = result.get("save_status", {})
    print(f"\nTwitter Layer 2 Complete")
    print(f"  JSON: {save_status.get('json_path', 'N/A')}")
    print(f"  CSV:  {save_status.get('csv_path', 'N/A')}")
    print(f"  Records: {save_status.get('record_count', 0)}")
