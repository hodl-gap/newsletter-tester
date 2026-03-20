"""
Twitter Layer 1 Orchestrator - Account Discovery

Validates Twitter account activity and caches scraped tweets for Layer 2.

Supports two modes:
- Single-config: Scrapes accounts from one config, saves to data/{config}/
- Multi-config: Scrapes accounts from multiple configs (deduplicated),
                saves to data/shared/ for shared access

Pipeline Flow:
    load_twitter_accounts -> fetch_twitter_content -> analyze_account_activity ->
    save_twitter_availability

Output (single-config):
    - data/{config}/twitter_availability.json (account status and metrics)
    - data/{config}/twitter_raw_cache.json (raw tweets for Layer 2)

Output (multi-config):
    - data/shared/twitter_raw_cache.json (shared cache for all configs)

Usage:
    # Single-config (existing behavior)
    python twitter_layer1_orchestrator.py --config=business_news

    # Multi-config (consolidated scraping)
    python twitter_layer1_orchestrator.py --configs business_news ai_tips

    # Multi-config with full pipeline (L1 + L2 for each config)
    python twitter_layer1_orchestrator.py --configs business_news ai_tips --run-all
"""

from typing import TypedDict, Optional

from langgraph.graph import StateGraph, START, END

from src.config import set_config, DEFAULT_CONFIG
from src.tracking import debug_log, reset_cost_tracker, cost_tracker, track_time

# Import node functions
from src.functions.load_twitter_accounts import (
    load_twitter_accounts,
    load_multi_config_twitter_accounts_node,
)
from src.functions.fetch_twitter_content import fetch_twitter_content
from src.functions.analyze_account_activity import analyze_account_activity
from src.functions.save_twitter_availability import (
    save_twitter_availability,
    save_shared_twitter_cache,
)


# =============================================================================
# State Definitions
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


class TwitterMultiConfigState(TypedDict):
    """
    State object for multi-config Twitter scraping pipeline.
    """
    # Input: list of config names to scrape
    configs: list[str]

    # Optional: filter for specific handles
    handle_filter: Optional[list[str]]

    # From load_multi_config_twitter_accounts_node
    twitter_accounts: list[dict]
    config_handle_map: dict[str, set[str]]
    twitter_settings: dict

    # From fetch_twitter_content
    raw_tweets: list[dict]

    # From analyze_account_activity
    activity_results: list[dict]

    # From save_shared_twitter_cache
    save_status: dict


# =============================================================================
# Graph Definitions
# =============================================================================

def build_graph() -> StateGraph:
    """
    Build and return the single-config Twitter discovery workflow.

    Returns:
        Compiled StateGraph ready to invoke.
    """
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

    return graph.compile()


def build_multi_config_graph() -> StateGraph:
    """
    Build and return the multi-config Twitter scraping workflow.

    Uses shared cache instead of config-specific cache.

    Returns:
        Compiled StateGraph ready to invoke.
    """
    graph = StateGraph(TwitterMultiConfigState)

    # Add nodes
    graph.add_node("load_multi_config_accounts", load_multi_config_twitter_accounts_node)
    graph.add_node("fetch_twitter_content", fetch_twitter_content)
    graph.add_node("analyze_account_activity", analyze_account_activity)
    graph.add_node("save_shared_twitter_cache", save_shared_twitter_cache)

    # Define edges (linear pipeline)
    graph.add_edge(START, "load_multi_config_accounts")
    graph.add_edge("load_multi_config_accounts", "fetch_twitter_content")
    graph.add_edge("fetch_twitter_content", "analyze_account_activity")
    graph.add_edge("analyze_account_activity", "save_shared_twitter_cache")
    graph.add_edge("save_shared_twitter_cache", END)

    return graph.compile()


# =============================================================================
# Entry Points
# =============================================================================

