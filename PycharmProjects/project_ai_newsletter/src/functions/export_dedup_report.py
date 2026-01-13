"""
Export Deduplication Report Node

Generates a comprehensive report of deduplication results and exports
deduplicated articles to JSON and CSV files.
"""

import json
import csv
from datetime import datetime, timedelta
from pathlib import Path

from src.config import get_data_dir, get_config
from src.tracking import debug_log, track_time, cost_tracker
from src.database import ArticleDatabase


def _get_output_paths() -> tuple[Path, Path, Path]:
    """Get output paths for dedup report files."""
    data_dir = get_data_dir()
    return (
        data_dir / "merged_news_deduped.json",
        data_dir / "merged_news_deduped.csv",
        data_dir / "dedup_report.json",
    )


def export_dedup_report(state: dict) -> dict:
    """
    Generate and export deduplication report.

    Creates:
    - dedup_report.json: Statistics and duplicate details
    - merged_news_deduped.json: Deduplicated articles
    - merged_news_deduped.csv: CSV format

    Args:
        state: Pipeline state with:
            - 'final_unique': Unique articles to export
            - 'confirmed_duplicates': Duplicate articles (for report)
            - 'stored_count': Number stored to DB
            - 'is_first_run': Whether this was a seeding run
            - 'articles_to_check': Original input articles
            - 'merge_stats': Statistics from merge_pipeline_outputs

    Returns:
        Dict with 'dedup_report': Report summary
    """
    with track_time("export_dedup_report"):
        debug_log("[NODE: export_dedup_report] Entering")

        dedup_json_path, dedup_csv_path, report_path = _get_output_paths()

        final_unique = state.get("final_unique", [])
        confirmed_duplicates = state.get("confirmed_duplicates", [])
        stored_count = state.get("stored_count", 0)
        is_first_run = state.get("is_first_run", False)
        articles_to_check = state.get("articles_to_check", [])
        merge_stats = state.get("merge_stats", {})

        # Count dedup types
        url_dup_count = state.get("url_duplicates_dropped", 0)
        auto_dup_count = len([d for d in confirmed_duplicates if not d.get("llm_confirmed")])
        llm_dup_count = len([d for d in confirmed_duplicates if d.get("llm_confirmed")])

        # Count by source_type in final output
        by_source_type = {}
        for article in final_unique:
            st = article.get("source_type", "rss")
            by_source_type[st] = by_source_type.get(st, 0) + 1

        # Count cross-source duplicates (where kept and removed have different source_type)
        cross_source_dups = 0
        for dup in confirmed_duplicates:
            article = dup.get("article", dup)
            duplicate_of = dup.get("duplicate_of", {})
            if article.get("source_type") != duplicate_of.get("source_type"):
                cross_source_dups += 1

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
            "by_source_type": by_source_type,
            "cross_source_duplicates": cross_source_dups,
            "merge_stats": merge_stats,
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

        # Save report (get_data_dir creates the directory if needed)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        debug_log(f"[NODE: export_dedup_report] Saved report to {report_path}")

        # Save deduplicated articles JSON
        _save_deduped_json(final_unique, report, dedup_json_path)

        # Save deduplicated articles CSV
        _save_deduped_csv(final_unique, dedup_csv_path)

        debug_log(f"[NODE: export_dedup_report] Exported {len(final_unique)} unique articles")

        # Export full database with is_new flag (based on created_at timestamp)
        lookback_hours = state.get("lookback_hours", 24)
        _save_all_articles(lookback_hours)

        return {"dedup_report": report}


def _save_deduped_json(articles: list[dict], report: dict, output_path: Path):
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

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    debug_log(f"[NODE: export_dedup_report] Saved JSON to {output_path}")


