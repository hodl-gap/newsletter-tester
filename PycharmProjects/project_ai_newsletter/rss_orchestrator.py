"""
RSS Orchestrator - Layer 1: Source Discovery (v2)

This orchestrator tests RSS feed availability for a list of URLs.
Pipeline: Load URLs -> Test Main RSS -> Test AI Category -> Agent Discovery -> Classify -> Save
"""

import json
from datetime import datetime
from pathlib import Path
from typing import TypedDict

from langgraph.graph import StateGraph, START, END

from src.functions.test_rss_preset import test_rss_preset, RSSTestResult
from src.functions.test_ai_category import test_ai_category, AIFeedResult
from src.functions.discover_rss_agent import discover_rss_agent, RSSDiscoveryResult
from src.functions.classify_feeds import classify_feeds, determine_recommended_feed
from src.tracking import track_time, cost_tracker, reset_cost_tracker, get_logger, debug_log


# =============================================================================
# State Definition
# =============================================================================

class FinalResult(TypedDict):
    url: str
    status: str  # "available", "paywalled", "unavailable"
    main_feed_url: str | None
    ai_feed_url: str | None
    is_ai_focused: bool
    recommended_feed: str  # "main_feed_url", "ai_feed_url", "none"
    recommended_feed_url: str | None  # The actual URL to use
    method: str  # "preset", "agent_search", "agent_browse"
    notes: str | None


class RSSDiscoveryState(TypedDict):
    input_urls: list[str]
    main_rss_results: list[RSSTestResult]
    ai_category_results: list[AIFeedResult]
    agent_results: list[RSSDiscoveryResult]
    classification: dict[str, bool]
    final_results: list[FinalResult]


# =============================================================================
# Node Functions
# =============================================================================

def load_urls(state: RSSDiscoveryState) -> dict:
    """Load URLs from input file."""
    with track_time("load_urls"):
        debug_log("[NODE: load_urls] Entering")

        input_path = Path("data/input_urls.json")
        with open(input_path) as f:
            data = json.load(f)

        urls = data.get("urls", [])
        debug_log(f"[NODE: load_urls] Loaded {len(urls)} URLs")
        debug_log(f"[NODE: load_urls] Output: {urls}")

        return {"input_urls": urls}


def test_main_rss(state: RSSDiscoveryState) -> dict:
    """Test main RSS paths for all URLs."""
    with track_time("test_main_rss"):
        debug_log("[NODE: test_main_rss] Entering")
        debug_log(f"[NODE: test_main_rss] Input: {len(state['input_urls'])} URLs")

        results = []
        for url in state["input_urls"]:
            result = test_rss_preset(url)
            results.append(result)

        available = sum(1 for r in results if r["status"] == "available")
        debug_log(f"[NODE: test_main_rss] Output: {available}/{len(results)} have main RSS")

        return {"main_rss_results": results}


def test_ai_category_feeds(state: RSSDiscoveryState) -> dict:
    """Test AI category RSS paths for all URLs."""
    with track_time("test_ai_category_feeds"):
        debug_log("[NODE: test_ai_category_feeds] Entering")
        debug_log(f"[NODE: test_ai_category_feeds] Input: {len(state['input_urls'])} URLs")

        results = []
        for url in state["input_urls"]:
            result = test_ai_category(url)
            results.append(result)

        available = sum(1 for r in results if r["status"] == "available")
        debug_log(f"[NODE: test_ai_category_feeds] Output: {available}/{len(results)} have AI category")

        return {"ai_category_results": results}


def normalize_url(url: str) -> str:
    """Normalize URL by stripping trailing slashes for consistent lookups."""
    return url.rstrip("/")


