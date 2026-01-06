"""
LLM Confirm Duplicates Node

Uses LLM to confirm whether ambiguous article pairs (similarity 0.75-0.90)
are true duplicates or unique articles.
"""

import json

from dotenv import load_dotenv
import anthropic

# Load environment variables
load_dotenv()

from src.utils import load_prompt
from src.tracking import track_llm_cost, debug_log, track_time


def llm_confirm_duplicates(state: dict) -> dict:
    """
    Use LLM to confirm ambiguous duplicate pairs.

    Takes pairs of articles with similarity scores between 0.75-0.90
    and asks the LLM to determine if they are true duplicates.

    Args:
        state: Pipeline state with:
            - 'unique_articles': Already confirmed unique
            - 'duplicate_articles': Already confirmed duplicates
            - 'ambiguous_pairs': Pairs needing confirmation

    Returns:
        Dict with:
        - 'confirmed_duplicates': All confirmed duplicates (auto + LLM)
        - 'confirmed_unique': All confirmed unique (auto + LLM)
    """
    with track_time("llm_confirm_duplicates"):
        debug_log("[NODE: llm_confirm_duplicates] Entering")

        ambiguous_pairs = state.get("ambiguous_pairs", [])
        unique_articles = list(state.get("unique_articles", []))
        duplicate_articles = list(state.get("duplicate_articles", []))

        debug_log(f"[NODE: llm_confirm_duplicates] {len(ambiguous_pairs)} pairs to confirm")

        if not ambiguous_pairs:
            # No ambiguous pairs - just pass through
            return {
                "confirmed_duplicates": duplicate_articles,
                "confirmed_unique": unique_articles
            }

        # Batch all ambiguous pairs into single LLM call
        pairs_for_llm = []
        for i, pair in enumerate(ambiguous_pairs):
            pairs_for_llm.append({
                "pair_index": i,
                "new_article": {
                    "title": pair["new_article"].get("title", ""),
                    "summary": pair["new_article"].get("contents", pair["new_article"].get("summary", "")),
                    "source": pair["new_article"].get("source", ""),
                    "date": pair["new_article"].get("date", pair["new_article"].get("pub_date", ""))
                },
                "existing_article": {
                    "title": pair["existing_article"].get("title", ""),
                    "summary": pair["existing_article"].get("summary", ""),
                    "source": pair["existing_article"].get("source", ""),
                    "date": pair["existing_article"].get("pub_date", "")
                },
                "similarity_score": pair["similarity"]
            })

        # Make LLM call
        confirmations = _call_llm_for_confirmation(pairs_for_llm)

        # Process results
        for i, confirmation in enumerate(confirmations):
            pair = ambiguous_pairs[i]

            if confirmation.get("is_duplicate", False):
                # Add to duplicates
                duplicate_articles.append({
                    "article": pair["new_article"],
                    "duplicate_of": pair["existing_article"],
                    "similarity": pair["similarity"],
                    "llm_reason": confirmation.get("reason", "LLM confirmed duplicate"),
                    "llm_confirmed": True
                })
                debug_log(
                    f"[NODE: llm_confirm_duplicates] LLM confirmed duplicate: "
                    f"{pair['new_article'].get('title', '')[:50]}..."
                )
            else:
                # Add to unique
                unique_articles.append(pair["new_article"])
                debug_log(
                    f"[NODE: llm_confirm_duplicates] LLM confirmed unique: "
                    f"{pair['new_article'].get('title', '')[:50]}..."
                )

        debug_log(
            f"[NODE: llm_confirm_duplicates] Final: "
            f"{len(unique_articles)} unique, {len(duplicate_articles)} duplicates"
        )

        return {
            "confirmed_duplicates": duplicate_articles,
            "confirmed_unique": unique_articles
        }


def _call_llm_for_confirmation(pairs: list[dict]) -> list[dict]:
    """
    Call LLM to confirm duplicate pairs.

    Args:
        pairs: List of pair dicts for LLM

    Returns:
        List of confirmation dicts with is_duplicate and reason
    """
    # Load system prompt
    system_prompt = load_prompt("confirm_duplicate_system_prompt.md")

    # Prepare user message
    user_message = json.dumps({"pairs": pairs}, indent=2)

    debug_log(f"[LLM INPUT]: Confirming {len(pairs)} ambiguous pairs")

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
        confirmations = result.get("confirmations", [])

        # Ensure we have confirmation for each pair (default to not duplicate)
        while len(confirmations) < len(pairs):
            confirmations.append({
                "pair_index": len(confirmations),
                "is_duplicate": False,
                "reason": "No LLM response - defaulting to unique"
            })

        return confirmations

    except Exception as e:
        debug_log(f"[NODE: llm_confirm_duplicates] ERROR parsing response: {e}", "error")
        # Default all to unique on parse error
        return [
            {"pair_index": i, "is_duplicate": False, "reason": f"Parse error: {e}"}
            for i in range(len(pairs))
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
