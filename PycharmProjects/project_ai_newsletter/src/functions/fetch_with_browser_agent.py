"""
Fetch With Browser Agent Node

Uses browser-use Agent (LLM-driven browsing) to scrape articles from
sources blocked by CAPTCHA/Cloudflare.
"""

import asyncio
import json
from datetime import datetime
from typing import TypedDict, Optional

from src.tracking import debug_log, track_time, track_llm_cost


class ExtractedArticle(TypedDict):
    """Article extracted by browser-use Agent."""
    url: str
    title: str
    content: str
    date: Optional[str]
    source_name: str
    source_url: str


async def fetch_with_browser_agent(state: dict) -> dict:
    """
    Fetch articles using browser-use Agent (LLM-driven browsing).

    For each enabled source:
    1. Navigate to listing page
    2. Agent extracts article headlines and URLs
    3. For each article, agent extracts title, date, and content
    4. Returns structured article data

    Args:
        state: Pipeline state with:
            - 'browser_use_sources': List of enabled sources
            - 'browser_use_settings': Settings dict

    Returns:
        Dict with:
            - 'extracted_articles': List of extracted articles
            - 'browser_use_failures': List of failed sources
    """
    with track_time("fetch_with_browser_agent"):
        debug_log("[NODE: fetch_with_browser_agent] Entering")

        sources = state.get("browser_use_sources", [])
        settings = state.get("browser_use_settings", {})

        if not sources:
            debug_log("[NODE: fetch_with_browser_agent] No sources to process")
            return {"extracted_articles": [], "browser_use_failures": []}

        max_articles = settings.get("max_articles_per_source", 5)
        model = settings.get("model", "claude-sonnet-4-20250514")
        headless = settings.get("headless", False)

        debug_log(f"[NODE: fetch_with_browser_agent] Processing {len(sources)} sources")
        debug_log(f"[NODE: fetch_with_browser_agent] Model: {model}, Max articles: {max_articles}")

        # Import browser-use components
        try:
            from browser_use import Agent, Browser, ChatAnthropic
        except ImportError:
            debug_log("[NODE: fetch_with_browser_agent] browser-use not installed", "error")
            return {
                "extracted_articles": [],
                "browser_use_failures": [{"error": "browser-use not installed"}]
            }

        all_articles: list[ExtractedArticle] = []
        failures: list[dict] = []

        # Initialize LLM
        llm = ChatAnthropic(model=model)

        # Process each source
        for source in sources:
            url = source["url"]
            name = source["name"]

            debug_log(f"[NODE: fetch_with_browser_agent] Processing: {name} ({url})")

            try:
                articles = await _scrape_source_with_agent(
                    url=url,
                    source_name=name,
                    llm=llm,
                    max_articles=max_articles,
                    headless=headless,
                )

                all_articles.extend(articles)
                debug_log(f"[NODE: fetch_with_browser_agent]   Extracted {len(articles)} articles from {name}")

            except Exception as e:
                debug_log(f"[NODE: fetch_with_browser_agent]   Failed: {type(e).__name__}: {e}", "error")
                failures.append({
                    "url": url,
                    "name": name,
                    "error": str(e),
                    "timestamp": datetime.now().isoformat(),
                })

            # Rate limiting between sources
            if source != sources[-1]:
                debug_log("[NODE: fetch_with_browser_agent] Waiting 30s before next source...")
                await asyncio.sleep(30)

        debug_log(f"[NODE: fetch_with_browser_agent] Total extracted: {len(all_articles)} articles")
        debug_log(f"[NODE: fetch_with_browser_agent] Failures: {len(failures)}")

        return {
            "extracted_articles": all_articles,
            "browser_use_failures": failures,
        }


async def _scrape_source_with_agent(
    url: str,
    source_name: str,
    llm,
    max_articles: int,
    headless: bool,
) -> list[ExtractedArticle]:
    """
    Scrape a single source using browser-use Agent.

    Args:
        url: Source listing page URL
        source_name: Human-readable source name
        llm: ChatAnthropic instance
        max_articles: Max articles to extract
        headless: Whether to run headless

    Returns:
        List of extracted articles
    """
    from browser_use import Agent, Browser

    # Initialize browser
    browser = Browser(headless=headless)

    task = f"""
    Go to {url} and:
    1. Wait for the page to fully load (there may be a loading screen or CAPTCHA - wait for it)
    2. Find the first {max_articles} news article headlines on the page
    3. For each article, extract:
       - title: The headline text
       - url: The full article URL
       - date: Publication date if visible (format: YYYY-MM-DD)
       - content: A brief snippet or description (first 500 chars if available)

    Return ONLY a valid JSON array with objects containing these fields:
    [
      {{"title": "...", "url": "https://...", "date": "2026-01-12", "content": "..."}},
      ...
    ]

    IMPORTANT:
    - Return ONLY the JSON array, no other text
    - URLs must be complete (include https://)
    - If date is not visible, use null
    - If content is not visible from listing page, use empty string
    """

    agent = Agent(
        task=task,
        llm=llm,
        browser=browser,
    )

    try:
        history = await agent.run(max_steps=25)
        result = history.final_result()

        if not result:
            debug_log(f"[_scrape_source_with_agent] No result from agent for {source_name}")
            return []

        # Parse JSON result
        articles_data = _parse_agent_result(result)

        # Convert to ExtractedArticle format
        articles: list[ExtractedArticle] = []
        for item in articles_data:
            article_url = item.get("url", "")

            # Make URL absolute if needed
            if article_url and not article_url.startswith("http"):
                base_url = url.rstrip("/")
                if not article_url.startswith("/"):
                    article_url = "/" + article_url
                article_url = base_url.split("/")[0] + "//" + base_url.split("/")[2] + article_url

            articles.append(ExtractedArticle(
                url=article_url,
                title=item.get("title", ""),
                content=item.get("content", ""),
                date=item.get("date"),
                source_name=source_name,
                source_url=url,
            ))

        return articles

    finally:
        # Cleanup
        try:
            await browser.stop()
        except Exception:
            pass


def _parse_agent_result(result: str) -> list[dict]:
    """
    Parse JSON result from browser-use Agent.

    Handles various edge cases like markdown code blocks.

    Args:
        result: Raw result string from agent

    Returns:
        List of article dicts
    """
    if not result:
        return []

    # Clean up result
    result = result.strip()

    # Remove markdown code block markers if present
    if result.startswith("```"):
        lines = result.split("\n")
        # Remove first line (```json or ```)
        lines = lines[1:]
        # Remove last line if it's ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        result = "\n".join(lines)

    # Try to find JSON array in result
    try:
        # Direct parse
        data = json.loads(result)
        if isinstance(data, list):
            return data
        return []
    except json.JSONDecodeError:
        pass

    # Try to extract JSON array from text
    import re
    json_match = re.search(r'\[[\s\S]*\]', result)
    if json_match:
        try:
            data = json.loads(json_match.group())
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass

    debug_log(f"[_parse_agent_result] Failed to parse result: {result[:200]}...", "warning")
    return []


# Synchronous wrapper for use in LangGraph
def fetch_with_browser_agent_sync(state: dict) -> dict:
    """
    Synchronous wrapper for fetch_with_browser_agent.

    Use this in LangGraph pipelines that don't support async nodes.
    """
    return asyncio.run(fetch_with_browser_agent(state))
