"""
Fetch Source Reputation Node

Uses web search to gather indirect reputation signals about news sources.
This approach works even for blocked/paywalled sites since it doesn't
require fetching the actual website.
"""

import time
from typing import TypedDict, Optional
from urllib.parse import urlparse

from duckduckgo_search import DDGS

from src.tracking import debug_log, track_time


# Configuration
SEARCH_DELAY = 2.0  # Seconds between search requests to avoid rate limiting
MAX_RESULTS = 8  # Number of search results to fetch


class SourceReputation(TypedDict):
    """Reputation information gathered from web search."""
    url: str
    domain: str
    publication_name: str  # Extracted or guessed from domain
    search_results: str  # Combined search results
    wikipedia_found: bool  # Whether Wikipedia page was found
    search_error: Optional[str]


def extract_domain(url: str) -> str:
    """Extract domain from URL."""
    parsed = urlparse(url)
    domain = parsed.netloc or parsed.path.split("/")[0]
    return domain.replace("www.", "")


def extract_publication_name(domain: str) -> str:
    """
    Extract a readable publication name from domain.

    Examples:
        techcrunch.com -> TechCrunch
        news.crunchbase.com -> Crunchbase News
        bbc.com -> BBC
    """
    # Remove TLD
    name = domain.split(".")[0]

    # Handle subdomains
    if "." in domain:
        parts = domain.split(".")
        if parts[0] in ("news", "tech", "biz", "www"):
            name = parts[1] if len(parts) > 1 else parts[0]
        else:
            name = parts[0]

    # Convert to title case with special handling
    special_cases = {
        "bbc": "BBC",
        "cnn": "CNN",
        "wsj": "WSJ",
        "ft": "Financial Times",
        "nyt": "New York Times",
        "scmp": "South China Morning Post",
        "techcrunch": "TechCrunch",
        "venturebeat": "VentureBeat",
        "kdnuggets": "KDnuggets",
        "36kr": "36Kr",
        "cnbc": "CNBC",
        "reuters": "Reuters",
        "bloomberg": "Bloomberg",
        "axios": "Axios",
        "forbes": "Forbes",
    }

    return special_cases.get(name.lower(), name.title())


def web_search(query: str) -> str:
    """
    Perform a web search using DDGS (DuckDuckGo Search).
    Returns search results as text.
    """
    debug_log(f"[TOOL: web_search] Query: {query}")

    # Add delay to avoid rate limiting
    time.sleep(SEARCH_DELAY)

    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=MAX_RESULTS))

        if not results:
            debug_log(f"[TOOL: web_search] No results found")
            return "No results found"

        # Format results
        formatted = []
        for r in results:
            title = r.get("title", "")
            body = r.get("body", "")
            formatted.append(f"• {title}\n  {body}")

        result_text = "\n\n".join(formatted)
        debug_log(f"[TOOL: web_search] Found {len(results)} results")
        return result_text

    except Exception as e:
        debug_log(f"[TOOL: web_search] Error: {e}", "error")
        return f"Search failed: {e}"


def check_wikipedia(publication_name: str) -> tuple[bool, str]:
    """
    Check if a publication has a Wikipedia page.

    Returns:
        Tuple of (found: bool, snippet: str)
    """
    query = f"{publication_name} site:wikipedia.org"
    debug_log(f"[TOOL: check_wikipedia] Query: {query}")

    # Add delay to avoid rate limiting
    time.sleep(SEARCH_DELAY)

    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))

        # Check if any result is from Wikipedia
        for r in results:
            href = r.get("href", "")
            if "wikipedia.org" in href.lower():
                snippet = r.get("body", "Wikipedia page exists")
                debug_log(f"[TOOL: check_wikipedia] Found Wikipedia page")
                return True, snippet[:500]

        debug_log(f"[TOOL: check_wikipedia] No Wikipedia page found")
        return False, ""

    except Exception as e:
        debug_log(f"[TOOL: check_wikipedia] Error: {e}", "error")
        return False, ""


def fetch_source_reputation(url: str) -> SourceReputation:
    """
    Fetch reputation information for a single source using web search.

    Args:
        url: URL of the news source.

    Returns:
        SourceReputation with search results and signals.
    """
    debug_log(f"[NODE: fetch_source_reputation] Fetching: {url}")

    domain = extract_domain(url)
    publication_name = extract_publication_name(domain)

    result: SourceReputation = {
        "url": url,
        "domain": domain,
        "publication_name": publication_name,
        "search_results": "",
        "wikipedia_found": False,
        "search_error": None,
    }

    try:
        # Search 1: General reputation search
        reputation_query = f'"{publication_name}" news publication'
        reputation_results = web_search(reputation_query)

        # Search 2: Check for Wikipedia page
        wiki_found, wiki_snippet = check_wikipedia(publication_name)
        result["wikipedia_found"] = wiki_found

        # Search 3: Look for ownership/parent company info
        ownership_query = f'"{publication_name}" owned by OR founded OR parent company'
        ownership_results = web_search(ownership_query)

        # Combine all search results
        combined_results = []

        if wiki_found:
            combined_results.append(f"=== Wikipedia ===\n{wiki_snippet}")

        combined_results.append(f"=== About {publication_name} ===\n{reputation_results}")
        combined_results.append(f"=== Ownership/History ===\n{ownership_results}")

        result["search_results"] = "\n\n".join(combined_results)

        debug_log(f"[NODE: fetch_source_reputation] Wikipedia: {wiki_found}, Results length: {len(result['search_results'])}")

    except Exception as e:
        debug_log(f"[NODE: fetch_source_reputation] Error: {e}", "error")
        result["search_error"] = str(e)

    return result


def fetch_source_reputation_batch(urls: list[str]) -> list[SourceReputation]:
    """
    Fetch reputation information for multiple URLs.

    Args:
        urls: List of source URLs.

    Returns:
        List of SourceReputation for each URL.
    """
    with track_time("fetch_source_reputation_batch"):
        debug_log(f"[NODE: fetch_source_reputation_batch] Entering")
        debug_log(f"[NODE: fetch_source_reputation_batch] Input: {len(urls)} URLs")

        results = []
        for i, url in enumerate(urls):
            debug_log(f"[NODE: fetch_source_reputation_batch] Processing {i+1}/{len(urls)}: {url}")
            result = fetch_source_reputation(url)
            results.append(result)

        wiki_count = sum(1 for r in results if r["wikipedia_found"])
        debug_log(f"[NODE: fetch_source_reputation_batch] Output: {len(results)} results, {wiki_count} with Wikipedia")

        return results


if __name__ == "__main__":
    # Test with sample URLs
    test_urls = [
        "https://techcrunch.com",
        "https://www.reuters.com/technology/",
        "https://36kr.com/",
        "https://somefakesite123.com/",
    ]

    for url in test_urls:
        result = fetch_source_reputation(url)
        print(f"\n{'='*60}")
        print(f"URL: {result['url']}")
        print(f"Domain: {result['domain']}")
        print(f"Publication: {result['publication_name']}")
        print(f"Wikipedia: {result['wikipedia_found']}")
        print(f"Search Results Preview: {result['search_results'][:500]}...")
