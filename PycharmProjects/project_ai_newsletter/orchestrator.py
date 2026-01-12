"""
Main Orchestrator - Full Pipeline Runner

Runs the complete AI Newsletter pipeline for one or multiple configs.
When running multiple configs, Twitter scraping is automatically consolidated
(each handle scraped once, shared across configs).

Pipeline Order:
    1. RSS Layer 1 (per config) - RSS discovery
    2. RSS Layer 2 (per config) - Content aggregation
    3. HTML Layer 1 (per config) - Scrapability discovery
    4. HTML Layer 2 (per config) - Content scraping
    5. Browser-Use L2 (per config) - Blocked sources via LLM-driven browser
    6. Twitter Layer 1 (CONSOLIDATED if multi-config) - Account discovery
    7. Twitter Layer 2 (per config) - Content aggregation
    8. Dedup Layer 3 (per config) - Semantic deduplication

Usage:
    # Single config
    python orchestrator.py --config business_news

    # Multiple configs (Twitter automatically consolidated)
    python orchestrator.py --configs business_news ai_tips

    # Skip specific layers
    python orchestrator.py --configs business_news ai_tips --skip-rss-l1 --skip-html

    # Only run specific layers
    python orchestrator.py --configs business_news ai_tips --only twitter dedup
"""

from typing import Optional
from src.tracking import debug_log, reset_cost_tracker, cost_tracker, track_time


