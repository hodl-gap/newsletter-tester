"""
Deduplication Orchestrator - Layer 3 Pipeline

This orchestrator deduplicates articles from Layer 2 outputs using:
1. Multi-source merging (RSS, HTML, Browser-Use, Twitter with URL dedup)
2. Semantic deduplication (embeddings + LLM for ambiguous cases)

Pipeline Flow:
    merge_pipeline_outputs -> generate_embeddings -> load_historical_embeddings ->
    compare_similarities -> llm_confirm_duplicates -> store_articles ->
    export_dedup_report

First Run Behavior:
    If database is empty, skips deduplication and seeds the DB with all articles.
"""

from typing import TypedDict

from langgraph.graph import StateGraph, START, END

from src.config import set_config, DEFAULT_CONFIG
from src.tracking import debug_log, reset_cost_tracker, cost_tracker

# Import node functions
from src.functions.merge_pipeline_outputs import merge_pipeline_outputs
from src.functions.generate_embeddings import generate_embeddings
from src.functions.load_historical_embeddings import load_historical_embeddings
from src.functions.compare_similarities import compare_similarities
from src.functions.llm_confirm_duplicates import llm_confirm_duplicates
from src.functions.store_articles import store_articles
from src.functions.export_dedup_report import export_dedup_report


# =============================================================================
# State Definition
# =============================================================================

class DeduplicationState(TypedDict):
    """
    State object passed between nodes in the deduplication pipeline.
    """
    # Input configuration
    lookback_hours: int
    input_sources: list[str]  # ["rss", "html", "browser_use", "twitter"]

    # From merge_pipeline_outputs
    articles_to_check: list[dict]
    merge_stats: dict

    # From generate_embeddings
    articles_with_embeddings: list[dict]

    # From load_historical_embeddings
    historical_articles: list[dict]
    is_first_run: bool

    # From compare_similarities
    unique_articles: list[dict]
    duplicate_articles: list[dict]
    ambiguous_pairs: list[dict]

    # From llm_confirm_duplicates
    confirmed_duplicates: list[dict]
    confirmed_unique: list[dict]

    # From store_articles
    stored_count: int
    final_unique: list[dict]

    # From export_dedup_report
    dedup_report: dict


# =============================================================================
# Graph Definition
# =============================================================================

def build_graph() -> StateGraph:
    """
    Build and return the deduplication LangGraph workflow.

    Returns:
        Compiled StateGraph ready to invoke.
    """
    # Initialize the graph with state schema
    graph = StateGraph(DeduplicationState)

    # Add nodes
    graph.add_node("merge_pipeline_outputs", merge_pipeline_outputs)
    graph.add_node("generate_embeddings", generate_embeddings)
    graph.add_node("load_historical_embeddings", load_historical_embeddings)
    graph.add_node("compare_similarities", compare_similarities)
    graph.add_node("llm_confirm_duplicates", llm_confirm_duplicates)
    graph.add_node("store_articles", store_articles)
    graph.add_node("export_dedup_report", export_dedup_report)

    # Define edges (linear pipeline)
    graph.add_edge(START, "merge_pipeline_outputs")
    graph.add_edge("merge_pipeline_outputs", "generate_embeddings")
    graph.add_edge("generate_embeddings", "load_historical_embeddings")
    graph.add_edge("load_historical_embeddings", "compare_similarities")
    graph.add_edge("compare_similarities", "llm_confirm_duplicates")
    graph.add_edge("llm_confirm_duplicates", "store_articles")
    graph.add_edge("store_articles", "export_dedup_report")
    graph.add_edge("export_dedup_report", END)

    # Compile the graph
    return graph.compile()


# =============================================================================
# Entry Point
# =============================================================================