def discover_with_agent(state: RSSDiscoveryState) -> dict:
    """Use agent to discover RSS for URLs that failed both preset tests (and aren't paywalled)."""
    with track_time("discover_with_agent"):
        debug_log("[NODE: discover_with_agent] Entering")

        # Find URLs that failed both main RSS and AI category
        # Use normalized URLs for consistent lookups (preset tests strip trailing slashes)
        main_results_map = {normalize_url(r["url"]): r for r in state["main_rss_results"]}
        ai_results_map = {normalize_url(r["url"]): r for r in state["ai_category_results"]}

        failed_urls = []
        paywalled_urls = []

        for url in state["input_urls"]:
            normalized = normalize_url(url)
            main_status = main_results_map.get(normalized, {}).get("status")
            ai_status = ai_results_map.get(normalized, {}).get("status")

            # Skip if already found a feed
            if main_status == "available" or ai_status == "available":
                continue

            # Skip if already detected as paywalled (no point calling agent)
            if main_status == "paywalled" or ai_status == "paywalled":
                paywalled_urls.append(url)
                continue

            failed_urls.append(url)

        debug_log(f"[NODE: discover_with_agent] Input: {len(failed_urls)} failed URLs, {len(paywalled_urls)} paywalled (skipped)")

        if not failed_urls:
            debug_log("[NODE: discover_with_agent] No failed URLs to process, skipping agent")
            return {"agent_results": []}

        results = []
        for url in failed_urls:
            result = discover_rss_agent(url)
            results.append(result)

        debug_log(f"[NODE: discover_with_agent] Output: {len(results)} agent results")

        return {"agent_results": results}


def classify_all_feeds(state: RSSDiscoveryState) -> dict:
    """Classify all feeds as AI-focused or not using batch LLM call."""
    with track_time("classify_all_feeds"):
        debug_log("[NODE: classify_all_feeds] Entering")

        # Collect titles from main RSS results
        feed_titles = {}
        for r in state["main_rss_results"]:
            if r["status"] == "available" and r.get("article_titles"):
                feed_titles[r["url"]] = r["article_titles"]

        # Also add titles from agent results
        for r in state.get("agent_results", []):
            if r["status"] == "available" and r["url"] not in feed_titles:
                # Agent results don't have titles, so we mark as unknown
                feed_titles[r["url"]] = []

        debug_log(f"[NODE: classify_all_feeds] Input: {len(feed_titles)} feeds to classify")

        if not feed_titles:
            debug_log("[NODE: classify_all_feeds] No feeds to classify")
            return {"classification": {}}

        # Filter out feeds with no titles (can't classify without content)
        feeds_with_titles = {url: titles for url, titles in feed_titles.items() if titles}

        if not feeds_with_titles:
            debug_log("[NODE: classify_all_feeds] No feeds with titles to classify")
            return {"classification": {url: False for url in feed_titles.keys()}}

        classification = classify_feeds(feeds_with_titles)

        # Add back URLs that had no titles as non-AI-focused
        for url in feed_titles.keys():
            if url not in classification:
                classification[url] = False

        debug_log(f"[NODE: classify_all_feeds] Output: {classification}")

        return {"classification": classification}


def merge_results(state: RSSDiscoveryState) -> dict:
    """Merge all results into final output."""
    with track_time("merge_results"):
        debug_log("[NODE: merge_results] Entering")

        # Use normalized URLs for consistent lookups
        main_map = {normalize_url(r["url"]): r for r in state["main_rss_results"]}
        ai_map = {normalize_url(r["url"]): r for r in state["ai_category_results"]}
        agent_map = {normalize_url(r["url"]): r for r in state.get("agent_results", [])}
        classification = state.get("classification", {})

        final_results: list[FinalResult] = []

        for url in state["input_urls"]:
            normalized = normalize_url(url)
            main_r = main_map.get(normalized, {})
            ai_r = ai_map.get(normalized, {})
            agent_r = agent_map.get(normalized, {})

            # Determine main feed URL
            main_feed_url = None
            method = "preset"
            notes = None

            if main_r.get("status") == "available":
                main_feed_url = main_r.get("feed_url")
                notes = main_r.get("notes")
            elif agent_r:
                # Agent was called - capture its method and notes regardless of status
                method = agent_r.get("method", "agent_search")
                notes = agent_r.get("notes")
                if agent_r.get("status") == "available":
                    main_feed_url = agent_r.get("feed_url")

            # Determine AI feed URL
            ai_feed_url = ai_r.get("ai_feed_url") if ai_r.get("status") == "available" else None

            # Determine status - check for paywalled from any source
            if main_feed_url or ai_feed_url:
                status = "available"
            elif (main_r.get("status") == "paywalled" or
                  ai_r.get("status") == "paywalled" or
                  agent_r.get("status") == "paywalled"):
                status = "paywalled"
                # Use notes from whichever detected paywall first
                if main_r.get("status") == "paywalled" and not notes:
                    notes = main_r.get("notes")
                elif ai_r.get("status") == "paywalled" and not notes:
                    notes = ai_r.get("notes")
            else:
                status = "unavailable"

            # Get classification
            is_ai_focused = classification.get(url, False)

            # Determine recommended feed
            recommended_url, recommended_field = determine_recommended_feed(
                url, is_ai_focused, main_feed_url, ai_feed_url
            )

            final_results.append({
                "url": url,
                "status": status,
                "main_feed_url": main_feed_url,
                "ai_feed_url": ai_feed_url,
                "is_ai_focused": is_ai_focused,
                "recommended_feed": recommended_field,
                "recommended_feed_url": recommended_url,
                "method": method,
                "notes": notes,
            })

        debug_log(f"[NODE: merge_results] Output: {len(final_results)} final results")
        return {"final_results": final_results}


