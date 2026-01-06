"""
Generate Embeddings Node

Generates embeddings for articles using OpenAI's text-embedding-3-small model.
Embeddings are used for semantic similarity comparison in deduplication.
"""

import os
import numpy as np
from openai import OpenAI

from src.tracking import debug_log, track_time


# =============================================================================
# Configuration
# =============================================================================

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536
BATCH_SIZE = 100  # OpenAI recommends batching for efficiency


# =============================================================================
# Helper Functions
# =============================================================================

def create_embedding_text(article: dict) -> str:
    """
    Create text for embedding from article fields.

    Combines title and summary for a comprehensive representation.

    Args:
        article: Article dict with title and contents/summary.

    Returns:
        Formatted text string for embedding.
    """
    title = article.get("title", "")
    summary = article.get("contents", article.get("summary", article.get("description", "")))

    # Format: "TITLE: {title} SUMMARY: {summary}"
    return f"TITLE: {title} SUMMARY: {summary}"


def get_openai_client() -> OpenAI:
    """Get OpenAI client instance."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable not set")
    return OpenAI(api_key=api_key)


def embed_texts(texts: list[str]) -> list[np.ndarray]:
    """
    Generate embeddings for a list of texts using OpenAI API.

    Args:
        texts: List of text strings to embed.

    Returns:
        List of numpy arrays (embeddings).
    """
    if not texts:
        return []

    client = get_openai_client()
    embeddings = []

    # Process in batches
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i:i + BATCH_SIZE]

        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=batch
        )

        # Extract embeddings in order
        batch_embeddings = [
            np.array(item.embedding, dtype=np.float32)
            for item in sorted(response.data, key=lambda x: x.index)
        ]
        embeddings.extend(batch_embeddings)

        debug_log(f"[EMBED] Generated {len(batch)} embeddings (batch {i // BATCH_SIZE + 1})")

    return embeddings


# =============================================================================
# Node Function
# =============================================================================

def generate_embeddings(state: dict) -> dict:
    """
    Generate embeddings for all articles to be checked.

    Creates embedding vectors from title + summary text using
    OpenAI's text-embedding-3-small model.

    Args:
        state: Pipeline state with 'articles_to_check'

    Returns:
        Dict with:
        - 'articles_with_embeddings': Articles with embedding vectors attached
    """
    with track_time("generate_embeddings"):
        debug_log("[NODE: generate_embeddings] Entering")

        articles = state.get("articles_to_check", [])

        debug_log(f"[NODE: generate_embeddings] Input: {len(articles)} articles")

        if not articles:
            return {"articles_with_embeddings": []}

        # Create texts for embedding
        texts = [create_embedding_text(article) for article in articles]

        # Generate embeddings
        embeddings = embed_texts(texts)

        # Attach embeddings to articles
        articles_with_embeddings = []
        for article, embedding in zip(articles, embeddings):
            article_copy = article.copy()
            article_copy["embedding"] = embedding
            articles_with_embeddings.append(article_copy)

        debug_log(f"[NODE: generate_embeddings] Output: {len(articles_with_embeddings)} articles with embeddings")

        return {"articles_with_embeddings": articles_with_embeddings}