def run(
    lookback_hours: int = 48,
    input_sources: list[str] = None,
    config: str = DEFAULT_CONFIG
) -> dict:
    """
    Run the deduplication pipeline.

    Args:
        lookback_hours: Number of hours to look back for historical articles.
                       Default: 48 (compare against last 2 days).
        input_sources: List of source types to include.
                       Default: ["rss", "html", "browser_use", "twitter"] (all sources).
                       Options: "rss", "html", "browser_use", "twitter"
        config: Configuration name (default: business_news).

    Returns:
        Final state with deduplication results.
    """
    # Set active configuration
    set_config(config)

    if input_sources is None:
        input_sources = ["rss", "html", "browser_use", "twitter"]

    debug_log("=" * 60)
    debug_log("STARTING DEDUPLICATION PIPELINE (LAYER 3)")
    debug_log(f"CONFIG: {config}")
    debug_log(f"LOOKBACK HOURS: {lookback_hours}")
    debug_log(f"INPUT SOURCES: {input_sources}")
    debug_log("=" * 60)

    # Reset cost tracker
    reset_cost_tracker()

    # Build and run graph
    app = build_graph()

    # Initialize empty state
    initial_state: DeduplicationState = {
        "lookback_hours": lookback_hours,
        "input_sources": input_sources,
        "articles_to_check": [],
        "merge_stats": {},
        "articles_with_embeddings": [],
        "historical_articles": [],
        "is_first_run": False,
        "unique_articles": [],
        "duplicate_articles": [],
        "ambiguous_pairs": [],
        "confirmed_duplicates": [],
        "confirmed_unique": [],
        "stored_count": 0,
        "final_unique": [],
        "dedup_report": {},
    }

    result = app.invoke(initial_state)

    # Print summary
    debug_log("=" * 60)
    debug_log("DEDUPLICATION PIPELINE COMPLETE")

    report = result.get("dedup_report", {})
    summary = report.get("summary", {})
    merge_stats = result.get("merge_stats", {})

    # Merge stats
    debug_log("  --- Merge Stats ---")
    for source_type, stats in merge_stats.get("by_source_type", {}).items():
        debug_log(f"    {source_type}: {stats.get('loaded', 0)} loaded, {stats.get('kept', 0)} kept")
    debug_log(f"  URL collisions:   {merge_stats.get('url_collisions', 0)}")

    # Dedup stats
    debug_log("  --- Dedup Stats ---")
    debug_log(f"  Total input:      {summary.get('total_input', 0)}")
    debug_log(f"  Unique kept:      {summary.get('unique_kept', 0)}")
    debug_log(f"  Duplicates found: {summary.get('duplicates_removed', 0)}")
    debug_log(f"    - URL exact:    {summary.get('url_duplicates', 0)}")
    debug_log(f"    - Semantic auto:{summary.get('semantic_auto_duplicates', 0)}")
    debug_log(f"    - Semantic LLM: {summary.get('semantic_llm_confirmed', 0)}")
    debug_log(f"  Stored to DB:     {summary.get('stored_to_db', 0)}")

    cost_tracker.print_summary()
    debug_log("=" * 60)

    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run deduplication pipeline (Layer 3)")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="Config to use (default: business_news)")
    parser.add_argument("--lookback-hours", type=int, default=48, help="Lookback hours for historical articles (default: 48)")
    parser.add_argument("--input-sources", nargs="*", default=["rss", "html", "browser_use", "twitter"],
                       help="Input sources to include (default: rss html browser_use twitter)")

    args = parser.parse_args()

    result = run(
        config=args.config,
        lookback_hours=args.lookback_hours,
        input_sources=args.input_sources
    )

    # Print output locations
    report = result.get("dedup_report", {})
    print(f"\nDeduplication complete!")
    print(f"  Report: data/{args.config}/dedup_report.json")
    print(f"  JSON:   data/{args.config}/merged_news_deduped.json")
    print(f"  CSV:    data/{args.config}/merged_news_deduped.csv")
    print(f"  Unique articles: {report.get('summary', {}).get('unique_kept', 0)}")
