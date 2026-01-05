"""
Classify Feeds

This node uses a single batch LLM call to classify feeds as AI-focused or not.
"""

import json
from datetime import datetime, timedelta
from typing import TypedDict

from dotenv import load_dotenv
import anthropic

# Load environment variables
load_dotenv()

from src.utils import load_prompt
from src.tracking import track_llm_cost, debug_log, track_time


class ClassificationResult(TypedDict):
    url: str
    is_ai_focused: bool


def classify_feeds(feed_titles: dict[str, list[str]]) -> dict[str, bool]:
    """
    Classify multiple feeds as AI-focused or not using a single LLM call.

    Args:
        feed_titles: Dict mapping URL to list of article titles.
                    Example: {"https://example.com": ["Title 1", "Title 2"]}

    Returns:
        Dict mapping URL to is_ai_focused boolean.
        Example: {"https://example.com": True}
    """
    with track_time("classify_feeds"):
        debug_log(f"[NODE: classify_feeds] Entering")
        debug_log(f"[NODE: classify_feeds] Input: {len(feed_titles)} feeds to classify")

        if not feed_titles:
            debug_log(f"[NODE: classify_feeds] No feeds to classify")
            return {}

        # Load system prompt
        system_prompt = load_prompt("classify_feeds_system_prompt.md")

        # Prepare user message with feed titles
        user_message = json.dumps(feed_titles, indent=2)

        debug_log(f"[LLM INPUT]: {system_prompt}")
        debug_log(f"[LLM INPUT USER]: {user_message}")

        # Make LLM call
        client = anthropic.Anthropic()

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_message}
            ],
        )

        # Track cost
        track_llm_cost(
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

        # Extract response text
        response_text = response.content[0].text
        debug_log(f"[LLM OUTPUT]: {response_text}")

        # Parse JSON response (handle markdown code blocks)
        try:
            # Strip markdown code blocks if present
            clean_text = response_text.strip()
            if clean_text.startswith("```"):
                # Remove opening ```json or ```
                lines = clean_text.split("\n")
                lines = lines[1:]  # Remove first line with ```
                # Remove closing ```
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                clean_text = "\n".join(lines)

            result = json.loads(clean_text)
            debug_log(f"[NODE: classify_feeds] Output: {result}")
            return result
        except json.JSONDecodeError as e:
            debug_log(f"[NODE: classify_feeds] ERROR: Failed to parse LLM response as JSON: {e}")
            debug_log(f"[NODE: classify_feeds] Raw response: {response_text}")
            # Return all as non-AI-focused as fallback
            return {url: False for url in feed_titles.keys()}


def is_feed_fresh(latest_article_date: str | None, max_age_days: int = 7) -> bool:
    """
    Check if a feed's latest article is within max_age_days.

    Args:
        latest_article_date: ISO format date string (YYYY-MM-DD) or None.
        max_age_days: Maximum age in days for a feed to be considered fresh.

    Returns:
        True if feed is fresh (latest article within max_age_days), False otherwise.
    """
    if not latest_article_date:
        return False  # No date = assume stale

    try:
        latest = datetime.strptime(latest_article_date, "%Y-%m-%d")
        cutoff = datetime.now() - timedelta(days=max_age_days)
        return latest >= cutoff
    except ValueError:
        return False


def determine_recommended_feed(
    url: str,
    is_ai_focused: bool,
    main_feed_url: str | None,
    ai_feed_url: str | None,
    ai_feed_latest_date: str | None = None,
    max_stale_days: int = 7,
) -> tuple[str | None, str, str | None]:
    """
    Determine which feed URL to recommend based on classification and freshness.

    Args:
        url: Original base URL.
        is_ai_focused: Whether the main feed is AI-focused.
        main_feed_url: URL of the main RSS feed (if found).
        ai_feed_url: URL of the AI category feed (if found).
        ai_feed_latest_date: ISO date of latest article in AI feed (for freshness check).
        max_stale_days: Maximum age in days before AI feed is considered stale.

    Returns:
        Tuple of (recommended_feed_url, field_name, fallback_reason).
        fallback_reason is None if no fallback occurred, or a string explaining why.
    """
    if is_ai_focused:
        # Site is AI-focused, use main feed
        return main_feed_url, "main_feed_url", None
    elif ai_feed_url:
        # Site has AI category - check if it's fresh
        if is_feed_fresh(ai_feed_latest_date, max_stale_days):
            return ai_feed_url, "ai_feed_url", None
        else:
            # AI feed is stale, fall back to main feed if available
            if main_feed_url:
                return main_feed_url, "main_feed_url", "stale_ai_feed"
            # No main feed available, use stale AI feed anyway
            return ai_feed_url, "ai_feed_url", "no_main_feed_fallback"
    elif main_feed_url:
        # No AI category but has main feed
        return main_feed_url, "main_feed_url", None
    else:
        return None, "none", None


if __name__ == "__main__":
    # Test with sample data
    test_data = {
        "https://www.bensbites.com": [
            "A great time to be a builder",
            "Cheap intelligence, expensive AI",
            "GPT-5 doesn't suck anymore",
            "Google's secret kitchen",
        ],
        "https://techcabal.com": [
            "Five African founders who staged major comebacks",
            "Starlink users in Nigeria must complete biometric update",
            "iPhone 17 Series breakdown",
            "Cyber breaches in Africa became harder to hide",
        ],
    }

    result = classify_feeds(test_data)
    print(f"\n=== Classification Results ===")
    for url, is_ai in result.items():
        print(f"{url}: {'AI-focused' if is_ai else 'General'}")
