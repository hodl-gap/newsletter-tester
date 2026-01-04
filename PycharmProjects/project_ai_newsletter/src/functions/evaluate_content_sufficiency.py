"""
Evaluate Content Sufficiency Node

Samples articles to determine if RSS descriptions provide
enough context, or if LLM summaries are needed.
"""

import json
import random
from typing import TypedDict

from dotenv import load_dotenv
import anthropic

# Load environment variables
load_dotenv()

from src.utils import load_prompt
from src.tracking import track_llm_cost, debug_log, track_time


class SufficiencyResult(TypedDict):
    """Result of content sufficiency evaluation."""
    sample_size: int
    avg_score: float
    use_descriptions: bool
    recommendation: str
    source_breakdown: dict[str, dict]


# Sample size for evaluation (percentage of articles)
SAMPLE_PERCENTAGE = 0.15  # 15%
MIN_SAMPLE_SIZE = 5
MAX_SAMPLE_SIZE = 20


def evaluate_content_sufficiency(state: dict) -> dict:
    """
    Evaluate if RSS descriptions are sufficient or if LLM summaries are needed.

    Args:
        state: Pipeline state with 'filtered_articles'

    Returns:
        Dict with 'content_sufficiency' evaluation results
    """
    with track_time("evaluate_content_sufficiency"):
        debug_log("[NODE: evaluate_content_sufficiency] Entering")

        filtered_articles = state.get("filtered_articles", [])
        debug_log(f"[NODE: evaluate_content_sufficiency] Total articles: {len(filtered_articles)}")

        if not filtered_articles:
            return {
                "content_sufficiency": {
                    "sample_size": 0,
                    "avg_score": 0,
                    "use_descriptions": True,
                    "recommendation": "no_articles",
                    "source_breakdown": {},
                }
            }

        # Filter articles that have full_content for evaluation
        articles_with_content = [
            a for a in filtered_articles
            if a.get("full_content") and len(a.get("full_content", "")) > 100
        ]

        if not articles_with_content:
            debug_log("[NODE: evaluate_content_sufficiency] No articles with full content, using descriptions by default")
            return {
                "content_sufficiency": {
                    "sample_size": 0,
                    "avg_score": 4.0,  # Assume good since we can't compare
                    "use_descriptions": True,
                    "recommendation": "no_full_content_available",
                    "source_breakdown": {},
                }
            }

        # Calculate sample size
        sample_size = max(
            MIN_SAMPLE_SIZE,
            min(MAX_SAMPLE_SIZE, int(len(articles_with_content) * SAMPLE_PERCENTAGE))
        )
        sample_size = min(sample_size, len(articles_with_content))

        # Stratified sampling by source
        samples = _stratified_sample(articles_with_content, sample_size)
        debug_log(f"[NODE: evaluate_content_sufficiency] Sampled {len(samples)} articles for evaluation")

        # Evaluate with LLM
        evaluation = _evaluate_samples(samples)

        debug_log(f"[NODE: evaluate_content_sufficiency] Avg score: {evaluation['avg_score']:.2f}")
        debug_log(f"[NODE: evaluate_content_sufficiency] Recommendation: {evaluation['recommendation']}")

        return {"content_sufficiency": evaluation}


def _stratified_sample(articles: list[dict], sample_size: int) -> list[dict]:
    """
    Perform stratified sampling to ensure coverage across sources.

    Args:
        articles: List of articles with full_content
        sample_size: Target sample size

    Returns:
        Sampled articles
    """
    # Group by source
    by_source: dict[str, list[dict]] = {}
    for article in articles:
        source = article.get("source_name", "Unknown")
        if source not in by_source:
            by_source[source] = []
        by_source[source].append(article)

    # Sample proportionally from each source
    samples = []
    sources = list(by_source.keys())

    # At least 1 per source if possible
    for source in sources:
        if by_source[source] and len(samples) < sample_size:
            samples.append(random.choice(by_source[source]))

    # Fill remaining slots randomly
    all_remaining = [a for a in articles if a not in samples]
    remaining_slots = sample_size - len(samples)
    if remaining_slots > 0 and all_remaining:
        samples.extend(random.sample(all_remaining, min(remaining_slots, len(all_remaining))))

    return samples


def _evaluate_samples(samples: list[dict]) -> SufficiencyResult:
    """
    Evaluate sampled articles using LLM.

    Args:
        samples: List of sampled articles

    Returns:
        SufficiencyResult dict
    """
    # Load system prompt
    system_prompt = load_prompt("evaluate_content_sufficiency_system_prompt.md")

    # Prepare samples for LLM
    samples_for_llm = [
        {
            "url": s.get("link", ""),
            "title": s.get("title", ""),
            "description": s.get("description", ""),
            "full_content": _truncate_content(s.get("full_content", "")),
        }
        for s in samples
    ]

    user_message = json.dumps({"samples": samples_for_llm}, indent=2)

    debug_log(f"[LLM INPUT]: System prompt length: {len(system_prompt)}")
    debug_log(f"[LLM INPUT USER]: Evaluating {len(samples)} samples")

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

        avg_score = result.get("avg_score", 3.5)
        recommendation = result.get("recommendation", "use_descriptions")
        use_descriptions = recommendation == "use_descriptions" or avg_score >= 3.5

        # Build source breakdown
        source_breakdown: dict[str, dict] = {}
        for eval_item in result.get("evaluations", []):
            url = eval_item.get("url", "")
            # Find source for this URL
            for sample in samples:
                if sample.get("link") == url:
                    source = sample.get("source_name", "Unknown")
                    if source not in source_breakdown:
                        source_breakdown[source] = {"scores": [], "avg": 0}
                    source_breakdown[source]["scores"].append(eval_item.get("score", 3))
                    break

        # Calculate averages per source
        for source, data in source_breakdown.items():
            if data["scores"]:
                data["avg"] = sum(data["scores"]) / len(data["scores"])
                data["sufficient"] = data["avg"] >= 3.5

        return SufficiencyResult(
            sample_size=len(samples),
            avg_score=avg_score,
            use_descriptions=use_descriptions,
            recommendation=recommendation,
            source_breakdown=source_breakdown,
        )

    except Exception as e:
        debug_log(f"[NODE: evaluate_content_sufficiency] ERROR parsing response: {e}", "error")
        # Default to using descriptions
        return SufficiencyResult(
            sample_size=len(samples),
            avg_score=3.5,
            use_descriptions=True,
            recommendation="parse_error_default",
            source_breakdown={},
        )


def _truncate_content(content: str, max_length: int = 2000) -> str:
    """Truncate content to reasonable length for LLM."""
    if not content:
        return ""

    # Remove HTML tags roughly
    import re
    content = re.sub(r'<[^>]+>', ' ', content)
    content = re.sub(r'\s+', ' ', content).strip()

    if len(content) > max_length:
        return content[:max_length] + "..."
    return content


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
