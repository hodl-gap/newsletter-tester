"""
Generate Summaries Node

Generates LLM summaries for ALL articles. Each summary is:
- 1-2 sentences (concise)
- In English (translated if source is non-English)
- Contains key business facts (company, action, numbers, geography)
"""

import json
import re
from typing import Optional

from dotenv import load_dotenv
import anthropic

# Load environment variables
load_dotenv()

from src.utils import load_prompt
from src.tracking import track_llm_cost, debug_log, track_time


# Batch sizes for LLM calls (with fallback on error)
BATCH_SIZE = 10
FALLBACK_BATCH_SIZES = [7, 5]


def generate_summaries(state: dict) -> dict:
    """
    Generate LLM summaries for ALL articles.

    Args:
        state: Pipeline state with 'enriched_articles'

    Returns:
        Dict with updated 'enriched_articles' (with 'contents' field)
    """
    with track_time("generate_summaries"):
        debug_log("[NODE: generate_summaries] Entering")

        enriched_articles = state.get("enriched_articles", [])
        debug_log(f"[NODE: generate_summaries] Processing {len(enriched_articles)} articles")

        if not enriched_articles:
            return {"enriched_articles": enriched_articles}

        # Generate summaries for all articles
        all_summaries = _generate_summaries_with_retry(enriched_articles)

        # Apply summaries to articles
        summarized_count = 0
        fallback_count = 0

        for article in enriched_articles:
            url = article.get("link", "")
            if url in all_summaries and all_summaries[url]:
                article["contents"] = all_summaries[url]
                article["content_source"] = "llm_summary"
                summarized_count += 1
            else:
                # Fallback to description if summarization failed
                article["contents"] = article.get("description", "")
                article["content_source"] = "description_fallback"
                fallback_count += 1

        debug_log(f"[NODE: generate_summaries] Summarized: {summarized_count}, Fallback: {fallback_count}")
        debug_log(f"[NODE: generate_summaries] Output: {len(enriched_articles)} articles processed")

        return {"enriched_articles": enriched_articles}


def _generate_summaries_with_retry(articles: list[dict]) -> dict[str, str]:
    """
    Generate summaries for all articles with adaptive batch retry.

    On parse errors, retries with smaller batch sizes (10 -> 7 -> 5).

    Args:
        articles: List of articles to summarize

    Returns:
        Dict mapping URL to summary
    """
    all_summaries: dict[str, str] = {}

    # Process in batches
    for i in range(0, len(articles), BATCH_SIZE):
        batch = articles[i:i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        total_batches = (len(articles) + BATCH_SIZE - 1) // BATCH_SIZE

        debug_log(f"[NODE: generate_summaries] Processing batch {batch_num}/{total_batches}")

        summaries = _summarize_batch_with_retry(batch)
        all_summaries.update(summaries)

    return all_summaries


def _summarize_batch_with_retry(articles: list[dict]) -> dict[str, str]:
    """
    Summarize a batch with automatic retry on smaller batch sizes.

    Args:
        articles: List of articles to summarize

    Returns:
        Dict mapping URL to summary
    """
    # Try with full batch first
    success, summaries = _summarize_batch(articles, max_tokens=2048)

    if success:
        return summaries

    # Retry with smaller batch sizes
    for fallback_size in FALLBACK_BATCH_SIZES:
        debug_log(f"[NODE: generate_summaries] Retrying with batch size {fallback_size}")

        all_success = True
        temp_summaries: dict[str, str] = {}

        for i in range(0, len(articles), fallback_size):
            sub_batch = articles[i:i + fallback_size]
            # Increase max_tokens for smaller batches
            max_tokens = 2048 if fallback_size >= 7 else 3072

            success, sub_summaries = _summarize_batch(sub_batch, max_tokens=max_tokens)

            if success:
                temp_summaries.update(sub_summaries)
            else:
                all_success = False
                break

        if all_success:
            debug_log(f"[NODE: generate_summaries] Retry with batch size {fallback_size} succeeded")
            return temp_summaries

    # All retries failed - return empty (will fall back to descriptions)
    debug_log(f"[NODE: generate_summaries] All retries failed for {len(articles)} articles", "error")
    return {}


def _summarize_batch(articles: list[dict], max_tokens: int = 2048) -> tuple[bool, dict[str, str]]:
    """
    Summarize a single batch of articles using LLM.

    Args:
        articles: List of articles to summarize
        max_tokens: Maximum tokens for LLM response

    Returns:
        Tuple of (success: bool, summaries: dict mapping URL to summary)
    """
    # Load system prompt
    system_prompt = load_prompt("generate_summary_system_prompt.md")

    # Prepare articles for LLM - use full_content if available, else description
    articles_for_llm = [
        {
            "url": a.get("link", ""),
            "title": a.get("title", ""),
            "full_content": _clean_and_truncate(
                a.get("full_content") or a.get("description", "")
            ),
        }
        for a in articles
    ]

    user_message = json.dumps({"articles": articles_for_llm}, indent=2)

    debug_log(f"[LLM INPUT]: Summarizing {len(articles)} articles, max_tokens: {max_tokens}")

    # Make LLM call
    client = anthropic.Anthropic()

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=max_tokens,
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

    response_text = response.content[0].text
    debug_log(f"[LLM OUTPUT]: {response_text[:500]}...")

    # Parse response
    try:
        result = _parse_llm_response(response_text)

        summaries = {}
        for item in result.get("summaries", []):
            url = item.get("url", "")
            summary = item.get("summary", "")
            if url and summary:
                summaries[url] = summary

        return True, summaries

    except Exception as e:
        debug_log(f"[NODE: generate_summaries] ERROR parsing response: {e}", "error")
        return False, {}


def _clean_and_truncate(content: str, max_length: int = 3000) -> str:
    """
    Clean HTML and truncate content for LLM.

    Args:
        content: Raw HTML content
        max_length: Maximum length

    Returns:
        Cleaned and truncated text
    """
    if not content:
        return ""

    # Remove HTML tags
    text = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
    text = re.sub(r'<[^>]+>', ' ', text)

    # Decode entities
    text = text.replace("&nbsp;", " ")
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&quot;", '"')
    text = text.replace("&#39;", "'")

    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()

    # Truncate
    if len(text) > max_length:
        text = text[:max_length] + "..."

    return text


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
