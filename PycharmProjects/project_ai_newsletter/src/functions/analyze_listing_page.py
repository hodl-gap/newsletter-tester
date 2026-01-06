"""
Analyze Listing Page Node

Uses LLM to analyze the structure of a news website's listing page
to understand how to find article links.
"""

import json
import re
from typing import TypedDict

from dotenv import load_dotenv
import anthropic

load_dotenv()

from src.utils import load_prompt
from src.tracking import track_llm_cost, debug_log, track_time


class ListingAnalysis(TypedDict):
    """Result of listing page analysis."""
    url: str
    has_article_links: bool
    article_url_pattern: str | None
    sample_article_urls: list[str]
    listing_type: str  # "blog", "news_grid", "magazine", "feed", "unknown"
    pagination_pattern: str | None
    confidence: float
    notes: str | None


def analyze_listing_page(state: dict) -> dict:
    """
    Analyze listing pages for accessible sources using LLM.

    Args:
        state: Pipeline state with 'accessibility_results'

    Returns:
        Dict with 'listing_analyses' list
    """
    with track_time("analyze_listing_page"):
        debug_log("[NODE: analyze_listing_page] Entering")

        accessibility_results = state.get("accessibility_results", [])

        # Filter to accessible sources (or JS-requiring sources we might still analyze)
        analyzable = [
            r for r in accessibility_results
            if r["accessible"] or r["requires_javascript"]
        ]

        debug_log(f"[NODE: analyze_listing_page] Analyzing {len(analyzable)} sources")

        analyses: list[ListingAnalysis] = []

        for result in analyzable:
            url = result["url"]
            html_content = result.get("html_content")

            if not html_content:
                debug_log(f"[NODE: analyze_listing_page] Skipping {url} - no HTML content")
                analyses.append(_empty_analysis(url, "No HTML content available"))
                continue

            debug_log(f"[NODE: analyze_listing_page] Analyzing: {url}")

            analysis = _analyze_with_llm(url, html_content)
            analyses.append(analysis)

            debug_log(f"[NODE: analyze_listing_page]   has_article_links: {analysis['has_article_links']}")
            debug_log(f"[NODE: analyze_listing_page]   listing_type: {analysis['listing_type']}")
            debug_log(f"[NODE: analyze_listing_page]   sample_urls: {len(analysis['sample_article_urls'])}")

        debug_log(f"[NODE: analyze_listing_page] Completed {len(analyses)} analyses")

        return {"listing_analyses": analyses}


def _empty_analysis(url: str, reason: str) -> ListingAnalysis:
    """Create an empty analysis result."""
    return ListingAnalysis(
        url=url,
        has_article_links=False,
        article_url_pattern=None,
        sample_article_urls=[],
        listing_type="unknown",
        pagination_pattern=None,
        confidence=0.0,
        notes=reason,
    )


def _analyze_with_llm(url: str, html_content: str) -> ListingAnalysis:
    """
    Use LLM to analyze the listing page structure.

    Args:
        url: Source URL
        html_content: HTML content of the page

    Returns:
        ListingAnalysis with discovered patterns
    """
    # Load system prompt
    system_prompt = load_prompt("analyze_listing_page_system_prompt.md")

    # Truncate HTML to fit in context window
    # Use 50k chars to ensure we capture <body> content (many sites have 10-15k in <head>)
    html_truncated = html_content[:50000]

    # Prepare user message
    user_message = f"""Analyze this listing page from {url}

HTML Content:
```html
{html_truncated}
```

Please analyze the structure and return JSON with article link patterns."""

    debug_log(f"[LLM INPUT]: analyze_listing_page for {url}, HTML: {len(html_truncated)} chars")

    # Make LLM call
    client = anthropic.Anthropic()

    try:
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
        debug_log(f"[LLM OUTPUT]: {response_text[:500]}...")

        # Parse JSON response
        result = _parse_llm_response(response_text)

        # Resolve relative URLs to absolute
        base_url = _get_base_url(url)
        sample_urls = result.get("sample_article_urls", [])
        resolved_urls = [_resolve_url(u, base_url) for u in sample_urls]

        return ListingAnalysis(
            url=url,
            has_article_links=result.get("has_article_links", False),
            article_url_pattern=result.get("article_url_pattern"),
            sample_article_urls=resolved_urls,
            listing_type=result.get("listing_type", "unknown"),
            pagination_pattern=result.get("pagination_pattern"),
            confidence=result.get("confidence", 0.5),
            notes=result.get("notes"),
        )

    except Exception as e:
        debug_log(f"[NODE: analyze_listing_page] ERROR analyzing {url}: {e}", "error")
        return _empty_analysis(url, f"LLM error: {str(e)[:100]}")


def _parse_llm_response(response_text: str) -> dict:
    """
    Parse LLM response, handling markdown code blocks and extra text.

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
        # Find the closing ``` and stop there
        json_lines = []
        for line in lines:
            if line.strip() == "```":
                break
            json_lines.append(line)
        clean_text = "\n".join(json_lines)

    # Try to find JSON object boundaries if there's extra text
    try:
        return json.loads(clean_text)
    except json.JSONDecodeError:
        # Try to extract just the JSON object
        start = clean_text.find("{")
        if start != -1:
            # Find matching closing brace
            depth = 0
            for i, char in enumerate(clean_text[start:], start):
                if char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        json_str = clean_text[start:i+1]
                        return json.loads(json_str)
        raise


def _get_base_url(url: str) -> str:
    """Extract base URL (protocol + domain) from URL."""
    match = re.match(r'(https?://[^/]+)', url)
    return match.group(1) if match else url


def _resolve_url(url: str, base_url: str) -> str:
    """Resolve relative URL to absolute."""
    if url.startswith("http"):
        return url
    elif url.startswith("//"):
        return "https:" + url
    elif url.startswith("/"):
        return base_url + url
    else:
        return base_url + "/" + url