def run(
    handle_filter: Optional[list[str]] = None,
    config: str = DEFAULT_CONFIG,
) -> dict:
    """
    Run the Twitter Layer 1 discovery pipeline for a single config.

    Args:
        handle_filter: Optional list of Twitter handles to filter for.
                      If None, all configured accounts are processed.
                      Uses substring matching (e.g., "OpenAI" matches "@OpenAI")
        config: Configuration name (default: business_news).

    Returns:
        Final state with activity results and save status.
    """
    # Set active configuration
    set_config(config)

    debug_log("=" * 60)
    debug_log("STARTING TWITTER LAYER 1 (ACCOUNT DISCOVERY)")
    debug_log(f"CONFIG: {config}")
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


def run_multi(
    configs: list[str],
    handle_filter: Optional[list[str]] = None,
) -> dict:
    """
    Run consolidated Twitter L1 scraping for multiple configs.

    Each unique handle is scraped only once. Results are saved to
    data/shared/twitter_raw_cache.json for shared access.

    Args:
        configs: List of config names (e.g., ["business_news", "ai_tips"])
        handle_filter: Optional filter for specific handles (substring match)

    Returns:
        Final state with save status
    """
    debug_log("=" * 60)
    debug_log("STARTING TWITTER LAYER 1 (MULTI-CONFIG)")
    debug_log(f"CONFIGS: {configs}")
    if handle_filter:
        debug_log(f"HANDLE FILTER: {handle_filter}")
    debug_log("=" * 60)

    # Reset cost tracker
    reset_cost_tracker()

    # Build and run graph
    with track_time("twitter_layer1_multi_total"):
        app = build_multi_config_graph()

        # Initialize state
        initial_state: TwitterMultiConfigState = {
            "configs": configs,
            "handle_filter": handle_filter,
            "twitter_accounts": [],
            "config_handle_map": {},
            "twitter_settings": {},
            "raw_tweets": [],
            "activity_results": [],
            "save_status": {},
        }

        result = app.invoke(initial_state)

    # Print summary
    debug_log("=" * 60)
    debug_log("MULTI-CONFIG SCRAPING COMPLETE")

    save_status = result.get("save_status", {})
    debug_log(f"Total handles: {save_status.get('total_handles', 0)}")
    debug_log(f"Cached tweets: {save_status.get('cached_tweets', 0)}")
    debug_log(f"Configs covered: {save_status.get('configs_covered', [])}")
    debug_log(f"Cache path: {save_status.get('cache_path', 'N/A')}")

    cost_tracker.print_summary()
    debug_log("=" * 60)

    return result


