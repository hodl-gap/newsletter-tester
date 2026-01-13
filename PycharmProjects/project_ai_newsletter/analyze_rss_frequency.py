#!/usr/bin/env python3
"""
RSS Feed Frequency Analysis

One-time script to analyze RSS feed characteristics (item count, date range)
to determine optimal pipeline run frequency.

Usage:
    python analyze_rss_frequency.py --config business_news
    python analyze_rss_frequency.py --configs business_news ai_tips
"""

import argparse
import json
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

import httpx
import feedparser


REQUEST_TIMEOUT = 20


def load_available_feeds(config: str) -> list[dict]:
    """Load available feeds from rss_availability.json for a config."""
    data_path = Path(__file__).parent / "data" / config / "rss_availability.json"

    if not data_path.exists():
        print(f"Warning: {data_path} not found")
        return []

    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    feeds = []
    for result in data.get("results", []):
        if result.get("status") != "available":
            continue

        feed_url = result.get("recommended_feed_url")
        if not feed_url:
            continue

        # Extract source name from URL
        url = result.get("url", "")
        name = url.replace("https://", "").replace("http://", "").replace("www.", "")
        name = name.split("/")[0].replace(".com", "").replace(".io", "").replace(".co.kr", "")

        feeds.append({
            "source": name[:25],  # Truncate for display
            "feed_url": feed_url,
            "config": config,
        })

    return feeds


def parse_date(entry: dict) -> datetime | None:
    """Parse entry date to datetime object."""
    # Try different date fields
    date_str = entry.get("published") or entry.get("updated") or entry.get("created")

    if not date_str:
        # Check for parsed time tuple
        if "published_parsed" in entry and entry.published_parsed:
            try:
                return datetime(*entry.published_parsed[:6])
            except Exception:
                pass
        return None

    # Try RFC 2822 date
    try:
        return parsedate_to_datetime(date_str)
    except Exception:
        pass

    # Try ISO format
    try:
        date_str = date_str.replace("Z", "+00:00")
        return datetime.fromisoformat(date_str[:19])
    except Exception:
        pass

    return None


def fetch_feed_stats(feed: dict) -> dict | None:
    """Fetch a single feed and return stats."""
    feed_url = feed["feed_url"]

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; AINewsBot/1.0)",
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        }

        response = httpx.get(
            feed_url,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
        )
        response.raise_for_status()

        parsed = feedparser.parse(response.text)

        if not parsed.entries:
            return {
                "source": feed["source"],
                "config": feed["config"],
                "items": 0,
                "newest": None,
                "oldest": None,
                "span_days": None,
                "error": "No entries",
            }

        # Parse all dates
        dates = []
        for entry in parsed.entries:
            dt = parse_date(entry)
            if dt:
                dates.append(dt)

        if not dates:
            return {
                "source": feed["source"],
                "config": feed["config"],
                "items": len(parsed.entries),
                "newest": None,
                "oldest": None,
                "span_days": None,
                "error": "No parseable dates",
            }

        newest = max(dates)
        oldest = min(dates)
        span = (newest - oldest).days

        return {
            "source": feed["source"],
            "config": feed["config"],
            "items": len(parsed.entries),
            "newest": newest.strftime("%Y-%m-%d"),
            "oldest": oldest.strftime("%Y-%m-%d"),
            "span_days": span,
            "error": None,
        }

    except Exception as e:
        return {
            "source": feed["source"],
            "config": feed["config"],
            "items": 0,
            "newest": None,
            "oldest": None,
            "span_days": None,
            "error": str(e)[:30],
        }


def main():
    parser = argparse.ArgumentParser(description="Analyze RSS feed frequency")
    parser.add_argument("--config", help="Single config to analyze")
    parser.add_argument("--configs", nargs="+", help="Multiple configs to analyze")
    args = parser.parse_args()

    configs = args.configs or ([args.config] if args.config else ["business_news"])

    # Load all feeds
    all_feeds = []
    for config in configs:
        feeds = load_available_feeds(config)
        all_feeds.extend(feeds)
        print(f"Loaded {len(feeds)} feeds from {config}")

    print(f"\nAnalyzing {len(all_feeds)} feeds...\n")

    # Fetch stats for each feed
    results = []
    for i, feed in enumerate(all_feeds):
        print(f"  [{i+1}/{len(all_feeds)}] {feed['source']}...", end=" ", flush=True)
        stats = fetch_feed_stats(feed)
        if stats:
            results.append(stats)
            if stats["error"]:
                print(f"ERROR: {stats['error']}")
            else:
                print(f"{stats['items']} items, {stats['span_days']}d span")
        else:
            print("FAILED")

    # Sort by span (ascending), None values last
    results.sort(key=lambda x: (x["span_days"] is None, x["span_days"] or 999))

    # Print table
    print("\n" + "=" * 85)
    print("RSS Feed Frequency Analysis")
    print("=" * 85)
    print(f"{'Source':<25} | {'Config':<15} | {'Items':>5} | {'Newest':<10} | {'Oldest':<10} | {'Span':>4}")
    print("-" * 85)

    for r in results:
        if r["error"]:
            print(f"{r['source']:<25} | {r['config']:<15} | ERROR: {r['error']}")
        else:
            span_str = str(r['span_days']) if r['span_days'] is not None else 'N/A'
            print(f"{r['source']:<25} | {r['config']:<15} | {r['items']:>5} | {r['newest'] or 'N/A':<10} | {r['oldest'] or 'N/A':<10} | {span_str:>4}d")

    # Summary
    valid_results = [r for r in results if r["span_days"] is not None]
    if valid_results:
        print("\n" + "=" * 85)
        print("Summary")
        print("=" * 85)

        short_span = [r for r in valid_results if r["span_days"] < 1]
        medium_span = [r for r in valid_results if 1 <= r["span_days"] <= 3]
        long_span = [r for r in valid_results if r["span_days"] > 3]

        print(f"  Feeds with <1 day span:  {len(short_span):>3}  (run every 12h recommended)")
        print(f"  Feeds with 1-3 day span: {len(medium_span):>3}  (run every 24h safe)")
        print(f"  Feeds with >3 day span:  {len(long_span):>3}  (run every 48h safe)")

        # Find the bottleneck
        if short_span:
            min_span = min(r["span_days"] for r in valid_results)
            bottleneck = [r["source"] for r in valid_results if r["span_days"] == min_span]
            print(f"\n  Bottleneck ({min_span}d span): {', '.join(bottleneck)}")


if __name__ == "__main__":
    main()
