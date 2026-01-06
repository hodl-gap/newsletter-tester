"""
Analyze Article Page Node

Uses LLM to analyze the structure of an article page
to understand how to extract content, title, date, etc.
"""

import json
import re
from typing import TypedDict

from dotenv import load_dotenv
import anthropic
import httpx

load_dotenv()

from src.utils import load_prompt
from src.tracking import track_llm_cost, debug_log, track_time


# Browser-like headers
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


class SampleExtracted(TypedDict):
    """Sample content extracted from article."""
    title: str
    content_preview: str  # First 500 chars
    date: str | None
    author: str | None


class ArticleAnalysis(TypedDict):
    """Result of article page analysis."""
    url: str  # Original source URL (not sample article URL)
    sample_article_url: str | None
    has_full_content: bool
    title_selector: str | None
    content_selector: str | None
    date_selector: str | None
    date_format: str | None
    author_selector: str | None
    sample_extracted: SampleExtracted | None
    confidence: float
    notes: str | None


def analyze_article_page(state: dict) -> dict:
    """
    Analyze article pages using sample URLs from listing analysis.

    Args:
        state: Pipeline state with 'listing_analyses'

    Returns:
        Dict with 'article_analyses' list
    """
    with track_time("analyze_article_page"):
        debug_log("[NODE: analyze_article_page] Entering")

        listing_analyses = state.get("listing_analyses", [])

        # Filter to sources that have article links
        analyzable = [
            a for a in listing_analyses
            if a["has_article_links"] and a["sample_article_urls"]
        ]

        debug_log(f"[NODE: analyze_article_page] Analyzing {len(analyzable)} sources with article links")

        analyses: list[ArticleAnalysis] = []

        for listing in analyzable:
            url = listing["url"]
            sample_urls = listing["sample_article_urls"]

            debug_log(f"[NODE: analyze_article_page] Analyzing: {url}")
            debug_log(f"[NODE: analyze_article_page]   Sample URLs: {sample_urls[:2]}")

            # Try to fetch and analyze a sample article
            analysis = _analyze_sample_article(url, sample_urls)
            analyses.append(analysis)

            debug_log(f"[NODE: analyze_article_page]   has_full_content: {analysis['has_full_content']}")
            debug_log(f"[NODE: analyze_article_page]   confidence: {analysis['confidence']}")

        # Also create empty analyses for sources without article links
        sources_analyzed = {a["url"] for a in analyses}
        for listing in listing_analyses:
            if listing["url"] not in sources_analyzed:
                analyses.append(_empty_analysis(listing["url"], "No article links found in listing"))

        debug_log(f"[NODE: analyze_article_page] Completed {len(analyses)} analyses")

        return {"article_analyses": analyses}


def _empty_analysis(url: str, reason: str) -> ArticleAnalysis:
    """Create an empty analysis result."""
    return ArticleAnalysis(
        url=url,
        sample_article_url=None,
        has_full_content=False,
        title_selector=None,
        content_selector=None,
        date_selector=None,
        date_format=None,
        author_selector=None,
        sample_extracted=None,
        confidence=0.0,
        notes=reason,
    )


def _analyze_sample_article(source_url: str, sample_urls: list[str]) -> ArticleAnalysis:
    """
    Fetch a sample article and analyze its structure with LLM.

    Args:
        source_url: Original source URL
        sample_urls: List of sample article URLs to try

    Returns:
        ArticleAnalysis with discovered patterns
    """
    # Try each sample URL until one works
    html_content = None
    used_url = None

    for article_url in sample_urls[:3]:  # Try up to 3 URLs
        debug_log(f"[NODE: analyze_article_page] Fetching: {article_url}")

        try:
            response = httpx.get(
                article_url,
                timeout=15,
                headers=BROWSER_HEADERS,
                follow_redirects=True,
            )

            if response.status_code == 200:
                html_content = response.text
                used_url = article_url

                # Check for actual bot protection (blocked pages are short with no content)
                html_lower = html_content.lower()
                html_len = len(html_content)
                is_blocked = False

                # Actual blocked pages are typically short (<10k) and contain challenge keywords
                # Real article pages have lots of content even if they include recaptcha for comments
                if html_len < 10000:
                    # Cloudflare challenge page indicators
                    if 'just a moment' in html_lower and 'cloudflare' in html_lower:
                        is_blocked = True
                    elif 'cf-challenge' in html_lower or 'challenge-form' in html_lower:
                        is_blocked = True
                    # CAPTCHA challenge pages (not just comment forms)
                    elif 'recaptcha' in html_lower and '<article' not in html_lower:
                        is_blocked = True
                    elif 'hcaptcha' in html_lower and '<article' not in html_lower:
                        is_blocked = True
                    elif html_len < 3000 and 'captcha' in html_lower:
                        is_blocked = True

                if is_blocked:
                    debug_log(f"[NODE: analyze_article_page]   Blocked ({html_len} chars), trying next URL")
                    html_content = None
                    continue

                break

        except Exception as e:
            debug_log(f"[NODE: analyze_article_page]   Error: {e}")
            continue

    if not html_content:
        return _empty_analysis(source_url, "Could not fetch any sample article")

    # Analyze with LLM
    return _analyze_with_llm(source_url, used_url, html_content)


def _analyze_with_llm(source_url: str, article_url: str, html_content: str) -> ArticleAnalysis:
    """
    Use LLM to analyze the article page structure.

    Args:
        source_url: Original source URL
        article_url: Sample article URL
        html_content: HTML content of the article

    Returns:
        ArticleAnalysis with discovered patterns
    """
    # Load system prompt
    system_prompt = load_prompt("analyze_article_page_system_prompt.md")

    # Truncate HTML to fit in context window
    # Use 30k chars to ensure we capture article body content
    html_truncated = html_content[:30000]

    # Prepare user message
    user_message = f"""Analyze this article page from {article_url}

HTML Content:
```html
{html_truncated}
```

Please analyze the structure and return JSON with content extraction patterns."""

    debug_log(f"[LLM INPUT]: analyze_article_page for {source_url}, HTML: {len(html_truncated)} chars")

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

        # Extract sample_extracted if present
        sample = result.get("sample_extracted")
        sample_extracted = None
        if sample:
            sample_extracted = SampleExtracted(
                title=sample.get("title", ""),
                content_preview=sample.get("content_preview", "")[:500],
                date=sample.get("date"),
                author=sample.get("author"),
            )

        return ArticleAnalysis(
            url=source_url,
            sample_article_url=article_url,
            has_full_content=result.get("has_full_content", False),
            title_selector=result.get("title_selector"),
            content_selector=result.get("content_selector"),
            date_selector=result.get("date_selector"),
            date_format=result.get("date_format"),
            author_selector=result.get("author_selector"),
            sample_extracted=sample_extracted,
            confidence=result.get("confidence", 0.5),
            notes=result.get("notes"),
        )

    except Exception as e:
        debug_log(f"[NODE: analyze_article_page] ERROR analyzing {source_url}: {e}", "error")
        return _empty_analysis(source_url, f"LLM error: {str(e)[:100]}")


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