def save_results(state: RSSDiscoveryState) -> dict:
    """Save final results to JSON file."""
    with track_time("save_results"):
        debug_log("[NODE: save_results] Entering")

        results = state["final_results"]

        output = {
            "results": results,
            "timestamp": datetime.now().isoformat(),
            "total": len(results),
            "available": sum(1 for r in results if r["status"] == "available"),
            "paywalled": sum(1 for r in results if r["status"] == "paywalled"),
            "unavailable": sum(1 for r in results if r["status"] == "unavailable"),
            "ai_focused": sum(1 for r in results if r["is_ai_focused"]),
            "has_ai_category": sum(1 for r in results if r["ai_feed_url"]),
        }

        output_path = Path("data/rss_availability.json")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(output, f, indent=2)

        debug_log(f"[NODE: save_results] Saved to {output_path}")
        debug_log("[NODE: save_results] Summary:")
        debug_log(f"  - Total: {output['total']}")
        debug_log(f"  - Available: {output['available']}")
        debug_log(f"  - Paywalled: {output['paywalled']}")
        debug_log(f"  - Unavailable: {output['unavailable']}")
        debug_log(f"  - AI-focused: {output['ai_focused']}")
        debug_log(f"  - Has AI category: {output['has_ai_category']}")

        return {}


# =============================================================================
# Graph Definition
# =============================================================================

def build_graph() -> StateGraph:
    """Build and return the RSS discovery graph."""
    graph = StateGraph(RSSDiscoveryState)

    # Add nodes
    graph.add_node("load_urls", load_urls)
    graph.add_node("test_main_rss", test_main_rss)
    graph.add_node("test_ai_category_feeds", test_ai_category_feeds)
    graph.add_node("discover_with_agent", discover_with_agent)
    graph.add_node("classify_all_feeds", classify_all_feeds)
    graph.add_node("merge_results", merge_results)
    graph.add_node("save_results", save_results)

    # Define edges
    graph.add_edge(START, "load_urls")
    graph.add_edge("load_urls", "test_main_rss")
    graph.add_edge("test_main_rss", "test_ai_category_feeds")
    graph.add_edge("test_ai_category_feeds", "discover_with_agent")
    graph.add_edge("discover_with_agent", "classify_all_feeds")
    graph.add_edge("classify_all_feeds", "merge_results")
    graph.add_edge("merge_results", "save_results")
    graph.add_edge("save_results", END)

    return graph.compile()


# =============================================================================
# Entry Point
# =============================================================================

def run() -> dict:
    """Run the RSS discovery pipeline."""
    # Reset cost tracker for this run
    reset_cost_tracker()

    # Initialize logger at pipeline start
    get_logger()

    debug_log("=" * 60)
    debug_log("RSS Discovery Pipeline - Layer 1 (v2)")
    debug_log("=" * 60)

    app = build_graph()

    initial_state: RSSDiscoveryState = {
        "input_urls": [],
        "main_rss_results": [],
        "ai_category_results": [],
        "agent_results": [],
        "classification": {},
        "final_results": [],
    }

    result = app.invoke(initial_state)

    debug_log("=" * 60)
    debug_log("Pipeline Complete")
    debug_log("=" * 60)

    # Print cost summary
    cost_tracker.print_summary()

    return result


if __name__ == "__main__":
    run()
