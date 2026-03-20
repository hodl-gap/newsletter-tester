#!/usr/bin/env python3
"""
Clean up non-AI articles from database.

Re-evaluates articles that passed the original filter to find false positives:
- Banking/finance news (central banks, forex, stock markets)
- General business news without AI connection
- Non-tech news that slipped through

This is a more aggressive re-filter than cleanup_garbage.py which only
catches zero-information content.

Supports --dry-run for safe testing.
"""
import argparse
import csv
import json
import os
from datetime import datetime
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

from src.config import set_config, get_data_dir
from src.database import ArticleDatabase
from src.tracking import CostTracker, track_llm_cost, debug_log, setup_debug_logging


BATCH_SIZE = 25
FALLBACK_BATCH_SIZES = [15, 10]

# System prompt for strict AI-relevance verification
VERIFY_AI_PROMPT = """# AI Business News Verification

You are re-verifying articles that supposedly passed an AI business news filter.
Some articles may have incorrectly passed the filter and need to be removed.

## Task

For each article, determine if it is **genuinely about AI/ML business**.
Mark as NOT AI (is_ai=false) if it's clearly non-AI content that slipped through.

## NOT AI (is_ai = false) - REMOVE these:

### Finance/Banking (NO AI connection)
- Central bank policy, interest rates, monetary policy
- Stock market indices, trading volumes
- Foreign exchange, forex reserves
- Traditional banking news (loans, deposits, regulations)
- Insurance, real estate, commodities trading

### General Business (NO AI connection)
- Retail, consumer goods, food & beverage
- Automotive (unless specifically about AI/autonomous driving)
- Energy, oil & gas, utilities
- Manufacturing (unless AI/automation focused)
- Transportation, logistics (unless AI-powered)

### Other Non-AI
- Sports, entertainment, celebrity news
- Politics, government (unless AI regulation specifically)
- Weather, natural disasters
- Crime, legal cases (unless AI-related)

## KEEP as AI (is_ai = true):

- AI company news (OpenAI, Anthropic, Google AI, etc.)
- AI chip makers (NVIDIA, AMD AI products)
- AI software/platform companies
- AI applications in any industry (AI in healthcare, AI in finance, etc.)
- AI regulation and policy affecting AI companies
- Robotics and automation companies
- Data/cloud companies with AI focus

## Input Format

```json
{
  "articles": [
    {"url": "...", "title": "...", "description": "..."}
  ]
}
```

## Output Format

Return ONLY valid JSON:

```json
{
  "classifications": [
    {"url": "...", "is_ai": true, "reason": "AI company funding"},
    {"url": "...", "is_ai": false, "reason": "Central bank policy, no AI connection"}
  ]
}
```

## Important

- Be strict: if there's no clear AI/ML connection, mark as NOT AI
- "Tech" alone doesn't qualify - must be specifically AI/ML related
- Banks using AI internally counts, but pure banking news does not
"""


