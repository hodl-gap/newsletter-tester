#!/usr/bin/env python3
"""
Regenerate Korean summaries for articles with bad summaries in the DB.

Identifies articles with:
- Too long summaries (> 250 chars)
- Non-Korean summaries (< 30% Korean characters)

Regenerates using the same LLM with stronger prompts and validation.
"""
import argparse
import json
import os
from datetime import datetime
from pathlib import Path

from src.config import set_config, get_data_dir
from src.database import ArticleDatabase
from src.functions.generate_summaries import (
    _validate_summary,
    _retry_single_article,
    MAX_SUMMARY_LENGTH,
)
from src.tracking import CostTracker, debug_log, setup_debug_logging


def regenerate_bad_summaries(config_name: str, dry_run: bool = False) -> dict:
    """
    Find and regenerate bad summaries in the database.

    Args:
        config_name: Config to process (e.g., "business_news")
        dry_run: If True, only report issues without regenerating

    Returns:
        Dict with statistics
    """
    # Set config for prompt loading
    set_config(config_name)
    os.environ["NEWSLETTER_CONFIG"] = config_name

    db = ArticleDatabase()

    # Find articles needing regeneration
    bad_articles = db.get_articles_needing_regeneration(max_summary_length=MAX_SUMMARY_LENGTH)

    if not bad_articles:
        debug_log(f"[REGEN] No articles need regeneration for {config_name}")
        return {"total": 0, "fixed": 0, "failed": 0}

    debug_log(f"[REGEN] Found {len(bad_articles)} articles needing regeneration")

    # Group by reason for reporting
    by_reason = {}
    for article in bad_articles:
        reason = article.get("regenerate_reason", "unknown")
        by_reason[reason] = by_reason.get(reason, 0) + 1

    debug_log(f"[REGEN] Breakdown: {by_reason}")

    if dry_run:
        print(f"\n=== DRY RUN: {config_name} ===")
        print(f"Total articles needing regeneration: {len(bad_articles)}")
        print(f"By reason: {by_reason}")
        print("\nSample articles:")
        for article in bad_articles[:5]:
            title = article.get("title", "")[:50]
            reason = article.get("regenerate_reason")
            summary_len = len(article.get("summary", ""))
            print(f"  - [{reason}] {title}... ({summary_len} chars)")
        return {"total": len(bad_articles), "fixed": 0, "failed": 0, "dry_run": True}

    # Regenerate each article
    fixed_count = 0
    failed_count = 0

    for i, article in enumerate(bad_articles, 1):
        title = article.get("title", "")[:40]
        url = article.get("url", "")
        reason = article.get("regenerate_reason", "unknown")

        debug_log(f"[REGEN] Processing {i}/{len(bad_articles)}: {title}...")

        # Convert DB article format to pipeline format
        pipeline_article = {
            "link": url,
            "title": article.get("title", ""),
            "full_content": article.get("full_content", ""),
            "description": article.get("summary", ""),  # Use existing as fallback
        }

        # Retry with validation
        new_summary, new_title = _retry_single_article(pipeline_article, reason)

        if new_summary:
            # Update database
            success = db.update_summary(url, new_summary, new_title)
            if success:
                debug_log(f"[REGEN] Fixed: {title}...")
                fixed_count += 1
            else:
                debug_log(f"[REGEN] DB update failed: {title}...", "error")
                failed_count += 1
        else:
            debug_log(f"[REGEN] All retries failed: {title}...", "error")
            failed_count += 1

    stats = {
        "total": len(bad_articles),
        "fixed": fixed_count,
        "failed": failed_count,
        "by_reason": by_reason,
    }

    debug_log(f"[REGEN] Complete: {fixed_count} fixed, {failed_count} failed")

    return stats


def export_all_articles(config_name: str):
    """Export all articles to JSON/CSV with is_new flag for all."""
    import csv

    set_config(config_name)
    db = ArticleDatabase()
    data_dir = get_data_dir()

    # Get all articles
    articles = db.get_all_articles(with_embeddings=False)

    # Mark all as new (since we just regenerated)
    for article in articles:
        article["is_new"] = True

    # Save JSON
    output = {
        "metadata": {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_articles": len(articles),
            "new_articles": len(articles),
            "config": config_name,
            "regenerated": True,
        },
        "articles": articles,
    }

    json_path = data_dir / "all_articles.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    debug_log(f"[REGEN] Saved {json_path}")

    # Save CSV
    csv_path = data_dir / "all_articles.csv"
    columns = ["date", "source", "source_type", "region", "category", "layer",
               "title", "summary", "url", "created_at", "is_new"]

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for article in articles:
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

    debug_log(f"[REGEN] Saved {csv_path}")


def main():
    parser = argparse.ArgumentParser(description="Regenerate bad summaries in DB")
    parser.add_argument("--config", default="business_news", help="Config name")
    parser.add_argument("--dry-run", action="store_true",
                        help="Only report issues without regenerating")
    parser.add_argument("--export", action="store_true",
                        help="Export all_articles.json/csv after regeneration")
    parser.add_argument("--configs", nargs="+",
                        help="Process multiple configs")
    args = parser.parse_args()

    setup_debug_logging()

    configs = args.configs if args.configs else [args.config]

    all_stats = {}
    for config_name in configs:
        print(f"\n{'='*50}")
        print(f"Processing: {config_name}")
        print(f"{'='*50}")

        stats = regenerate_bad_summaries(config_name, dry_run=args.dry_run)
        all_stats[config_name] = stats

        if not args.dry_run and args.export:
            export_all_articles(config_name)

    # Print summary
    print(f"\n{'='*50}")
    print("SUMMARY")
    print(f"{'='*50}")

    for config_name, stats in all_stats.items():
        print(f"\n{config_name}:")
        print(f"  Total needing regeneration: {stats['total']}")
        if not stats.get("dry_run"):
            print(f"  Fixed: {stats['fixed']}")
            print(f"  Failed: {stats['failed']}")
        if stats.get("by_reason"):
            print(f"  By reason: {stats['by_reason']}")

    if not args.dry_run:
        CostTracker().print_summary()


if __name__ == "__main__":
    main()
