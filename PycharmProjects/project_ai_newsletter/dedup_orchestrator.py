"""
Deduplication Orchestrator - Layer 3 Pipeline

This orchestrator deduplicates articles from Layer 2 output using:
1. URL deduplication (exact match against historical DB)
2. Semantic deduplication (embeddings + LLM for ambiguous cases)

Pipeline Flow:
    load_new_articles -> generate_embeddings -> load_historical_embeddings ->
    compare_similarities -> llm_confirm_duplicates -> store_articles ->
    export_dedup_report

First Run Behavior:
    If database is empty, skips deduplication and seeds the DB with all articles.
"""

import json
from typing import TypedDict, Optional
from pathlib import Path

from langgraph.graph import StateGraph, START, END

from src.tracking import debug_log, reset_cost_tracker, cost_tracker

# Import node functions
from src.functions.generate_embeddings import generate_embeddings
from src.functions.load_historical_embeddings import load_historical_embeddings
from src.functions.compare_similarities import compare_similarities
from src.functions.llm_confirm_duplicates import llm_confirm_duplicates
from src.functions.store_articles import store_articles
from src.functions.export_dedup_report import export_dedup_report


# =============================================================================
# Configuration
# =============================================================================

DATA_DIR = Path(__file__).parent / "data"
INPUT_JSON_PATH = DATA_DIR / "aggregated_news.json"


# =============================================================================
# State Definition
# =============================================================================

class DeduplicationState(TypedDict):
    """
    State object passed between nodes in the deduplication pipeline.
    """
    # Input configuration
    lookback_hours: int

    # From load_new_articles
    articles_to_check: list[dict]

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
# Node Functions
# =============================================================================

def load_new_articles(state: dict) -> dict:
    """
    Load new articles from Layer 2 output.

    Reads aggregated_news.json and prepares articles for deduplication.

    Args:
        state: Pipeline state

    Returns:
        Dict with 'articles_to_check': List of articles
    """
    debug_log("[NODE: load_new_articles] Entering")

    if not INPUT_JSON_PATH.exists():
        debug_log(f"[NODE: load_new_articles] Input file not found: {INPUT_JSON_PATH}", "error")
        return {"articles_to_check": []}

    with open(INPUT_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    articles = data.get("articles", [])

    debug_log(f"[NODE: load_new_articles] Loaded {len(articles)} articles from {INPUT_JSON_PATH}")

    return {"articles_to_check": articles}


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
    graph.add_node("load_new_articles", load_new_articles)
    graph.add_node("generate_embeddings", generate_embeddings)
    graph.add_node("load_historical_embeddings", load_historical_embeddings)
    graph.add_node("compare_similarities", compare_similarities)
    graph.add_node("llm_confirm_duplicates", llm_confirm_duplicates)
    graph.add_node("store_articles", store_articles)
    graph.add_node("export_dedup_report", export_dedup_report)

    # Define edges (linear pipeline)
    graph.add_edge(START, "load_new_articles")
    graph.add_edge("load_new_articles", "generate_embeddings")
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

def run(lookback_hours: int = 48) -> dict:
    """
    Run the deduplication pipeline.

    Args:
        lookback_hours: Number of hours to look back for historical articles.
                       Default: 48 (compare against last 2 days).

    Returns:
        Final state with deduplication results.
    """
    debug_log("=" * 60)
    debug_log("STARTING DEDUPLICATION PIPELINE (LAYER 3)")
    debug_log(f"LOOKBACK HOURS: {lookback_hours}")
    debug_log("=" * 60)

    # Reset cost tracker
    reset_cost_tracker()

    # Build and run graph
    app = build_graph()

    # Initialize empty state
    initial_state: DeduplicationState = {
        "lookback_hours": lookback_hours,
        "articles_to_check": [],
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
    result = run()

    # Print output locations
    report = result.get("dedup_report", {})
    print(f"\nDeduplication complete!")
    print(f"  Report: data/dedup_report.json")
    print(f"  JSON:   data/aggregated_news_deduped.json")
    print(f"  CSV:    data/aggregated_news_deduped.csv")
    print(f"  Unique articles: {report.get('summary', {}).get('unique_kept', 0)}")