def run(
    configs: list[str],
    max_age_hours: int = 24,
    skip_rss_l1: bool = False,
    skip_rss_l2: bool = False,
    skip_html_l1: bool = False,
    skip_html_l2: bool = False,
    skip_browser_use: bool = False,
    skip_twitter: bool = False,
    skip_dedup: bool = False,
) -> dict:
    """
    Run the full pipeline for one or multiple configs.

    When multiple configs are provided, Twitter scraping is automatically
    consolidated - each handle is scraped only once and cached in
    data/shared/twitter_raw_cache.json.

    Args:
        configs: List of config names (e.g., ["business_news", "ai_tips"])
        max_age_hours: Maximum article age in hours (default: 24)
        skip_rss_l1: Skip RSS Layer 1 (discovery)
        skip_rss_l2: Skip RSS Layer 2 (content aggregation)
        skip_html_l1: Skip HTML Layer 1 (scrapability discovery)
        skip_html_l2: Skip HTML Layer 2 (content scraping)
        skip_browser_use: Skip Browser-Use layer (blocked sources)
        skip_twitter: Skip Twitter layers entirely
        skip_dedup: Skip deduplication layer

    Returns:
        Dict with results from each layer/config
    """
    import rss_orchestrator
    import content_orchestrator
    import html_layer1_orchestrator
    import html_layer2_orchestrator
    import browser_use_orchestrator
    import twitter_layer1_orchestrator
    import twitter_layer2_orchestrator
    import dedup_orchestrator

    is_multi_config = len(configs) > 1

    debug_log("=" * 70)
    debug_log("STARTING MAIN ORCHESTRATOR")
    debug_log(f"CONFIGS: {configs}")
    debug_log(f"MULTI-CONFIG MODE: {is_multi_config}")
    debug_log(f"MAX AGE HOURS: {max_age_hours}")
    debug_log("=" * 70)

    reset_cost_tracker()

    results = {
        "configs": configs,
        "rss_l1": {},
        "rss_l2": {},
        "html_l1": {},
        "html_l2": {},
        "browser_use": {},
        "twitter_l1": None,
        "twitter_l2": {},
        "dedup": {},
    }

    # =========================================================================
    # RSS Layer 1: Discovery (per config)
    # =========================================================================
    if not skip_rss_l1:
        debug_log("\n" + "=" * 70)
        debug_log("PHASE 1: RSS LAYER 1 (DISCOVERY)")
        debug_log("=" * 70)

        for config in configs:
            debug_log(f"\n--- RSS L1: {config} ---")
            try:
                with track_time(f"rss_l1_{config}"):
                    result = rss_orchestrator.run(config=config)
                    results["rss_l1"][config] = {"success": True, "result": result}
            except Exception as e:
                debug_log(f"RSS L1 failed for {config}: {e}", "error")
                results["rss_l1"][config] = {"success": False, "error": str(e)}
    else:
        debug_log("\n[SKIPPED] RSS Layer 1")

    # =========================================================================
    # RSS Layer 2: Content Aggregation (per config)
    # =========================================================================
    if not skip_rss_l2:
        debug_log("\n" + "=" * 70)
        debug_log("PHASE 2: RSS LAYER 2 (CONTENT AGGREGATION)")
        debug_log("=" * 70)

        for config in configs:
            debug_log(f"\n--- RSS L2: {config} ---")
            try:
                with track_time(f"rss_l2_{config}"):
                    result = content_orchestrator.run(
                        config=config,
                        max_age_hours=max_age_hours,
                    )
                    results["rss_l2"][config] = {"success": True, "result": result}
            except Exception as e:
                debug_log(f"RSS L2 failed for {config}: {e}", "error")
                results["rss_l2"][config] = {"success": False, "error": str(e)}
    else:
        debug_log("\n[SKIPPED] RSS Layer 2")

    # =========================================================================
    # HTML Layer 1: Scrapability Discovery (per config)
    # =========================================================================
    if not skip_html_l1:
        debug_log("\n" + "=" * 70)
        debug_log("PHASE 3: HTML LAYER 1 (SCRAPABILITY DISCOVERY)")
        debug_log("=" * 70)

        for config in configs:
            debug_log(f"\n--- HTML L1: {config} ---")
            try:
                with track_time(f"html_l1_{config}"):
                    result = html_layer1_orchestrator.run(config=config)
                    results["html_l1"][config] = {"success": True, "result": result}
            except Exception as e:
                debug_log(f"HTML L1 failed for {config}: {e}", "error")
                results["html_l1"][config] = {"success": False, "error": str(e)}
    else:
        debug_log("\n[SKIPPED] HTML Layer 1")

    # =========================================================================
    # HTML Layer 2: Content Scraping (per config)
    # =========================================================================
    if not skip_html_l2:
        debug_log("\n" + "=" * 70)
        debug_log("PHASE 4: HTML LAYER 2 (CONTENT SCRAPING)")
        debug_log("=" * 70)

        for config in configs:
            debug_log(f"\n--- HTML L2: {config} ---")
            try:
                with track_time(f"html_l2_{config}"):
                    result = html_layer2_orchestrator.run(
                        config=config,
                        max_age_hours=max_age_hours,
                    )
                    results["html_l2"][config] = {"success": True, "result": result}
            except Exception as e:
                debug_log(f"HTML L2 failed for {config}: {e}", "error")
                results["html_l2"][config] = {"success": False, "error": str(e)}
    else:
        debug_log("\n[SKIPPED] HTML Layer 2")

    # =========================================================================
    # Browser-Use: Blocked Sources Scraping (per config)
    # =========================================================================
    if not skip_browser_use:
        debug_log("\n" + "=" * 70)
        debug_log("PHASE 5: BROWSER-USE (BLOCKED SOURCES)")
        debug_log("=" * 70)

        for config in configs:
            debug_log(f"\n--- Browser-Use: {config} ---")
            try:
                with track_time(f"browser_use_{config}"):
                    result = browser_use_orchestrator.run(
                        config=config,
                        max_age_hours=max_age_hours,
                    )
                    results["browser_use"][config] = {"success": True, "result": result}
            except Exception as e:
                debug_log(f"Browser-Use failed for {config}: {e}", "error")
                results["browser_use"][config] = {"success": False, "error": str(e)}
    else:
        debug_log("\n[SKIPPED] Browser-Use Layer")

    # =========================================================================
    # Twitter: Consolidated L1 + Per-Config L2
    # =========================================================================
    if not skip_twitter:
        debug_log("\n" + "=" * 70)
        debug_log("PHASE 6: TWITTER (CONSOLIDATED SCRAPING)")
        debug_log("=" * 70)

        if is_multi_config:
            # Multi-config: Use consolidated scraping
            debug_log("\n--- Twitter L1: CONSOLIDATED (all configs) ---")
            try:
                with track_time("twitter_l1_consolidated"):
                    result = twitter_layer1_orchestrator.run_multi(configs=configs)
                    results["twitter_l1"] = {"success": True, "result": result, "mode": "consolidated"}
            except Exception as e:
                debug_log(f"Twitter L1 (consolidated) failed: {e}", "error")
                results["twitter_l1"] = {"success": False, "error": str(e), "mode": "consolidated"}

            # Run L2 for each config using shared cache
            debug_log("\n" + "-" * 40)
            debug_log("TWITTER LAYER 2 (PER CONFIG, SHARED CACHE)")
            debug_log("-" * 40)

            for config in configs:
                debug_log(f"\n--- Twitter L2: {config} ---")
                try:
                    with track_time(f"twitter_l2_{config}"):
                        result = twitter_layer2_orchestrator.run(
                            config=config,
                            use_shared_cache=True,
                            max_age_hours=max_age_hours,
                        )
                        results["twitter_l2"][config] = {"success": True, "result": result}
                except Exception as e:
                    debug_log(f"Twitter L2 failed for {config}: {e}", "error")
                    results["twitter_l2"][config] = {"success": False, "error": str(e)}
        else:
            # Single config: Use standard L1 + L2
            config = configs[0]

            debug_log(f"\n--- Twitter L1: {config} ---")
            try:
                with track_time(f"twitter_l1_{config}"):
                    result = twitter_layer1_orchestrator.run(config=config)
                    results["twitter_l1"] = {"success": True, "result": result, "mode": "single"}
            except Exception as e:
                debug_log(f"Twitter L1 failed for {config}: {e}", "error")
                results["twitter_l1"] = {"success": False, "error": str(e), "mode": "single"}

            debug_log(f"\n--- Twitter L2: {config} ---")
            try:
                with track_time(f"twitter_l2_{config}"):
                    result = twitter_layer2_orchestrator.run(
                        config=config,
                        max_age_hours=max_age_hours,
                    )
                    results["twitter_l2"][config] = {"success": True, "result": result}
            except Exception as e:
                debug_log(f"Twitter L2 failed for {config}: {e}", "error")
                results["twitter_l2"][config] = {"success": False, "error": str(e)}
    else:
        debug_log("\n[SKIPPED] Twitter Layers")

    # =========================================================================
    # Dedup Layer 3: Semantic Deduplication (per config)
    # =========================================================================
    if not skip_dedup:
        debug_log("\n" + "=" * 70)
        debug_log("PHASE 7: DEDUPLICATION (LAYER 3)")
        debug_log("=" * 70)

        for config in configs:
            debug_log(f"\n--- Dedup: {config} ---")
            try:
                with track_time(f"dedup_{config}"):
                    result = dedup_orchestrator.run(config=config)
                    results["dedup"][config] = {"success": True, "result": result}
            except Exception as e:
                debug_log(f"Dedup failed for {config}: {e}", "error")
                results["dedup"][config] = {"success": False, "error": str(e)}
    else:
        debug_log("\n[SKIPPED] Deduplication")

    # =========================================================================
    # Summary
    # =========================================================================
    debug_log("\n" + "=" * 70)
    debug_log("MAIN ORCHESTRATOR COMPLETE")
    debug_log("=" * 70)

    _print_summary(results)
    cost_tracker.print_summary()

    return results


