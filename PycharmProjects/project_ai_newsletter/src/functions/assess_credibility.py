"""
Assess Credibility Node

Uses LLM to assess source credibility based on web search results
(Wikipedia presence, ownership info, reputation mentions).
Returns source_quality: "quality" or "crude" for each source.
"""

import json
from typing import TypedDict

from dotenv import load_dotenv
import anthropic

# Load environment variables
load_dotenv()

from src.utils import load_prompt
from src.tracking import track_llm_cost, debug_log, track_time
from src.functions.fetch_source_reputation import SourceReputation


class CredibilityAssessment(TypedDict):
    """Credibility assessment result for a source."""
    url: str
    source_quality: str  # "quality" or "crude"
    reason: str


# Batch size for LLM calls
BATCH_SIZE = 5  # Smaller batches due to longer search results


def assess_credibility(state: dict) -> dict:
    """
    Assess credibility of sources based on web search reputation data.

    Args:
        state: Pipeline state with 'source_reputation' list

    Returns:
        Dict with 'assessments' list of CredibilityAssessment
    """
    with track_time("assess_credibility"):
        debug_log("[NODE: assess_credibility] Entering")

        source_reputation = state.get("source_reputation", [])
        debug_log(f"[NODE: assess_credibility] Processing {len(source_reputation)} sources")

        if not source_reputation:
            return {"assessments": []}

        # Filter out sources with search errors
        assessable_sources = [s for s in source_reputation if not s.get("search_error")]
        errored_sources = [s for s in source_reputation if s.get("search_error")]

        debug_log(f"[NODE: assess_credibility] {len(assessable_sources)} assessable, {len(errored_sources)} with search errors")

        # Process in batches
        all_assessments: list[CredibilityAssessment] = []

        for i in range(0, len(assessable_sources), BATCH_SIZE):
            batch = assessable_sources[i:i + BATCH_SIZE]
            batch_num = i // BATCH_SIZE + 1
            total_batches = (len(assessable_sources) + BATCH_SIZE - 1) // BATCH_SIZE

            debug_log(f"[NODE: assess_credibility] Processing batch {batch_num}/{total_batches}")

            batch_assessments = _assess_batch(batch)
            all_assessments.extend(batch_assessments)

        # Add default assessments for sources with search errors
        for source in errored_sources:
            all_assessments.append({
                "url": source["url"],
                "source_quality": "crude",
                "reason": f"Could not search for reputation: {source.get('search_error', 'unknown error')}",
            })

        # Log summary
        quality_count = sum(1 for a in all_assessments if a["source_quality"] == "quality")
        crude_count = sum(1 for a in all_assessments if a["source_quality"] == "crude")
        debug_log(f"[NODE: assess_credibility] Quality: {quality_count}, Crude: {crude_count}")

        return {"assessments": all_assessments}


def _assess_batch(sources: list[SourceReputation]) -> list[CredibilityAssessment]:
    """
    Assess a batch of sources using LLM.

    Args:
        sources: List of SourceReputation dicts

    Returns:
        List of CredibilityAssessment dicts
    """
    # Load system prompt
    system_prompt = load_prompt("assess_credibility_system_prompt.md")

    # Prepare user message with search results
    sources_for_llm = [
        {
            "url": s["url"],
            "domain": s["domain"],
            "publication_name": s["publication_name"],
            "wikipedia_found": s["wikipedia_found"],
            "search_results": s["search_results"][:2000],  # Limit to prevent token overflow
        }
        for s in sources
    ]

    user_message = json.dumps({"sources": sources_for_llm}, indent=2)

    debug_log(f"[LLM INPUT]: System prompt length: {len(system_prompt)}, batch_size: {len(sources)}")
    debug_log(f"[LLM INPUT USER]: {user_message[:2000]}...")

    # Make LLM call
    client = anthropic.Anthropic()

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
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

    # Parse JSON response
    try:
        result = _parse_llm_response(response_text)

        assessments: list[CredibilityAssessment] = []
        for item in result.get("assessments", []):
            url = item.get("url", "")
            quality = item.get("source_quality", "crude")
            # Validate quality value
            if quality not in ("quality", "crude"):
                quality = "crude"

            assessments.append({
                "url": url,
                "source_quality": quality,
                "reason": item.get("reason", ""),
            })

        # Check if all sources got assessed
        assessed_urls = {a["url"] for a in assessments}
        for source in sources:
            if source["url"] not in assessed_urls:
                debug_log(f"[NODE: assess_credibility] Missing assessment for {source['url']}, defaulting to crude")
                assessments.append({
                    "url": source["url"],
                    "source_quality": "crude",
                    "reason": "No assessment returned by LLM",
                })

        return assessments

    except Exception as e:
        debug_log(f"[NODE: assess_credibility] ERROR parsing response: {e}", "error")
        # Default all to crude on parse error
        return [
            {
                "url": s["url"],
                "source_quality": "crude",
                "reason": f"LLM parse error: {str(e)[:50]}",
            }
            for s in sources
        ]


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
