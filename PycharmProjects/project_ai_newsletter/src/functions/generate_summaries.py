"""
Generate Summaries Node

Generates LLM titles and summaries for ALL articles. Each output is:
- title: Concise Korean headline (preserves original if already Korean)
- summary: 1-2 sentences in Korean (terse wire-service style)
- Contains key business facts (company, action, numbers, geography)

Includes validation and retry logic for failed summaries.
"""

import json
import re
from typing import Optional

from dotenv import load_dotenv
import openai

# Load environment variables
load_dotenv()

from src.utils import load_prompt
from src.tracking import track_llm_cost, debug_log, track_time


# Batch sizes for LLM calls (with fallback on error)
BATCH_SIZE = 10
FALLBACK_BATCH_SIZES = [7, 5]

# Validation constants
MAX_SUMMARY_LENGTH = 250  # chars - 1-2 sentences should be under this
MIN_KOREAN_RATIO = 0.2    # at least 20% Korean characters (allows English proper nouns)
MAX_RETRIES = 3           # max retry attempts for failed summaries


def _validate_summary(summary: str, original_content: str) -> tuple[bool, str]:
    """
    Validate that a summary meets quality requirements.

    Checks:
    1. Length is reasonable (< MAX_SUMMARY_LENGTH chars)
    2. Contains Korean text (at least MIN_KOREAN_RATIO)
    3. Is not just truncated original content

    Args:
        summary: The generated summary to validate
        original_content: The original article content (for comparison)

    Returns:
        Tuple of (is_valid: bool, reason: str)
    """
    if not summary or len(summary.strip()) < 10:
        return False, "empty_or_too_short"

    # Check 1: Length (should be < MAX_SUMMARY_LENGTH for 1-2 sentences)
    if len(summary) > MAX_SUMMARY_LENGTH:
        return False, "too_long"

    # Check 2: Contains Korean (at least MIN_KOREAN_RATIO Korean chars)
    korean_chars = len(re.findall(r'[가-힣]', summary))
    total_chars = len(re.findall(r'[a-zA-Z가-힣0-9]', summary))
    if total_chars > 0 and korean_chars / total_chars < MIN_KOREAN_RATIO:
        return False, "not_korean"

    # Check 3: Not just truncated original content
    if original_content:
        # Clean the original for comparison
        clean_original = re.sub(r'\s+', ' ', original_content).strip()
        clean_summary = re.sub(r'\s+', ' ', summary).strip()

        # Check if summary is a substring of original (just truncated)
        if len(clean_summary) > 50 and clean_summary in clean_original:
            return False, "not_summarized"

        # Check if summary starts with the same content as original
        if len(clean_original) > 100 and clean_summary[:80] == clean_original[:80]:
            return False, "not_summarized"

    return True, "valid"


def generate_summaries(state: dict) -> dict:
    """
    Generate LLM titles and summaries for ALL articles.

    Args:
        state: Pipeline state with 'enriched_articles'

    Returns:
        Dict with updated 'enriched_articles' (with 'title' and 'contents' fields)
    """
    with track_time("generate_summaries"):
        debug_log("[NODE: generate_summaries] Entering")

        enriched_articles = state.get("enriched_articles", [])
        debug_log(f"[NODE: generate_summaries] Processing {len(enriched_articles)} articles")

        if not enriched_articles:
            return {"enriched_articles": enriched_articles}

        # Generate titles and summaries for all articles
        all_summaries, all_titles = _generate_summaries_with_retry(enriched_articles)

        # Apply titles and summaries to articles, with validation
        summarized_count = 0
        fallback_count = 0
        retry_count = 0
        validation_stats = {"too_long": 0, "not_korean": 0, "not_summarized": 0, "valid": 0}

        for article in enriched_articles:
            url = article.get("link", "")
            original_content = article.get("full_content") or article.get("description", "")

            if url in all_summaries and all_summaries[url]:
                summary = all_summaries[url]

                # Validate the summary
                is_valid, reason = _validate_summary(summary, original_content)
                validation_stats[reason] = validation_stats.get(reason, 0) + 1

                if is_valid:
                    # Use LLM-generated Korean title if available
                    if url in all_titles and all_titles[url]:
                        article["title"] = all_titles[url]
                    article["contents"] = summary
                    article["content_source"] = "llm_summary"
                    summarized_count += 1
                else:
                    # Validation failed - retry with single article
                    debug_log(f"[NODE: generate_summaries] Validation failed ({reason}): {article.get('title', '')[:50]}...")
                    retry_summary, retry_title = _retry_single_article(article, reason)

                    if retry_summary:
                        if retry_title:
                            article["title"] = retry_title
                        article["contents"] = retry_summary
                        article["content_source"] = "llm_summary_retry"
                        summarized_count += 1
                        retry_count += 1
                    else:
                        # All retries failed - fallback
                        article["contents"] = article.get("description", "")
                        article["content_source"] = "description_fallback"
                        article["fallback_reason"] = f"validation_failed:{reason}"
                        fallback_count += 1
            else:
                # No summary returned - fallback to description
                article["contents"] = article.get("description", "")
                article["content_source"] = "description_fallback"
                article["fallback_reason"] = "llm_no_response"
                fallback_count += 1

        debug_log(f"[NODE: generate_summaries] Summarized: {summarized_count}, Retried: {retry_count}, Fallback: {fallback_count}")
        debug_log(f"[NODE: generate_summaries] Validation stats: {validation_stats}")
        debug_log(f"[NODE: generate_summaries] Output: {len(enriched_articles)} articles processed")

        return {"enriched_articles": enriched_articles}


