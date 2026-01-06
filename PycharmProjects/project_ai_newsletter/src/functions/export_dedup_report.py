"""
Export Deduplication Report Node

Generates a comprehensive report of deduplication results and exports
deduplicated articles to JSON and CSV files.
"""

import json
import csv
from datetime import datetime
from pathlib import Path

from src.tracking import debug_log, track_time, cost_tracker


# Output paths
DATA_DIR = Path(__file__).parent.parent.parent / "data"
DEDUP_JSON_PATH = DATA_DIR / "aggregated_news_deduped.json"
DEDUP_CSV_PATH = DATA_DIR / "aggregated_news_deduped.csv"
REPORT_PATH = DATA_DIR / "dedup_report.json"


def export_dedup_report(state: dict) -> dict:
    """
    Generate and export deduplication report.

    Creates:
    - dedup_report.json: Statistics and duplicate details
    - aggregated_news_deduped.json: Deduplicated articles
    - aggregated_news_deduped.csv: CSV format

    Args:
        state: Pipeline state with:
            - 'final_unique': Unique articles to export
            - 'confirmed_duplicates': Duplicate articles (for report)
            - 'stored_count': Number stored to DB
            - 'is_first_run': Whether this was a seeding run
            - 'articles_to_check': Original input articles

    Returns:
        Dict with 'dedup_report': Report summary
    """
    with track_time("export_dedup_report"):
        debug_log("[NODE: export_dedup_report] Entering")

        final_unique = state.get("final_unique", [])
        confirmed_duplicates = state.get("confirmed_duplicates", [])
        stored_count = state.get("stored_count", 0)
        is_first_run = state.get("is_first_run", False)
        articles_to_check = state.get("articles_to_check", [])

        # Count dedup types
        url_dup_count = state.get("url_duplicates_dropped", 0)
        auto_dup_count = len([d for d in confirmed_duplicates if not d.get("llm_confirmed")])
        llm_dup_count = len([d for d in confirmed_duplicates if d.get("llm_confirmed")])

        # Build report
        report = {
            "timestamp": datetime.now().isoformat(),
            "is_first_run": is_first_run,
            "summary": {
                "total_input": len(articles_to_check),
                "unique_kept": len(final_unique),
                "duplicates_removed": len(confirmed_duplicates),
                "url_duplicates": url_dup_count,
                "semantic_auto_duplicates": auto_dup_count,
                "semantic_llm_confirmed": llm_dup_count,
                "stored_to_db": stored_count,
            },
            "cost": {
                "total_cost": f"${cost_tracker.total_cost:.4f}",
                "input_tokens": cost_tracker.total_input_tokens,
                "output_tokens": cost_tracker.total_output_tokens,
                "llm_calls": cost_tracker.call_count,
            },
            "duplicates": []
        }

        # Add duplicate details
        for dup in confirmed_duplicates:
            article = dup.get("article", dup)
            duplicate_of = dup.get("duplicate_of", {})

            report["duplicates"].append({
                "removed_url": article.get("url", article.get("link", "")),
                "removed_title": article.get("title", ""),
                "duplicate_of_url": duplicate_of.get("url", duplicate_of.get("link", "")),
                "duplicate_of_title": duplicate_of.get("title", ""),
                "similarity": dup.get("similarity"),
                "dedup_type": "semantic_llm" if dup.get("llm_confirmed") else "semantic_auto",
                "reason": dup.get("llm_reason", "Auto-detected duplicate")
            })

        # Save report
        DATA_DIR.mkdir(parents=True, exist_ok=True)

        with open(REPORT_PATH, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        debug_log(f"[NODE: export_dedup_report] Saved report to {REPORT_PATH}")

        # Save deduplicated articles JSON
        _save_deduped_json(final_unique, report)

        # Save deduplicated articles CSV
        _save_deduped_csv(final_unique)

        debug_log(f"[NODE: export_dedup_report] Exported {len(final_unique)} unique articles")

        return {"dedup_report": report}


def _save_deduped_json(articles: list[dict], report: dict):
    """Save deduplicated articles to JSON."""
    # Clean articles (remove embedding)
    clean_articles = []
    for article in articles:
        clean = {k: v for k, v in article.items() if k != "embedding"}
        clean_articles.append(clean)

    output = {
        "metadata": {
            "timestamp": report["timestamp"],
            "total_articles": len(clean_articles),
            "dedup_summary": report["summary"],
            "cost": report["cost"],
        },
        "articles": clean_articles
    }

    with open(DEDUP_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    debug_log(f"[NODE: export_dedup_report] Saved JSON to {DEDUP_JSON_PATH}")


def _save_deduped_csv(articles: list[dict]):
    """Save deduplicated articles to CSV."""
    if not articles:
        return

    # Define column order
    columns = ["date", "source", "region", "category", "layer", "title", "contents", "url"]

    with open(DEDUP_CSV_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()

        for article in articles:
            # Map fields to expected column names
            row = {
                "date": article.get("date", article.get("pub_date", "")),
                "source": article.get("source", article.get("source_name", "")),
                "region": article.get("region", ""),
                "category": article.get("category", ""),
                "layer": article.get("layer", ""),
                "title": article.get("title", ""),
                "contents": article.get("contents", article.get("summary", "")),
                "url": article.get("url", article.get("link", "")),
            }
            writer.writerow(row)

    debug_log(f"[NODE: export_dedup_report] Saved CSV to {DEDUP_CSV_PATH}")