def _print_summary(results: dict) -> None:
    """Print a summary of pipeline results."""
    debug_log("\n--- SUMMARY ---")

    for config in results["configs"]:
        debug_log(f"\nConfig: {config}")

        # RSS L2
        if config in results["rss_l2"]:
            r = results["rss_l2"][config]
            if r["success"]:
                save_status = r["result"].get("save_status", {})
                debug_log(f"  RSS L2: {save_status.get('record_count', 0)} articles")
            else:
                debug_log(f"  RSS L2: FAILED - {r.get('error', 'Unknown')}")

        # HTML L2
        if config in results["html_l2"]:
            r = results["html_l2"][config]
            if r["success"]:
                save_status = r["result"].get("save_status", {})
                debug_log(f"  HTML L2: {save_status.get('record_count', 0)} articles")
            else:
                debug_log(f"  HTML L2: FAILED - {r.get('error', 'Unknown')}")

        # Browser-Use
        if config in results["browser_use"]:
            r = results["browser_use"][config]
            if r["success"]:
                save_status = r["result"].get("save_status", {})
                debug_log(f"  Browser-Use: {save_status.get('record_count', 0)} articles")
            else:
                debug_log(f"  Browser-Use: FAILED - {r.get('error', 'Unknown')}")

        # Twitter L2
        if config in results["twitter_l2"]:
            r = results["twitter_l2"][config]
            if r["success"]:
                save_status = r["result"].get("save_status", {})
                debug_log(f"  Twitter L2: {save_status.get('record_count', 0)} articles")
            else:
                debug_log(f"  Twitter L2: FAILED - {r.get('error', 'Unknown')}")

        # Dedup
        if config in results["dedup"]:
            r = results["dedup"][config]
            if r["success"]:
                save_status = r["result"].get("save_status", {})
                debug_log(f"  Dedup: {save_status.get('unique_count', 0)} unique articles")
            else:
                debug_log(f"  Dedup: FAILED - {r.get('error', 'Unknown')}")

    # Twitter L1 (consolidated)
    if results["twitter_l1"]:
        r = results["twitter_l1"]
        mode = r.get("mode", "unknown")
        if r["success"]:
            save_status = r["result"].get("save_status", {})
            if mode == "consolidated":
                debug_log(f"\nTwitter L1 (consolidated): {save_status.get('total_handles', 0)} handles, "
                          f"{save_status.get('cached_tweets', 0)} tweets")
            else:
                debug_log(f"\nTwitter L1: {save_status.get('total_accounts', 0)} accounts, "
                          f"{save_status.get('cached_tweets', 0)} tweets")
        else:
            debug_log(f"\nTwitter L1: FAILED - {r.get('error', 'Unknown')}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Run the full AI Newsletter pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single config
  python orchestrator.py --config business_news

  # Multiple configs (Twitter automatically consolidated)
  python orchestrator.py --configs business_news ai_tips

  # Skip discovery layers (faster, use existing L1 data)
  python orchestrator.py --configs business_news ai_tips --skip-rss-l1 --skip-html-l1

  # Only run Twitter and Dedup
  python orchestrator.py --configs business_news ai_tips --only twitter dedup
        """
    )

    # Config selection (mutually exclusive)
    config_group = parser.add_mutually_exclusive_group(required=True)
    config_group.add_argument(
        "--config",
        help="Single config to run"
    )
    config_group.add_argument(
        "--configs",
        nargs="+",
        help="Multiple configs (Twitter automatically consolidated)"
    )

    # Common options
    parser.add_argument(
        "--max-age-hours",
        type=int,
        default=24,
        help="Maximum article age in hours (default: 24)"
    )

    # Skip options
    parser.add_argument("--skip-rss-l1", action="store_true", help="Skip RSS Layer 1")
    parser.add_argument("--skip-rss-l2", action="store_true", help="Skip RSS Layer 2")
    parser.add_argument("--skip-html-l1", action="store_true", help="Skip HTML Layer 1")
    parser.add_argument("--skip-html-l2", action="store_true", help="Skip HTML Layer 2")
    parser.add_argument("--skip-html", action="store_true", help="Skip both HTML layers")
    parser.add_argument("--skip-browser-use", action="store_true", help="Skip Browser-Use layer")
    parser.add_argument("--skip-twitter", action="store_true", help="Skip Twitter layers")
    parser.add_argument("--skip-dedup", action="store_true", help="Skip deduplication")

    # Only option (run specific layers only)
    parser.add_argument(
        "--only",
        nargs="+",
        choices=["rss-l1", "rss-l2", "rss", "html-l1", "html-l2", "html", "browser-use", "twitter", "dedup"],
        help="Only run specified layers"
    )

    args = parser.parse_args()

    # Handle --config vs --configs
    if args.config:
        configs = [args.config]
    else:
        configs = args.configs

    # Handle --skip-html shortcut
    skip_html_l1 = args.skip_html_l1 or args.skip_html
    skip_html_l2 = args.skip_html_l2 or args.skip_html

    # Handle --only option
    skip_browser_use = getattr(args, 'skip_browser_use', False)
    if args.only:
        only_set = set(args.only)
        # Expand shortcuts
        if "rss" in only_set:
            only_set.add("rss-l1")
            only_set.add("rss-l2")
        if "html" in only_set:
            only_set.add("html-l1")
            only_set.add("html-l2")

        # Set skips based on what's NOT in only
        args.skip_rss_l1 = "rss-l1" not in only_set
        args.skip_rss_l2 = "rss-l2" not in only_set
        skip_html_l1 = "html-l1" not in only_set
        skip_html_l2 = "html-l2" not in only_set
        skip_browser_use = "browser-use" not in only_set
        args.skip_twitter = "twitter" not in only_set
        args.skip_dedup = "dedup" not in only_set

    # Run the pipeline
    results = run(
        configs=configs,
        max_age_hours=args.max_age_hours,
        skip_rss_l1=args.skip_rss_l1,
        skip_rss_l2=args.skip_rss_l2,
        skip_html_l1=skip_html_l1,
        skip_html_l2=skip_html_l2,
        skip_browser_use=skip_browser_use,
        skip_twitter=args.skip_twitter,
        skip_dedup=args.skip_dedup,
    )

    # Print final summary
    print("\n" + "=" * 70)
    print("PIPELINE COMPLETE")
    print("=" * 70)

    for config in configs:
        print(f"\nConfig: {config}")

        if config in results["rss_l2"] and results["rss_l2"][config]["success"]:
            s = results["rss_l2"][config]["result"].get("save_status", {})
            print(f"  RSS: {s.get('record_count', 0)} articles → {s.get('json_path', 'N/A')}")

        if config in results["html_l2"] and results["html_l2"][config]["success"]:
            s = results["html_l2"][config]["result"].get("save_status", {})
            print(f"  HTML: {s.get('record_count', 0)} articles → {s.get('json_path', 'N/A')}")

        if config in results["browser_use"] and results["browser_use"][config]["success"]:
            s = results["browser_use"][config]["result"].get("save_status", {})
            print(f"  Browser-Use: {s.get('record_count', 0)} articles → {s.get('json_path', 'N/A')}")

        if config in results["twitter_l2"] and results["twitter_l2"][config]["success"]:
            s = results["twitter_l2"][config]["result"].get("save_status", {})
            print(f"  Twitter: {s.get('record_count', 0)} articles → {s.get('json_path', 'N/A')}")

        if config in results["dedup"] and results["dedup"][config]["success"]:
            s = results["dedup"][config]["result"].get("save_status", {})
            print(f"  Dedup: {s.get('unique_count', 0)} unique → {s.get('json_path', 'N/A')}")