def _generate_summaries_with_retry(articles: list[dict]) -> tuple[dict[str, str], dict[str, str]]:
    """
    Generate titles and summaries for all articles with adaptive batch retry.

    On parse errors, retries with smaller batch sizes (10 -> 7 -> 5).

    Args:
        articles: List of articles to summarize

    Returns:
        Tuple of (summaries dict, titles dict) mapping URL to content
    """
    all_summaries: dict[str, str] = {}
    all_titles: dict[str, str] = {}

    # Process in batches
    for i in range(0, len(articles), BATCH_SIZE):
        batch = articles[i:i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        total_batches = (len(articles) + BATCH_SIZE - 1) // BATCH_SIZE

        debug_log(f"[NODE: generate_summaries] Processing batch {batch_num}/{total_batches}")

        summaries, titles = _summarize_batch_with_retry(batch)
        all_summaries.update(summaries)
        all_titles.update(titles)

    return all_summaries, all_titles


def _summarize_batch_with_retry(articles: list[dict]) -> tuple[dict[str, str], dict[str, str]]:
    """
    Summarize a batch with automatic retry on smaller batch sizes.

    Args:
        articles: List of articles to summarize

    Returns:
        Tuple of (summaries dict, titles dict) mapping URL to content
    """
    # Try with full batch first
    success, summaries, titles = _summarize_batch(articles, max_tokens=4096)

    if success:
        return summaries, titles

    # Retry with smaller batch sizes
    for fallback_size in FALLBACK_BATCH_SIZES:
        debug_log(f"[NODE: generate_summaries] Retrying with batch size {fallback_size}")

        all_success = True
        temp_summaries: dict[str, str] = {}
        temp_titles: dict[str, str] = {}

        for i in range(0, len(articles), fallback_size):
            sub_batch = articles[i:i + fallback_size]
            # Increase max_tokens for smaller batches
            max_tokens = 4096 if fallback_size >= 7 else 6144

            success, sub_summaries, sub_titles = _summarize_batch(sub_batch, max_tokens=max_tokens)

            if success:
                temp_summaries.update(sub_summaries)
                temp_titles.update(sub_titles)
            else:
                all_success = False
                break

        if all_success:
            debug_log(f"[NODE: generate_summaries] Retry with batch size {fallback_size} succeeded")
            return temp_summaries, temp_titles

    # All retries failed - return empty (will fall back to descriptions)
    debug_log(f"[NODE: generate_summaries] All retries failed for {len(articles)} articles", "error")
    return {}, {}


def _summarize_batch(articles: list[dict], max_tokens: int = 2048) -> tuple[bool, dict[str, str], dict[str, str]]:
    """
    Summarize a single batch of articles using LLM.

    Args:
        articles: List of articles to summarize
        max_tokens: Maximum tokens for LLM response

    Returns:
        Tuple of (success: bool, summaries: dict, titles: dict)
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
    client = openai.OpenAI()

    response = client.chat.completions.create(
        model="gpt-5-mini",
        max_completion_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
    )

    # Track cost
    track_llm_cost(
        model=response.model,
        input_tokens=response.usage.prompt_tokens,
        output_tokens=response.usage.completion_tokens,
    )

    response_text = response.choices[0].message.content
    debug_log(f"[LLM OUTPUT]: {response_text[:500]}...")

    # Parse response
    try:
        result = _parse_llm_response(response_text)

        summaries = {}
        titles = {}
        for item in result.get("summaries", []):
            url = item.get("url", "")
            summary = item.get("summary", "")
            title = item.get("title", "")
            if url and summary:
                summaries[url] = summary
            if url and title:
                titles[url] = title

        return True, summaries, titles

    except Exception as e:
        debug_log(f"[NODE: generate_summaries] ERROR parsing response: {e}", "error")
        return False, {}, {}


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


def _retry_single_article(
    article: dict,
    failure_reason: str
) -> tuple[Optional[str], Optional[str]]:
    """
    Retry summarization for a single article with a stronger prompt.

    Args:
        article: The article that failed validation
        failure_reason: Why the original summary failed (too_long, not_korean, not_summarized)

    Returns:
        Tuple of (summary, title) or (None, None) if all retries fail
    """
    # Build a stronger prompt based on failure reason
    extra_instruction = ""
    if failure_reason == "too_long":
        extra_instruction = """
CRITICAL: Your previous summary was TOO LONG.
You MUST output a summary under 200 characters (about 1-2 sentences).
DO NOT copy the original text. SUMMARIZE it briefly."""
    elif failure_reason == "not_korean":
        extra_instruction = """
CRITICAL: Your previous summary was in ENGLISH, not Korean.
You MUST output the summary in Korean (한국어).
Translate and summarize ALL content to Korean."""
    elif failure_reason == "not_summarized":
        extra_instruction = """
CRITICAL: Your previous output was just the original content, not a summary.
You MUST SUMMARIZE the content into 1-2 concise Korean sentences.
DO NOT copy the original text verbatim."""

    system_prompt = load_prompt("generate_summary_system_prompt.md")
    system_prompt = f"{extra_instruction}\n\n{system_prompt}"

    # Prepare single article
    article_for_llm = {
        "url": article.get("link", ""),
        "title": article.get("title", ""),
        "full_content": _clean_and_truncate(
            article.get("full_content") or article.get("description", ""),
            max_length=2000  # Shorter for single article
        ),
    }

    user_message = json.dumps({"articles": [article_for_llm]}, indent=2)
    original_content = article.get("full_content") or article.get("description", "")

    client = openai.OpenAI()

    for attempt in range(MAX_RETRIES):
        debug_log(f"[NODE: generate_summaries] Retry attempt {attempt + 1}/{MAX_RETRIES} for: {article.get('title', '')[:40]}...")

        try:
            response = client.chat.completions.create(
                model="gpt-5-mini",
                max_completion_tokens=4096,  # Increased from 2048 - model needs ~2800 tokens for longer articles
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
            )

            track_llm_cost(
                model=response.model,
                input_tokens=response.usage.prompt_tokens,
                output_tokens=response.usage.completion_tokens,
            )

            # Check if response was truncated
            if response.choices[0].finish_reason == "length":
                debug_log(f"[NODE: generate_summaries] Retry {attempt + 1} truncated (finish_reason=length)", "warning")
                continue

            response_text = response.choices[0].message.content
            if not response_text:
                debug_log(f"[NODE: generate_summaries] Retry {attempt + 1} returned empty content", "warning")
                continue

            result = _parse_llm_response(response_text)

            summaries = result.get("summaries", [])
            if summaries:
                summary = summaries[0].get("summary", "")
                title = summaries[0].get("title", "")

                # Validate the retry result
                is_valid, reason = _validate_summary(summary, original_content)
                if is_valid:
                    debug_log(f"[NODE: generate_summaries] Retry succeeded on attempt {attempt + 1}")
                    return summary, title
                else:
                    debug_log(f"[NODE: generate_summaries] Retry {attempt + 1} still invalid: {reason}")

        except Exception as e:
            debug_log(f"[NODE: generate_summaries] Retry {attempt + 1} error: {e}", "error")

    debug_log(f"[NODE: generate_summaries] All {MAX_RETRIES} retries failed for: {article.get('title', '')[:40]}...", "error")
    return None, None
