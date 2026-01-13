#!/usr/bin/env python3
"""
RSS Fetch Orchestrator - Lightweight RSS Fetcher

Fetches RSS feeds and caches raw articles WITHOUT LLM processing.
Designed to run frequently (every 1-3 hours) to capture all articles
from high-frequency feeds.

Pipeline Flow:
    load_available_feeds -> fetch_rss_content -> save_rss_cache

Usage:
    python rss_fetch_orchestrator.py --config business_news
    python rss_fetch_orchestrator.py --configs business_news ai_tips
"""

import argparse
from typing import TypedDict, Optional

from langgraph.graph import StateGraph, START, END

from src.config import set_config, DEFAULT_CONFIG
from src.tracking import debug_log

# Import node functions
from src.functions.load_available_feeds import load_available_feeds
from src.functions.fetch_rss_content import fetch_rss_content
from src.functions.save_rss_cache import save_rss_cache


class RSSFetchState(TypedDict):
    """State object for RSS fetch pipeline."""
    source_filter: Optional[list[str]]
    available_feeds: list[dict]
    raw_articles: list[dict]
    cache_status: dict


def build_graph() -> StateGraph:
    """Build the RSS fetch pipeline graph."""
    graph = StateGraph(RSSFetchState)

    graph.add_node("load_available_feeds", load_available_feeds)
    graph.add_node("fetch_rss_content", fetch_rss_content)
    graph.add_node("save_rss_cache", save_rss_cache)

    graph.add_edge(START, "load_available_feeds")
    graph.add_edge("load_available_feeds", "fetch_rss_content")
    graph.add_edge("fetch_rss_content", "save_rss_cache")
    graph.add_edge("save_rss_cache", END)

    return graph.compile()


def run(
    config: str = DEFAULT_CONFIG,
    source_filter: Optional[list[str]] = None,
) -> dict:
    """
    Run the RSS fetch pipeline for a single config.

    Args:
        config: Configuration name (default: business_news)
        source_filter: Optional list of source names/URLs to filter for

    Returns:
        Final state with cache status
    """
    set_config(config)

    debug_log("=" * 60)
    debug_log("STARTING RSS FETCH PIPELINE")
    debug_log(f"CONFIG: {config}")
    if source_filter:
        debug_log(f"SOURCE FILTER: {source_filter}")
    debug_log("=" * 60)

    app = build_graph()

    initial_state: RSSFetchState = {
        "source_filter": source_filter,
        "available_feeds": [],
        "raw_articles": [],
        "cache_status": {},
    }

    result = app.invoke(initial_state)

    debug_log("=" * 60)
    debug_log("RSS FETCH COMPLETE")
    cache_status = result.get("cache_status", {})
    debug_log(f"New articles: {cache_status.get('new_articles', 0)}")
    debug_log(f"Total cached: {cache_status.get('total_articles', 0)}")
    debug_log(f"Duplicates skipped: {cache_status.get('duplicates_skipped', 0)}")
    debug_log("=" * 60)

    return result


def run_multi(configs: list[str]) -> dict:
    """
    Run RSS fetch for multiple configs.

    Args:
        configs: List of configuration names

    Returns:
        Dict with results per config
    """
    results = {}
    for config in configs:
        print(f"\n{'='*60}")
        print(f"Fetching RSS for config: {config}")
        print("=" * 60)
        results[config] = run(config=config)

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch RSS feeds and cache articles")
    parser.add_argument("--config", help="Single config to fetch")
    parser.add_argument("--configs", nargs="+", help="Multiple configs to fetch")
    parser.add_argument("--source-filter", nargs="*", help="Filter for specific sources")

    args = parser.parse_args()

    if args.configs:
        results = run_multi(args.configs)
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        for config, result in results.items():
            status = result.get("cache_status", {})
            print(f"  {config}: +{status.get('new_articles', 0)} new, {status.get('total_articles', 0)} total")
    else:
        config = args.config or DEFAULT_CONFIG
        result = run(config=config, source_filter=args.source_filter)
        status = result.get("cache_status", {})
        print(f"\nCache updated: +{status.get('new_articles', 0)} new articles")
        print(f"Total in cache: {status.get('total_articles', 0)}")