def cleanup_non_ai_articles(config_name: str, dry_run: bool = False, export: bool = False) -> dict:
    """
    Find and remove non-AI articles from the database.
    """
    set_config(config_name)
    os.environ["NEWSLETTER_CONFIG"] = config_name

    db = ArticleDatabase()

    all_articles = db.get_all_articles(with_embeddings=False)
    debug_log(f"[CLEANUP-AI] Found {len(all_articles)} total articles in {config_name}")

    if not all_articles:
        return {"total": 0, "kept": 0, "removed": 0}

    # Convert to filter format
    articles_for_filter = _adapt_db_to_filter_format(all_articles)

    # Run AI verification in batches
    all_classifications: dict[str, dict] = {}
    total_batches = (len(articles_for_filter) + BATCH_SIZE - 1) // BATCH_SIZE

    for i in range(0, len(articles_for_filter), BATCH_SIZE):
        batch = articles_for_filter[i:i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1

        debug_log(f"[CLEANUP-AI] Processing batch {batch_num}/{total_batches}")

        classifications = _verify_ai_batch_with_retry(batch)
        all_classifications.update(classifications)

    # Categorize results
    non_ai_articles = []
    kept_articles = []

    for article in all_articles:
        url = article.get("url", "")
        classification = all_classifications.get(url, {"is_ai": True, "reason": "default_keep"})

        if not classification.get("is_ai", True):
            reason = classification.get("reason", "not_ai")
            non_ai_articles.append({
                "url": url,
                "url_hash": article.get("url_hash", ""),
                "title": article.get("title", ""),
                "summary": article.get("summary", ""),
                "source": article.get("source", ""),
                "source_type": article.get("source_type", "rss"),
                "pub_date": article.get("pub_date", ""),
                "discard_reason": f"not_ai:{reason}",
            })
        else:
            kept_articles.append(article)

    debug_log(f"[CLEANUP-AI] Results: {len(kept_articles)} kept, {len(non_ai_articles)} non-AI")

    # Report breakdown
    reasons: dict[str, int] = {}
    for article in non_ai_articles:
        reason = article.get("discard_reason", "unknown")
        reasons[reason] = reasons.get(reason, 0) + 1

    if dry_run:
        print(f"\n=== DRY RUN: {config_name} ===")
        print(f"Total articles: {len(all_articles)}")
        print(f"Would keep: {len(kept_articles)}")
        print(f"Would remove: {len(non_ai_articles)}")
        if reasons:
            print(f"\nNon-AI by reason:")
            for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
                print(f"  {reason}: {count}")
        print("\nNon-AI articles to remove:")
        for article in non_ai_articles[:20]:
            title = article.get("title", "")[:80]
            reason = article.get("discard_reason", "")
            print(f"  - {title}")
            print(f"    Reason: {reason}")
            print(f"    URL: {article.get('url', '')[:80]}")
            print()
        if len(non_ai_articles) > 20:
            print(f"  ... and {len(non_ai_articles) - 20} more")
        return {
            "total": len(all_articles),
            "kept": len(kept_articles),
            "removed": len(non_ai_articles),
            "reasons": reasons,
            "dry_run": True
        }

    # Move non-AI to discarded_articles table
    run_timestamp = datetime.now().isoformat()
    inserted = db.insert_discarded_batch(
        non_ai_articles,
        source_type="non_ai_cleanup",
        run_timestamp=run_timestamp
    )
    debug_log(f"[CLEANUP-AI] Inserted {inserted} articles to discarded_articles")

    # Delete non-AI from articles table
    non_ai_urls = [a["url"] for a in non_ai_articles]
    deleted = db.delete_articles_batch(non_ai_urls)
    debug_log(f"[CLEANUP-AI] Deleted {deleted} articles from articles table")

    stats = {
        "total": len(all_articles),
        "kept": len(kept_articles),
        "removed": len(non_ai_articles),
        "inserted_to_discarded": inserted,
        "deleted": deleted,
        "reasons": reasons,
    }

    if export:
        _export_all_articles(config_name)

    return stats


def _adapt_db_to_filter_format(db_articles: list[dict]) -> list[dict]:
    """Convert DB format to filter input format."""
    result = []
    for article in db_articles:
        # Use summary, or full_content truncated, or title
        description = article.get("summary", "") or (article.get("full_content", "") or "")[:500]
        result.append({
            "url": article.get("url", ""),
            "title": article.get("title", ""),
            "description": description,
        })
    return result


def _verify_ai_batch_with_retry(articles: list[dict]) -> dict[str, dict]:
    """Verify batch with automatic retry on smaller batches."""
    success, classifications = _verify_ai_batch(articles, max_tokens=2048)

    if success:
        return classifications

    # Retry with smaller batches
    for fallback_size in FALLBACK_BATCH_SIZES:
        debug_log(f"[CLEANUP-AI] Retrying with batch size {fallback_size}")

        all_success = True
        temp_classifications: dict[str, dict] = {}

        for i in range(0, len(articles), fallback_size):
            sub_batch = articles[i:i + fallback_size]
            max_tokens = 2048 if fallback_size >= 15 else 3072

            success, sub_classifications = _verify_ai_batch(sub_batch, max_tokens=max_tokens)

            if success:
                temp_classifications.update(sub_classifications)
            else:
                all_success = False
                break

        if all_success:
            return temp_classifications

    # All retries failed - keep all (conservative)
    debug_log(f"[CLEANUP-AI] All retries failed, keeping {len(articles)} articles", "error")
    return {a.get("url", ""): {"is_ai": True, "reason": "classification_failed"} for a in articles}


def _verify_ai_batch(articles: list[dict], max_tokens: int = 2048) -> tuple[bool, dict[str, dict]]:
    """Verify a batch using the AI verification prompt."""
    # Prepare input
    articles_for_llm = [
        {
            "url": a.get("url", ""),
            "title": a.get("title", ""),
            "description": a.get("description", "")[:500],
        }
        for a in articles
    ]

    user_message = json.dumps({"articles": articles_for_llm}, indent=2, ensure_ascii=False)

    debug_log(f"[LLM INPUT]: batch_size={len(articles)}, max_tokens={max_tokens}")

    # LLM call
    client = anthropic.Anthropic()

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=max_tokens,
        system=VERIFY_AI_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    track_llm_cost(
        model=response.model,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )

    response_text = response.content[0].text
    debug_log(f"[LLM OUTPUT]: {response_text[:500]}...")

    # Parse response
    try:
        result = _parse_llm_response(response_text)

        classifications = {}
        for item in result.get("classifications", []):
            url = item.get("url", "")
            if url:
                classifications[url] = {
                    "is_ai": item.get("is_ai", True),
                    "reason": item.get("reason", ""),
                }

        return True, classifications

    except Exception as e:
        debug_log(f"[CLEANUP-AI] ERROR parsing response: {e}", "error")
        return False, {}


def _parse_llm_response(response_text: str) -> dict:
    """Parse LLM response, handling markdown code blocks."""
    clean_text = response_text.strip()

    if clean_text.startswith("```"):
        lines = clean_text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        clean_text = "\n".join(lines)

    return json.loads(clean_text)


def _export_all_articles(config_name: str):
    """Export all remaining articles to JSON/CSV."""
    set_config(config_name)
    db = ArticleDatabase()
    data_dir = get_data_dir()

    articles = db.get_all_articles(with_embeddings=False)

    for article in articles:
        article["is_new"] = False

    output = {
        "metadata": {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_articles": len(articles),
            "config": config_name,
            "cleanup_export": True,
        },
        "articles": articles,
    }

    json_path = data_dir / "all_articles.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    debug_log(f"[CLEANUP-AI] Saved {json_path}")

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

    debug_log(f"[CLEANUP-AI] Saved {csv_path}")


def main():
    parser = argparse.ArgumentParser(description="Clean up non-AI articles from DB")
    parser.add_argument("--config", default="business_news", help="Config name")
    parser.add_argument("--dry-run", action="store_true",
                        help="Only report non-AI articles without deleting")
    parser.add_argument("--export", action="store_true",
                        help="Export all_articles.json/csv after cleanup")
    parser.add_argument("--configs", nargs="+",
                        help="Process multiple configs")
    args = parser.parse_args()

    setup_debug_logging()

    configs = args.configs if args.configs else [args.config]

    all_stats = {}
    for config_name in configs:
        print(f"\n{'='*50}")
        print(f"Verifying AI relevance: {config_name}")
        print(f"{'='*50}")

        stats = cleanup_non_ai_articles(
            config_name,
            dry_run=args.dry_run,
            export=args.export
        )
        all_stats[config_name] = stats

    # Print summary
    print(f"\n{'='*50}")
    print("CLEANUP SUMMARY")
    print(f"{'='*50}")

    for config_name, stats in all_stats.items():
        print(f"\n{config_name}:")
        print(f"  Total articles: {stats['total']}")
        print(f"  Kept (AI-related): {stats['kept']}")
        print(f"  Removed (non-AI): {stats['removed']}")
        if not stats.get("dry_run"):
            print(f"  Inserted to discarded: {stats.get('inserted_to_discarded', 0)}")
            print(f"  Deleted: {stats.get('deleted', 0)}")
        if stats.get("reasons"):
            print(f"  By reason:")
            for reason, count in sorted(stats["reasons"].items(), key=lambda x: -x[1]):
                print(f"    {reason}: {count}")

    if not args.dry_run:
        CostTracker().print_summary()


if __name__ == "__main__":
    main()
