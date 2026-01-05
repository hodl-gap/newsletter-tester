"""
Discover RSS Agent

Uses Claude API with web search and browsing tools to find RSS feeds
when preset URL testing fails.
"""

import json
import os
import re
from typing import TypedDict, Optional
from urllib.parse import urlparse

from dotenv import load_dotenv
import anthropic
import httpx

# Load environment variables
load_dotenv()

from src.utils import load_prompt_with_vars
from src.tracking import track_llm_cost, debug_log, track_time


class RSSDiscoveryResult(TypedDict):
    url: str
    status: str  # "available", "paywalled", "unavailable"
    feed_url: Optional[str]
    method: str  # "agent_search", "agent_browse"
    notes: Optional[str]


def web_search(query: str) -> str:
    """
    Perform a web search using DuckDuckGo HTML.
    Returns search results as text.
    """
    debug_log(f"[TOOL: web_search] Query: {query}")

    try:
        response = httpx.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": "Mozilla/5.0 (compatible; RSSBot/1.0)"},
            timeout=15,
        )
        response.raise_for_status()

        # Extract result snippets (basic parsing)
        text = response.text
        # Find result links and snippets
        results = []
        links = re.findall(r'class="result__a"[^>]*href="([^"]+)"[^>]*>([^<]+)', text)
        snippets = re.findall(r'class="result__snippet"[^>]*>([^<]+)', text)

        for i, (link, title) in enumerate(links[:5]):
            snippet = snippets[i] if i < len(snippets) else ""
            results.append(f"- {title}: {link}\n  {snippet}")

        result_text = "\n".join(results) if results else "No results found"
        debug_log(f"[TOOL: web_search] Found {len(results)} results")
        return result_text

    except Exception as e:
        debug_log(f"[TOOL: web_search] Error: {e}", "error")
        return f"Search failed: {e}"


def browse_url(url: str) -> str:
    """
    Fetch a URL and return its content.
    Looks specifically for RSS-related links.
    """
    debug_log(f"[TOOL: browse_url] URL: {url}")

    try:
        response = httpx.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; RSSBot/1.0)"},
            timeout=15,
            follow_redirects=True,
        )
        response.raise_for_status()

        html = response.text

        # Look for RSS/feed links
        rss_patterns = [
            r'<link[^>]+type=["\']application/rss\+xml["\'][^>]*href=["\']([^"\']+)["\']',
            r'<link[^>]+type=["\']application/atom\+xml["\'][^>]*href=["\']([^"\']+)["\']',
            r'<a[^>]+href=["\']([^"\']*(?:feed|rss|atom)[^"\']*)["\']',
        ]

        found_feeds = []
        for pattern in rss_patterns:
            matches = re.findall(pattern, html, re.IGNORECASE)
            found_feeds.extend(matches)

        if found_feeds:
            result = f"Found potential feed links:\n" + "\n".join(f"- {f}" for f in found_feeds[:10])
        else:
            result = "No RSS/feed links found in page HTML"

        debug_log(f"[TOOL: browse_url] Found {len(found_feeds)} potential feeds")
        return result

    except Exception as e:
        debug_log(f"[TOOL: browse_url] Error: {e}", "error")
        return f"Failed to browse: {e}"


# Tool definitions for Claude
TOOLS = [
    {
        "name": "web_search",
        "description": "Search the web for information about RSS feeds. Use this to find documentation or mentions of a site's RSS feed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "browse_url",
        "description": "Browse a URL to look for RSS feed links in the HTML. Use this to inspect a webpage for feed links.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to browse"
                }
            },
            "required": ["url"]
        }
    }
]


def execute_tool(name: str, input_data: dict) -> str:
    """Execute a tool and return its result."""
    if name == "web_search":
        return web_search(input_data["query"])
    elif name == "browse_url":
        return browse_url(input_data["url"])
    else:
        return f"Unknown tool: {name}"


def discover_rss_agent(url: str) -> RSSDiscoveryResult:
    """
    Use Claude agent to discover RSS feed for a URL.

    Args:
        url: Base URL to find RSS for.

    Returns:
        RSSDiscoveryResult with status and feed_url if found.
    """
    with track_time("discover_rss_agent"):
        debug_log("[NODE: discover_rss_agent] Entering")
        debug_log(f"[NODE: discover_rss_agent] Input URL: {url}")

        # Extract domain for search
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path

        # Load and format prompt
        system_prompt = load_prompt_with_vars(
            "discover_rss_agent_system_prompt.md",
            url=url,
            domain=domain,
        )

        debug_log(f"[LLM INPUT]: {system_prompt}")

        # Initialize Anthropic client
        client = anthropic.Anthropic()

        messages = [
            {"role": "user", "content": f"Find the RSS feed for: {url}"}
        ]

        # Agent loop
        max_iterations = 5
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            debug_log(f"[NODE: discover_rss_agent] Iteration {iteration}")

            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
                system=system_prompt,
                tools=TOOLS,
                messages=messages,
            )

            # Track cost
            track_llm_cost(
                model=response.model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )

            debug_log(f"[LLM OUTPUT]: {response.content}")

            # Check if we got a final text response
            if response.stop_reason == "end_turn":
                # Extract JSON from response
                for block in response.content:
                    if hasattr(block, "text"):
                        text = block.text
                        # Try to parse JSON from response
                        json_match = re.search(r'\{[^{}]*"status"[^{}]*\}', text, re.DOTALL)
                        if json_match:
                            try:
                                result_data = json.loads(json_match.group())
                                result: RSSDiscoveryResult = {
                                    "url": url,
                                    "status": result_data.get("status", "unavailable"),
                                    "feed_url": result_data.get("feed_url"),
                                    "method": result_data.get("method", "agent_search"),
                                    "notes": result_data.get("notes"),
                                }
                                debug_log(f"[NODE: discover_rss_agent] Output: {result}")
                                return result
                            except json.JSONDecodeError:
                                pass

                # No valid JSON found, return unavailable
                break

            # Handle tool use
            if response.stop_reason == "tool_use":
                # Add assistant response to messages
                messages.append({"role": "assistant", "content": response.content})

                # Execute tools and add results
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        debug_log(f"[NODE: discover_rss_agent] Tool call: {block.name}")
                        result = execute_tool(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })

                messages.append({"role": "user", "content": tool_results})

        # Default result if agent didn't return valid JSON
        result: RSSDiscoveryResult = {
            "url": url,
            "status": "unavailable",
            "feed_url": None,
            "method": "agent_search",
            "notes": "Agent could not determine RSS availability",
        }
        debug_log(f"[NODE: discover_rss_agent] Output: {result}")
        return result


def discover_rss_agent_batch(urls: list[str]) -> list[RSSDiscoveryResult]:
    """
    Discover RSS feeds for multiple URLs.

    Args:
        urls: List of URLs to process.

    Returns:
        List of RSSDiscoveryResult.
    """
    debug_log("[NODE: discover_rss_agent_batch] Entering")
    debug_log(f"[NODE: discover_rss_agent_batch] Input: {len(urls)} URLs")

    results = []
    for url in urls:
        result = discover_rss_agent(url)
        results.append(result)

    debug_log(f"[NODE: discover_rss_agent_batch] Output: {len(results)} results")
    return results


if __name__ == "__main__":
    # Test with a sample URL
    result = discover_rss_agent("https://www.theinformation.com")
    print(f"\n=== Result ===")
    print(json.dumps(result, indent=2))
