"""
Layer 0 Orchestrator - Source Quality Assessment

This orchestrator assesses source credibility before Layer 1 (RSS Discovery).
Uses web search to gather reputation signals (Wikipedia, ownership, mentions)
rather than directly scraping websites.

Pipeline: Load URLs -> Fetch Source Reputation -> Assess Credibility -> Save Quality Results
"""

import json
from datetime import datetime
from pathlib import Path
from typing import TypedDict

from langgraph.graph import StateGraph, START, END

from src.config import set_config, DEFAULT_CONFIG, get_input_urls_path, get_data_dir
from src.functions.fetch_source_reputation import fetch_source_reputation, SourceReputation
from src.functions.assess_credibility import assess_credibility, CredibilityAssessment
from src.tracking import track_time, cost_tracker, reset_cost_tracker, get_logger, debug_log


# =============================================================================
# State Definition
# =============================================================================

class Layer0State(TypedDict):
    url_filter: list[str] | None  # Optional filter for URLs (substring match)
    input_urls: list[str]
    source_reputation: list[SourceReputation]
    assessments: list[CredibilityAssessment]


# =============================================================================
# Node Functions
# =============================================================================

def load_urls(state: Layer0State) -> dict:
    """Load URLs from input file."""
    with track_time("load_urls"):
        debug_log("[NODE: load_urls] Entering")

        input_path = get_input_urls_path()
        with open(input_path) as f:
            data = json.load(f)

        urls = data.get("urls", [])
        debug_log(f"[NODE: load_urls] Loaded {len(urls)} URLs from file")

        # Apply URL filter if specified
        url_filter = state.get("url_filter")
        if url_filter:
            debug_log(f"[NODE: load_urls] Applying URL filter: {url_filter}")
            filtered_urls = [
                url for url in urls
                if any(f.lower() in url.lower() for f in url_filter)
            ]
            debug_log(f"[NODE: load_urls] Filtered to {len(filtered_urls)} URLs")
            urls = filtered_urls

        debug_log(f"[NODE: load_urls] Output: {len(urls)} URLs")

        return {"input_urls": urls}


def fetch_all_source_reputation(state: Layer0State) -> dict:
    """Fetch reputation information for all sources using web search."""
    with track_time("fetch_all_source_reputation"):
        debug_log("[NODE: fetch_all_source_reputation] Entering")
        debug_log(f"[NODE: fetch_all_source_reputation] Input: {len(state['input_urls'])} URLs")

        results = []
        total = len(state["input_urls"])

        for i, url in enumerate(state["input_urls"]):
            debug_log(f"[NODE: fetch_all_source_reputation] Processing {i+1}/{total}: {url}")
            result = fetch_source_reputation(url)
            results.append(result)

        wiki_count = sum(1 for r in results if r.get("wikipedia_found"))
        debug_log(f"[NODE: fetch_all_source_reputation] Output: {len(results)} results, {wiki_count} with Wikipedia")

        return {"source_reputation": results}


def save_quality_results(state: Layer0State) -> dict:
    """Save quality assessment results to JSON file."""
    with track_time("save_quality_results"):
        debug_log("[NODE: save_quality_results] Entering")

        assessments = state.get("assessments", [])
        output_path = get_data_dir() / "source_quality.json"

        # Build results with reputation info
        reputation_map = {s["url"]: s for s in state.get("source_reputation", [])}

        results = []
        for assessment in assessments:
            url = assessment["url"]
            reputation = reputation_map.get(url, {})

            results.append({
                "url": url,
                "domain": reputation.get("domain", ""),
                "publication_name": reputation.get("publication_name", ""),
                "source_quality": assessment["source_quality"],
                "reason": assessment["reason"],
                "wikipedia_found": reputation.get("wikipedia_found", False),
            })

        # Calculate stats
        quality_count = sum(1 for r in results if r["source_quality"] == "quality")
        crude_count = sum(1 for r in results if r["source_quality"] == "crude")
        wiki_count = sum(1 for r in results if r.get("wikipedia_found"))

        output = {
            "results": results,
            "timestamp": datetime.now().isoformat(),
            "total": len(results),
            "quality": quality_count,
            "crude": crude_count,
            "with_wikipedia": wiki_count,
        }

        with open(output_path, "w") as f:
            json.dump(output, f, indent=2)

        debug_log(f"[NODE: save_quality_results] Saved to {output_path}")
        debug_log("[NODE: save_quality_results] Summary:")
        debug_log(f"  - Total: {output['total']}")
        debug_log(f"  - Quality: {output['quality']}")
        debug_log(f"  - Crude: {output['crude']}")
        debug_log(f"  - With Wikipedia: {output['with_wikipedia']}")

        return {}


# =============================================================================
# Graph Definition
# =============================================================================

def build_graph() -> StateGraph:
    """Build and return the Layer 0 quality assessment graph."""
    graph = StateGraph(Layer0State)

    # Add nodes
    graph.add_node("load_urls", load_urls)
    graph.add_node("fetch_all_source_reputation", fetch_all_source_reputation)
    graph.add_node("assess_credibility", assess_credibility)
    graph.add_node("save_quality_results", save_quality_results)

    # Define edges
    graph.add_edge(START, "load_urls")
    graph.add_edge("load_urls", "fetch_all_source_reputation")
    graph.add_edge("fetch_all_source_reputation", "assess_credibility")
    graph.add_edge("assess_credibility", "save_quality_results")
    graph.add_edge("save_quality_results", END)

    return graph.compile()


# =============================================================================
# Entry Point
# =============================================================================

def run(url_filter: list[str] | None = None, config: str = DEFAULT_CONFIG) -> dict:
    """
    Run the Layer 0 source quality assessment pipeline.

    Args:
        url_filter: Optional list of substrings to filter URLs.
                   Only URLs containing any of these substrings will be processed.
        config: Configuration name (default: business_news).

    Returns:
        Final pipeline state.
    """
    # Set active configuration
    set_config(config)

    # Reset cost tracker for this run
    reset_cost_tracker()

    # Initialize logger at pipeline start
    get_logger()

    debug_log("=" * 60)
    debug_log("Layer 0: Source Quality Assessment (Search-Based)")
    debug_log(f"CONFIG: {config}")
    if url_filter:
        debug_log(f"URL FILTER: {url_filter}")
    debug_log("=" * 60)

    app = build_graph()

    initial_state: Layer0State = {
        "url_filter": url_filter,
        "input_urls": [],
        "source_reputation": [],
        "assessments": [],
    }

    result = app.invoke(initial_state)

    debug_log("=" * 60)
    debug_log("Pipeline Complete")
    debug_log("=" * 60)

    # Print cost summary
    cost_tracker.print_summary()

    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run Layer 0 source quality assessment")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="Config to use (default: business_news)")
    parser.add_argument("--url-filter", nargs="*", help="Filter for specific URLs")

    args = parser.parse_args()

    result = run(config=args.config, url_filter=args.url_filter)

    # Print quick summary
    assessments = result.get("assessments", [])
    quality_count = sum(1 for a in assessments if a.get("source_quality") == "quality")
    crude_count = sum(1 for a in assessments if a.get("source_quality") == "crude")
    print(f"\nLayer 0 Complete")
    print(f"  Output: data/{args.config}/source_quality.json")
    print(f"  Total assessed: {len(assessments)}")
    print(f"  Quality: {quality_count}")
    print(f"  Crude: {crude_count}")
