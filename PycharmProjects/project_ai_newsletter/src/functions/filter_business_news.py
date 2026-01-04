"""
Filter Business News Node

Uses LLM to classify articles as business news (keep) or
non-business content (discard). Filters out technical research,
tutorials, and other non-business content.
"""

import json
from typing import TypedDict, Optional

from dotenv import load_dotenv
import anthropic

# Load environment variables
load_dotenv()

from src.utils import load_prompt
from src.tracking import track_llm_cost, debug_log, track_time


class FilteredArticle(TypedDict):
    """Article after business news filtering."""
    feed_url: str
    source_name: str
    title: str
    link: str
    pub_date: str
    description: str
    full_content: Optional[str]
    categories: list[str]
    author: Optional[str]
    is_business_news: bool
    filter_reason: str


# Batch size for LLM calls
BATCH_SIZE = 25


def filter_business_news(state: dict) -> dict:
    """
    Filter articles to keep only business/company AI news.

    Args:
        state: Pipeline state with 'raw_articles'

    Returns:
        Dict with 'filtered_articles' list (only business news)
    """
    with track_time("filter_business_news"):
        debug_log("[NODE: filter_business_news] Entering")

        raw_articles = state.get("raw_articles", [])
        debug_log(f"[NODE: filter_business_news] Processing {len(raw_articles)} articles")

        if not raw_articles:
            return {"filtered_articles": []}

        # Process in batches
        all_classifications: dict[str, dict] = {}

        for i in range(0, len(raw_articles), BATCH_SIZE):
            batch = raw_articles[i:i + BATCH_SIZE]
            batch_num = i // BATCH_SIZE + 1
            total_batches = (len(raw_articles) + BATCH_SIZE - 1) // BATCH_SIZE

            debug_log(f"[NODE: filter_business_news] Processing batch {batch_num}/{total_batches}")

            classifications = _classify_batch(batch)
            all_classifications.update(classifications)

        # Apply classifications
        filtered_articles: list[FilteredArticle] = []
        kept_count = 0
        discarded_count = 0

        for article in raw_articles:
            url = article.get("link", "")
            classification = all_classifications.get(url, {"is_business_news": True, "reason": "default_keep"})

            if classification["is_business_news"]:
                filtered_article: FilteredArticle = {
                    **article,
                    "is_business_news": True,
                    "filter_reason": classification.get("reason", "business_news"),
                }
                filtered_articles.append(filtered_article)
                kept_count += 1
            else:
                discarded_count += 1
                debug_log(f"[NODE: filter_business_news] Discarded: {article.get('title', '')[:50]}... ({classification.get('reason', 'unknown')})")

        debug_log(f"[NODE: filter_business_news] Kept: {kept_count}, Discarded: {discarded_count}")
        debug_log(f"[NODE: filter_business_news] Output: {len(filtered_articles)} articles")

        return {"filtered_articles": filtered_articles}


def _classify_batch(articles: list[dict]) -> dict[str, dict]:
    """
    Classify a batch of articles using LLM.

    Args:
        articles: List of article dicts

    Returns:
        Dict mapping URL to classification {is_business_news, reason}
    """
    # Load system prompt
    system_prompt = load_prompt("filter_business_news_system_prompt.md")

    # Prepare user message
    articles_for_llm = [
        {
            "url": a.get("link", ""),
            "title": a.get("title", ""),
            "description": a.get("description", "")[:500],  # Limit description length
        }
        for a in articles
    ]

    user_message = json.dumps({"articles": articles_for_llm}, indent=2)

    debug_log(f"[LLM INPUT]: System prompt length: {len(system_prompt)}")
    debug_log(f"[LLM INPUT USER]: {user_message[:1000]}...")

    # Make LLM call
    client = anthropic.Anthropic()

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
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

    # Extract response text
    response_text = response.content[0].text
    debug_log(f"[LLM OUTPUT]: {response_text}")

    # Parse JSON response
    try:
        result = _parse_llm_response(response_text)

        # Convert to dict by URL
        classifications = {}
        for item in result.get("classifications", []):
            url = item.get("url", "")
            if url:
                classifications[url] = {
                    "is_business_news": item.get("is_business_news", True),
                    "reason": item.get("reason", ""),
                }

        return classifications

    except Exception as e:
        debug_log(f"[NODE: filter_business_news] ERROR parsing response: {e}", "error")
        # Default to keeping all articles on error
        return {a.get("link", ""): {"is_business_news": True, "reason": "parse_error_default"} for a in articles}


def _parse_llm_response(response_text: str) -> dict:
    """
    Parse LLM response, handling markdown code blocks.

    Args:
        response_text: Raw LLM response

    Returns:
        Parsed JSON dict
    """
    clean_text = response_text.strip()

    # Remove markdown code blocks if present
    if clean_text.startswith("```"):
        lines = clean_text.split("\n")
        lines = lines[1:]  # Remove first line with ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        clean_text = "\n".join(lines)

    return json.loads(clean_text)
