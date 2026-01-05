"""
Generate Summaries Node

Generates LLM summaries for articles when RSS descriptions
are insufficient. This node is conditional - only runs if
content sufficiency evaluation recommends it.
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


# Batch size for LLM calls (smaller due to larger content)
BATCH_SIZE = 10

# Threshold: descriptions > 500 chars are likely full content (e.g., VentureBeat)
FULL_CONTENT_THRESHOLD = 500


def generate_summaries(state: dict) -> dict:
    """
    Generate LLM summaries for articles if needed.

    Uses description by default. Only generates LLM summaries if
    content_sufficiency.use_descriptions is False.

    Args:
        state: Pipeline state with 'enriched_articles' and 'content_sufficiency'

    Returns:
        Dict with updated 'enriched_articles' (with 'contents' field)
    """
    with track_time("generate_summaries"):
        debug_log("[NODE: generate_summaries] Entering")

        enriched_articles = state.get("enriched_articles", [])
        content_sufficiency = state.get("content_sufficiency", {})

        use_descriptions = content_sufficiency.get("use_descriptions", True)
        debug_log(f"[NODE: generate_summaries] use_descriptions: {use_descriptions}")

        if use_descriptions:
            # Use RSS descriptions as content
            debug_log("[NODE: generate_summaries] Using RSS descriptions")
            for article in enriched_articles:
                article["contents"] = article.get("description", "")
                article["content_source"] = "description"

            debug_log(f"[NODE: generate_summaries] Output: {len(enriched_articles)} articles with descriptions")
            return {"enriched_articles": enriched_articles}

        # Generate LLM summaries
        debug_log("[NODE: generate_summaries] Generating LLM summaries")

        # Separate articles with/without full content
        # Also treat long descriptions as full content (e.g., VentureBeat puts full articles in description)
        def has_summarizable_content(a: dict) -> bool:
            if a.get("full_content") and len(a.get("full_content", "")) > 100:
                return True
            if len(a.get("description", "")) > FULL_CONTENT_THRESHOLD:
                return True
            return False

        articles_with_content = [a for a in enriched_articles if has_summarizable_content(a)]
        articles_without_content = [a for a in enriched_articles if not has_summarizable_content(a)]

        debug_log(f"[NODE: generate_summaries] {len(articles_with_content)} articles have full content")
        debug_log(f"[NODE: generate_summaries] {len(articles_without_content)} articles will use description")

        # Use description for articles without full content
        for article in articles_without_content:
            article["contents"] = article.get("description", "")
            article["content_source"] = "description_fallback"

        # Generate summaries for articles with full content
        if articles_with_content:
            summaries = _generate_summaries_batch(articles_with_content)

            for article in articles_with_content:
                url = article.get("link", "")
                if url in summaries:
                    article["contents"] = summaries[url]
                    article["content_source"] = "llm_summary"
                else:
                    article["contents"] = article.get("description", "")
                    article["content_source"] = "description_fallback"

        debug_log(f"[NODE: generate_summaries] Output: {len(enriched_articles)} articles processed")
        return {"enriched_articles": enriched_articles}


def _generate_summaries_batch(articles: list[dict]) -> dict[str, str]:
    """
    Generate summaries for a batch of articles.

    Args:
        articles: List of articles with full_content

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

        summaries = _summarize_batch(batch)
        all_summaries.update(summaries)

    return all_summaries


def _summarize_batch(articles: list[dict]) -> dict[str, str]:
    """
    Summarize a single batch of articles using LLM.

    Args:
        articles: List of articles with full_content

    Returns:
        Dict mapping URL to summary
    """
    # Load system prompt
    system_prompt = load_prompt("generate_summary_system_prompt.md")

    # Prepare articles for LLM
    # Use full_content if available, otherwise fall back to description
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

    debug_log(f"[LLM INPUT]: Summarizing {len(articles)} articles")

    # Make LLM call
    client = anthropic.Anthropic()

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
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

        return summaries

    except Exception as e:
        debug_log(f"[NODE: generate_summaries] ERROR parsing response: {e}", "error")
        # Return empty on error - will fall back to descriptions
        return {}


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
