"""
Extract Metadata Node

Uses LLM to extract region, category, and layer from each article.
"""

import json
from typing import TypedDict, Optional

from dotenv import load_dotenv
import anthropic

# Load environment variables
load_dotenv()

from src.utils import load_prompt
from src.config import load_config_settings
from src.tracking import track_llm_cost, debug_log, track_time


class EnrichedArticle(TypedDict):
    """Article with extracted metadata."""
    # Original fields
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
    # Extracted metadata
    region: str
    category: str
    layer: str


# Default valid values (fallback if not in config.json)
DEFAULT_VALID_REGIONS = {
    "north_america", "latin_america", "europe", "middle_east",
    "africa", "south_asia", "southeast_asia", "east_asia",
    "oceania", "global", "unknown"
}

DEFAULT_VALID_CATEGORIES = {
    "funding", "acquisition", "product_launch", "partnership",
    "earnings", "expansion", "executive", "ipo",
    "regulation", "strategy", "research"
}

DEFAULT_VALID_LAYERS = {
    "chips_infra", "foundation_models", "finetuning_mlops",
    "b2b_apps", "consumer_apps"
}

# Batch size for LLM calls
BATCH_SIZE = 15


def _get_valid_values() -> tuple[set, set, set, str, str, str]:
    """
    Load valid values from config.json for current config.

    Returns:
        Tuple of (valid_regions, valid_categories, valid_layers,
                  default_region, default_category, default_layer)
    """
    config = load_config_settings()

    valid_regions = set(config.get("valid_regions", DEFAULT_VALID_REGIONS))
    valid_categories = set(config.get("valid_categories", DEFAULT_VALID_CATEGORIES))
    valid_layers = set(config.get("valid_layers", DEFAULT_VALID_LAYERS))

    # Determine defaults based on what's available
    default_region = "unknown" if "unknown" in valid_regions else "global"
    default_category = "general" if "general" in valid_categories else list(valid_categories)[0]
    default_layer = "b2b_apps" if "b2b_apps" in valid_layers else list(valid_layers)[0]

    return valid_regions, valid_categories, valid_layers, default_region, default_category, default_layer


def extract_metadata(state: dict) -> dict:
    """
    Extract region, category, and layer from filtered articles.

    Args:
        state: Pipeline state with 'filtered_articles'

    Returns:
        Dict with 'enriched_articles' list
    """
    with track_time("extract_metadata"):
        debug_log("[NODE: extract_metadata] Entering")

        filtered_articles = state.get("filtered_articles", [])
        debug_log(f"[NODE: extract_metadata] Processing {len(filtered_articles)} articles")

        if not filtered_articles:
            return {"enriched_articles": []}

        # Load config-specific valid values
        valid_regions, valid_categories, valid_layers, default_region, default_category, default_layer = _get_valid_values()
        debug_log(f"[NODE: extract_metadata] Valid categories: {valid_categories}")
        debug_log(f"[NODE: extract_metadata] Valid layers: {valid_layers}")

        # Process in batches
        all_extractions: dict[str, dict] = {}

        for i in range(0, len(filtered_articles), BATCH_SIZE):
            batch = filtered_articles[i:i + BATCH_SIZE]
            batch_num = i // BATCH_SIZE + 1
            total_batches = (len(filtered_articles) + BATCH_SIZE - 1) // BATCH_SIZE

            debug_log(f"[NODE: extract_metadata] Processing batch {batch_num}/{total_batches}")

            extractions = _extract_batch(batch, default_region, default_category, default_layer)
            all_extractions.update(extractions)

        # Apply extractions
        enriched_articles: list[EnrichedArticle] = []

        for article in filtered_articles:
            url = article.get("link", "")
            extraction = all_extractions.get(url, {})

            enriched_article: EnrichedArticle = {
                **article,
                "region": _validate_value(extraction.get("region"), valid_regions, default_region),
                "category": _validate_value(extraction.get("category"), valid_categories, default_category),
                "layer": _validate_value(extraction.get("layer"), valid_layers, default_layer),
            }
            enriched_articles.append(enriched_article)

        debug_log(f"[NODE: extract_metadata] Output: {len(enriched_articles)} enriched articles")

        # Log distribution
        _log_distribution(enriched_articles)

        return {"enriched_articles": enriched_articles}


def _extract_batch(
    articles: list[dict],
    default_region: str = "unknown",
    default_category: str = "general",
    default_layer: str = "b2b_apps"
) -> dict[str, dict]:
    """
    Extract metadata for a batch of articles using LLM.

    Args:
        articles: List of article dicts
        default_region: Default region value on parse error
        default_category: Default category value on parse error
        default_layer: Default layer value on parse error

    Returns:
        Dict mapping URL to extraction {region, category, layer}
    """
    # Load system prompt (config-aware)
    system_prompt = load_prompt("extract_metadata_system_prompt.md")

    # Prepare articles for LLM
    articles_for_llm = [
        {
            "url": a.get("link", ""),
            "title": a.get("title", ""),
            "description": a.get("description", "")[:500],
        }
        for a in articles
    ]

    user_message = json.dumps({"articles": articles_for_llm}, indent=2)

    debug_log(f"[LLM INPUT]: Extracting metadata for {len(articles)} articles")

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

    response_text = response.content[0].text
    debug_log(f"[LLM OUTPUT]: {response_text}")

    # Parse response
    try:
        result = _parse_llm_response(response_text)

        # Convert to dict by URL
        extractions = {}
        for item in result.get("extractions", []):
            url = item.get("url", "")
            if url:
                extractions[url] = {
                    "region": item.get("region", default_region),
                    "category": item.get("category", default_category),
                    "layer": item.get("layer", default_layer),
                }

        return extractions

    except Exception as e:
        debug_log(f"[NODE: extract_metadata] ERROR parsing response: {e}", "error")
        # Return defaults on error
        return {
            a.get("link", ""): {"region": default_region, "category": default_category, "layer": default_layer}
            for a in articles
        }


def _validate_value(value: str, valid_set: set, default: str) -> str:
    """Validate value is in allowed set, return default if not."""
    if value and value.lower() in valid_set:
        return value.lower()
    return default


def _log_distribution(articles: list[EnrichedArticle]) -> None:
    """Log distribution of extracted metadata."""
    region_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {}
    layer_counts: dict[str, int] = {}

    for article in articles:
        region = article.get("region", "unknown")
        category = article.get("category", "other")
        layer = article.get("layer", "b2b_apps")

        region_counts[region] = region_counts.get(region, 0) + 1
        category_counts[category] = category_counts.get(category, 0) + 1
        layer_counts[layer] = layer_counts.get(layer, 0) + 1

    debug_log(f"[NODE: extract_metadata] Region distribution: {region_counts}")
    debug_log(f"[NODE: extract_metadata] Category distribution: {category_counts}")
    debug_log(f"[NODE: extract_metadata] Layer distribution: {layer_counts}")


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