def _save_deduped_csv(articles: list[dict], output_path: Path):
    """Save deduplicated articles to CSV."""
    if not articles:
        return

    # Define column order (includes source_type for multi-source tracking)
    columns = ["date", "source", "source_type", "region", "category", "layer", "title", "contents", "url"]

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()

        for article in articles:
            # Map fields to expected column names
            row = {
                "date": article.get("date", article.get("pub_date", "")),
                "source": article.get("source", article.get("source_name", "")),
                "source_type": article.get("source_type", "rss"),
                "region": article.get("region", ""),
                "category": article.get("category", ""),
                "layer": article.get("layer", ""),
                "title": article.get("title", ""),
                "contents": article.get("contents", article.get("summary", "")),
                "url": article.get("url", article.get("link", "")),
            }
            writer.writerow(row)

    debug_log(f"[NODE: export_dedup_report] Saved CSV to {output_path}")


def _save_all_articles(lookback_hours: int = 24):
    """
    Export all articles from DB with is_new flag.

    Creates all_articles.json and all_articles.csv containing:
    - All historical articles from the database
    - is_new=True for articles with created_at within lookback_hours
    - is_new=False for older articles
    - created_at formatted in HMS (YYYY-MM-DD HH:MM:SS)

    Args:
        lookback_hours: Hours to look back for marking articles as new (default 24)
    """
    data_dir = get_data_dir()
    json_path = data_dir / "all_articles.json"
    csv_path = data_dir / "all_articles.csv"

    # Get DB instance
    db = ArticleDatabase()

    # Get all articles from DB
    all_articles = db.get_all_articles(with_embeddings=False)

    if not all_articles:
        debug_log("[NODE: export_dedup_report] No articles in database, skipping all_articles export")
        return

    # Calculate cutoff time for is_new flag
    cutoff_time = datetime.now() - timedelta(hours=lookback_hours)
    debug_log(f"[NODE: export_dedup_report] is_new cutoff: {cutoff_time.strftime('%Y-%m-%d %H:%M:%S')} ({lookback_hours}h lookback)")

    # Mark is_new based on created_at timestamp and format timestamps
    for article in all_articles:
        created_at_raw = article.get("created_at")
        created_at_dt = None

        # Parse created_at to datetime
        if created_at_raw:
            try:
                if isinstance(created_at_raw, str):
                    if "T" in created_at_raw:
                        created_at_dt = datetime.fromisoformat(created_at_raw.replace("Z", "+00:00"))
                        # Remove timezone info for comparison
                        if created_at_dt.tzinfo:
                            created_at_dt = created_at_dt.replace(tzinfo=None)
                    else:
                        created_at_dt = datetime.strptime(created_at_raw, "%Y-%m-%d %H:%M:%S")
                else:
                    created_at_dt = created_at_raw
                    if created_at_dt.tzinfo:
                        created_at_dt = created_at_dt.replace(tzinfo=None)

                # Format for output
                article["created_at"] = created_at_dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                pass  # Keep original if parsing fails

        # Mark as new if created within lookback period
        article["is_new"] = created_at_dt is not None and created_at_dt >= cutoff_time

    # Count new articles
    new_count = sum(1 for a in all_articles if a.get("is_new"))

    # Save JSON
    output = {
        "metadata": {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_articles": len(all_articles),
            "new_articles": new_count,
            "config": get_config()
        },
        "articles": all_articles
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    debug_log(f"[NODE: export_dedup_report] Saved all_articles.json ({len(all_articles)} total, {new_count} new)")

    # Save CSV
    columns = ["date", "source", "source_type", "region", "category", "layer",
               "title", "summary", "url", "created_at", "is_new"]

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()

        for article in all_articles:
            row = {
                "date": article.get("pub_date", ""),
                "source": article.get("source", ""),
                "source_type": article.get("source_type", "rss"),
                "region": article.get("region", ""),
                "category": article.get("category", ""),
                "layer": article.get("layer", ""),
                "title": article.get("title", ""),
                "summary": article.get("summary", ""),
                "url": article.get("url", ""),
                "created_at": article.get("created_at", ""),
                "is_new": article.get("is_new", False),
            }
            writer.writerow(row)

    debug_log(f"[NODE: export_dedup_report] Saved all_articles.csv")