def run_all(
    configs: list[str],
    handle_filter: Optional[list[str]] = None,
    max_age_hours: Optional[int] = None,
) -> dict:
    """
    Run full multi-config Twitter pipeline: consolidated L1 + L2 for each config.

    Steps:
    1. Run consolidated L1 scraping (all handles scraped once)
    2. For each config, run Twitter L2 with use_shared_cache=True

    Args:
        configs: List of config names (e.g., ["business_news", "ai_tips"])
        handle_filter: Optional filter for specific handles (L1 only)
        max_age_hours: Tweet age cutoff for L2 filtering (uses config default if None)

    Returns:
        Dict with:
            - l1_result: L1 scraping result
            - l2_results: Dict mapping config -> L2 result
    """
    import twitter_layer2_orchestrator

    debug_log("=" * 60)
    debug_log("STARTING FULL MULTI-CONFIG TWITTER PIPELINE")
    debug_log(f"CONFIGS: {configs}")
    debug_log("=" * 60)

    # Step 1: Consolidated L1 scraping
    debug_log("\n" + "=" * 40)
    debug_log("PHASE 1: CONSOLIDATED L1 SCRAPING")
    debug_log("=" * 40)

    l1_result = run_multi(configs=configs, handle_filter=handle_filter)

    # Step 2: Run L2 for each config
    l2_results = {}

    for config in configs:
        debug_log("\n" + "=" * 40)
        debug_log(f"PHASE 2: L2 FOR CONFIG '{config}'")
        debug_log("=" * 40)

        # Determine max_age_hours for this config
        l2_max_age = max_age_hours if max_age_hours is not None else 24

        try:
            l2_result = twitter_layer2_orchestrator.run(
                config=config,
                use_shared_cache=True,
                max_age_hours=l2_max_age,
            )
            l2_results[config] = l2_result
        except Exception as e:
            debug_log(f"Error running L2 for config '{config}': {e}", "error")
            l2_results[config] = {"error": str(e)}

    # Print final summary
    debug_log("\n" + "=" * 60)
    debug_log("FULL PIPELINE COMPLETE")
    debug_log("=" * 60)

    l1_status = l1_result.get("save_status", {})
    debug_log(f"L1: Scraped {l1_status.get('total_handles', 0)} handles, "
              f"cached {l1_status.get('cached_tweets', 0)} tweets")

    for config, l2_result in l2_results.items():
        if "error" in l2_result:
            debug_log(f"L2 [{config}]: ERROR - {l2_result['error']}")
        else:
            l2_status = l2_result.get("save_status", {})
            debug_log(f"L2 [{config}]: {l2_status.get('record_count', 0)} articles saved")

    return {
        "l1_result": l1_result,
        "l2_results": l2_results,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Run Twitter account discovery (Twitter Layer 1)"
    )

    # Single vs multi-config (mutually exclusive)
    config_group = parser.add_mutually_exclusive_group(required=True)
    config_group.add_argument(
        "--config",
        help="Single config to use (e.g., business_news)"
    )
    config_group.add_argument(
        "--configs",
        nargs="+",
        help="Multiple configs for consolidated scraping (e.g., business_news ai_tips)"
    )

    parser.add_argument(
        "--handle-filter",
        nargs="*",
        help="Filter for specific handles"
    )
    parser.add_argument(
        "--run-all",
        action="store_true",
        help="Run full pipeline (L1 + L2 for each config). Only valid with --configs."
    )
    parser.add_argument(
        "--max-age-hours",
        type=int,
        default=None,
        help="Max tweet age in hours for L2 (only with --run-all)"
    )

    args = parser.parse_args()

    if args.config:
        # Single-config mode
        result = run(config=args.config, handle_filter=args.handle_filter)

        save_status = result.get("save_status", {})
        print(f"\nTwitter Layer 1 Complete")
        print(f"  Availability: {save_status.get('availability_path', 'N/A')}")
        print(f"  Cache: {save_status.get('cache_path', 'N/A')}")
        print(f"  Active accounts: {save_status.get('active_accounts', 0)}")
        print(f"  Inactive accounts: {save_status.get('inactive_accounts', 0)}")
        print(f"  Cached tweets: {save_status.get('cached_tweets', 0)}")

    elif args.configs:
        if args.run_all:
            # Multi-config with full pipeline
            result = run_all(
                configs=args.configs,
                handle_filter=args.handle_filter,
                max_age_hours=args.max_age_hours,
            )

            print("\n" + "=" * 60)
            print("MULTI-CONFIG TWITTER PIPELINE COMPLETE")
            print("=" * 60)

            l1_status = result["l1_result"].get("save_status", {})
            print(f"\nL1 (Shared Cache):")
            print(f"  Path: {l1_status.get('cache_path', 'N/A')}")
            print(f"  Handles: {l1_status.get('total_handles', 0)}")
            print(f"  Tweets: {l1_status.get('cached_tweets', 0)}")

            print(f"\nL2 Results:")
            for config, l2_result in result["l2_results"].items():
                if "error" in l2_result:
                    print(f"  [{config}] ERROR: {l2_result['error']}")
                else:
                    l2_status = l2_result.get("save_status", {})
                    print(f"  [{config}] {l2_status.get('record_count', 0)} articles")
                    print(f"    JSON: {l2_status.get('json_path', 'N/A')}")
        else:
            # Multi-config L1 only
            result = run_multi(
                configs=args.configs,
                handle_filter=args.handle_filter,
            )

            save_status = result.get("save_status", {})
            print(f"\nTwitter Layer 1 (Multi-Config) Complete")
            print(f"  Cache: {save_status.get('cache_path', 'N/A')}")
            print(f"  Handles: {save_status.get('total_handles', 0)}")
            print(f"  Tweets: {save_status.get('cached_tweets', 0)}")
            print(f"  Configs: {save_status.get('configs_covered', [])}")
            print(f"\nNext step: Run L2 for each config with --use-shared-cache flag")
