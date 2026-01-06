"""
Compare Similarities Node

Compares new article embeddings against historical embeddings using
cosine similarity. Classifies articles as unique, duplicate, or ambiguous.
"""

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from src.tracking import debug_log, track_time


# =============================================================================
# Configuration - Hardcoded Thresholds
# =============================================================================

THRESHOLD_UNIQUE = 0.75      # Below this = definitely unique
THRESHOLD_DUPLICATE = 0.90   # Above this = definitely duplicate
# Between 0.75 and 0.90 = ambiguous, needs LLM confirmation


def compare_similarities(state: dict) -> dict:
    """
    Compare new article embeddings against historical embeddings.

    Uses cosine similarity to classify articles into three categories:
    - unique: similarity < 0.75 (keep, no LLM needed)
    - duplicate: similarity >= 0.90 (auto-discard, no LLM needed)
    - ambiguous: 0.75 <= similarity < 0.90 (needs LLM confirmation)

    Args:
        state: Pipeline state with:
            - 'articles_with_embeddings': New articles with embeddings
            - 'historical_articles': Historical articles from DB
            - 'is_first_run': True if no historical data

    Returns:
        Dict with:
        - 'unique_articles': Definitely unique articles
        - 'duplicate_articles': Auto-detected duplicates
        - 'ambiguous_pairs': Pairs needing LLM confirmation
    """
    with track_time("compare_similarities"):
        debug_log("[NODE: compare_similarities] Entering")

        new_articles = state.get("articles_with_embeddings", [])
        historical = state.get("historical_articles", [])
        is_first_run = state.get("is_first_run", False)

        debug_log(
            f"[NODE: compare_similarities] Input: {len(new_articles)} new, "
            f"{len(historical)} historical, first_run={is_first_run}"
        )

        # If first run or no history, all articles are unique
        if is_first_run or not historical:
            debug_log("[NODE: compare_similarities] No history - all articles are unique")
            return {
                "unique_articles": new_articles,
                "duplicate_articles": [],
                "ambiguous_pairs": []
            }

        # Build embedding matrices
        new_embeddings = np.array([a["embedding"] for a in new_articles])
        hist_embeddings = np.array([a["embedding"] for a in historical])

        debug_log(
            f"[NODE: compare_similarities] Computing {len(new_articles)} x {len(historical)} similarities"
        )

        # Compute all pairwise similarities
        similarities = cosine_similarity(new_embeddings, hist_embeddings)

        # Classify each new article
        unique = []
        duplicates = []
        ambiguous = []

        for i, article in enumerate(new_articles):
            max_sim = float(similarities[i].max())
            max_idx = int(similarities[i].argmax())

            if max_sim < THRESHOLD_UNIQUE:
                # Definitely unique
                unique.append(article)
            elif max_sim >= THRESHOLD_DUPLICATE:
                # Definitely duplicate
                duplicates.append({
                    "article": article,
                    "duplicate_of": historical[max_idx],
                    "similarity": max_sim
                })
            else:
                # Ambiguous - needs LLM confirmation
                ambiguous.append({
                    "new_article": article,
                    "existing_article": historical[max_idx],
                    "similarity": max_sim
                })

        debug_log(
            f"[NODE: compare_similarities] Results: "
            f"{len(unique)} unique, {len(duplicates)} duplicate, {len(ambiguous)} ambiguous"
        )

        return {
            "unique_articles": unique,
            "duplicate_articles": duplicates,
            "ambiguous_pairs": ambiguous
        }
