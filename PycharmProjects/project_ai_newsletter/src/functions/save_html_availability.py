"""
Save HTML Availability Node

Saves HTML availability results to JSON file, merging with existing results.
"""

import json
from datetime import datetime
from pathlib import Path

from src.tracking import debug_log, track_time


OUTPUT_FILE = Path("data/html_availability.json")


def save_html_availability(state: dict) -> dict:
    """
    Save HTML availability results to JSON file.

    Merges with existing results (updates existing entries, adds new ones).

    Args:
        state: Pipeline state with 'final_results'

    Returns:
        Dict with 'output_file' path
    """
    with track_time("save_html_availability"):
        debug_log("[NODE: save_html_availability] Entering")

        final_results = state.get("final_results", [])
        debug_log(f"[NODE: save_html_availability] Saving {len(final_results)} results")

        # Load existing results if file exists
        existing_results = []
        if OUTPUT_FILE.exists():
            try:
                with open(OUTPUT_FILE) as f:
                    existing_data = json.load(f)
                    existing_results = existing_data.get("results", [])
                debug_log(f"[NODE: save_html_availability] Loaded {len(existing_results)} existing results")
            except Exception as e:
                debug_log(f"[NODE: save_html_availability] Error loading existing file: {e}", "warning")

        # Merge results (new results override existing by URL)
        results_by_url = {r["url"]: r for r in existing_results}
        for result in final_results:
            results_by_url[result["url"]] = result

        merged_results = list(results_by_url.values())

        # Calculate summary stats
        status_counts = {}
        for r in merged_results:
            status = r.get("status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1

        # Build output data
        output_data = {
            "results": merged_results,
            "timestamp": datetime.now().isoformat(),
            "total": len(merged_results),
            "scrapable": status_counts.get("scrapable", 0),
            "requires_js": status_counts.get("requires_js", 0),
            "blocked": status_counts.get("blocked", 0),
            "not_scrapable": status_counts.get("not_scrapable", 0),
        }

        # Ensure data directory exists
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

        # Write to file
        with open(OUTPUT_FILE, "w") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

        debug_log(f"[NODE: save_html_availability] Saved to {OUTPUT_FILE}")
        debug_log(f"[NODE: save_html_availability] Summary:")
        debug_log(f"[NODE: save_html_availability]   Total: {output_data['total']}")
        debug_log(f"[NODE: save_html_availability]   Scrapable: {output_data['scrapable']}")
        debug_log(f"[NODE: save_html_availability]   Requires JS: {output_data['requires_js']}")
        debug_log(f"[NODE: save_html_availability]   Blocked: {output_data['blocked']}")
        debug_log(f"[NODE: save_html_availability]   Not scrapable: {output_data['not_scrapable']}")

        return {"output_file": str(OUTPUT_FILE)}
