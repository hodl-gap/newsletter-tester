"""
Twitter Layer 1 Orchestrator - Account Discovery

Validates Twitter account activity and caches scraped tweets for Layer 2.

Pipeline Flow:
    load_twitter_accounts -> fetch_twitter_content -> analyze_account_activity ->
    save_twitter_availability

Output:
    - data/twitter_availability.json (account status and metrics)
    - data/twitter_raw_cache.json (raw tweets for Layer 2)
"""

from typing import TypedDict, Optional

from langgraph.graph import StateGraph, START, END

from src.tracking import debug_log, reset_cost_tracker, cost_tracker, track_time

# Import node functions
from src.functions.load_twitter_accounts import load_twitter_accounts
from src.functions.fetch_twitter_content import fetch_twitter_content
from src.functions.analyze_account_activity import analyze_account_activity
from src.functions.save_twitter_availability import save_twitter_availability


# =============================================================================
# State Definition
# =============================================================================

class TwitterDiscoveryState(TypedDict):
    """
    State object passed between nodes in the Twitter discovery pipeline.
    """
    # Optional: filter for specific handles
    handle_filter: Optional[list[str]]

    # From load_twitter_accounts
    twitter_accounts: list[dict]
    twitter_settings: dict

    # From fetch_twitter_content
    raw_tweets: list[dict]

    # From analyze_account_activity
    activity_results: list[dict]

    # From save_twitter_availability
    save_status: dict


# =============================================================================
# Graph Definition
# =============================================================================

def build_graph() -> StateGraph:
    """
    Build and return the Twitter discovery LangGraph workflow.

    Returns:
        Compiled StateGraph ready to invoke.
    """
    # Initialize the graph with state schema
    graph = StateGraph(TwitterDiscoveryState)

    # Add nodes
    graph.add_node("load_twitter_accounts", load_twitter_accounts)
    graph.add_node("fetch_twitter_content", fetch_twitter_content)
    graph.add_node("analyze_account_activity", analyze_account_activity)
    graph.add_node("save_twitter_availability", save_twitter_availability)

    # Define edges (linear pipeline)
    graph.add_edge(START, "load_twitter_accounts")
    graph.add_edge("load_twitter_accounts", "fetch_twitter_content")
    graph.add_edge("fetch_twitter_content", "analyze_account_activity")
    graph.add_edge("analyze_account_activity", "save_twitter_availability")
    graph.add_edge("save_twitter_availability", END)

    # Compile the graph
    return graph.compile()


# =============================================================================
# Entry Point
# =============================================================================

def run(handle_filter: Optional[list[str]] = None) -> dict:
    """
    Run the Twitter Layer 1 discovery pipeline.

    Args:
        handle_filter: Optional list of Twitter handles to filter for.
                      If None, all configured accounts are processed.
                      Uses substring matching (e.g., "OpenAI" matches "@OpenAI")

    Returns:
        Final state with activity results and save status.
    """
    debug_log("=" * 60)
    debug_log("STARTING TWITTER LAYER 1 (ACCOUNT DISCOVERY)")
    if handle_filter:
        debug_log(f"HANDLE FILTER: {handle_filter}")
    debug_log("=" * 60)

    # Reset cost tracker (L1 has no LLM costs but track anyway)
    reset_cost_tracker()

    # Build and run graph
    with track_time("twitter_layer1_total"):
        app = build_graph()

        # Initialize empty state
        initial_state: TwitterDiscoveryState = {
            "handle_filter": handle_filter,
            "twitter_accounts": [],
            "twitter_settings": {},
            "raw_tweets": [],
            "activity_results": [],
            "save_status": {},
        }

        result = app.invoke(initial_state)

    # Print summary
    debug_log("=" * 60)
    debug_log("LAYER 1 COMPLETE")

    save_status = result.get("save_status", {})
    debug_log(f"Total accounts: {save_status.get('total_accounts', 0)}")
    debug_log(f"Active: {save_status.get('active_accounts', 0)}")
    debug_log(f"Inactive: {save_status.get('inactive_accounts', 0)}")
    debug_log(f"Cached tweets: {save_status.get('cached_tweets', 0)}")

    cost_tracker.print_summary()
    debug_log("=" * 60)

    return result


if __name__ == "__main__":
    result = run()

    # Print quick summary
    save_status = result.get("save_status", {})
    print(f"\nTwitter Layer 1 Complete")
    print(f"  Availability: {save_status.get('availability_path', 'N/A')}")
    print(f"  Cache: {save_status.get('cache_path', 'N/A')}")
    print(f"  Active accounts: {save_status.get('active_accounts', 0)}")
    print(f"  Inactive accounts: {save_status.get('inactive_accounts', 0)}")
    print(f"  Cached tweets: {save_status.get('cached_tweets', 0)}")
