"""
Test HTML Fetch for Unavailable RSS Sources

Tests whether we can fetch HTML content directly from sources
that don't have RSS feeds available.

Criteria for inclusion:
- Status: "unavailable" (no RSS)
- Domain is accessible (no DNS issues)
- Is a news/media source with regular content
- Not known to have enterprise bot protection (e.g., DataDome)

Excluded:
- Paywalled sources (Bloomberg, FT, Axios, etc.)
- Reuters (DataDome protection)
- asiatechreview.com (domain inaccessible)
- hai.stanford.edu (annual report, not news)
- whitecase.com (law firm)
- foreignaffairsforum.ae (think tank)
- wsj.com (likely paywalled)
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import httpx
from dataclasses import dataclass
from typing import Optional

from src.functions.fetch_rss_content import fetch_article_content, extract_article_text, BROWSER_HEADERS


# Sources to test
SOURCES_TO_TEST = [
    {
        "name": "South China Morning Post",
        "url": "https://www.scmp.com/tech",
        "test_urls": [
            "https://www.scmp.com/tech",
            "https://www.scmp.com/tech/big-tech",
        ],
    },
    {
        "name": "CNBC China Connection",
        "url": "https://www.cnbc.com/newsletters/the-china-connection/",
        "test_urls": [
            "https://www.cnbc.com/newsletters/the-china-connection/",
            "https://www.cnbc.com/technology/",
        ],
    },
    {
        "name": "Euronews Next",
        "url": "https://www.euronews.com/next",
        "test_urls": [
            "https://www.euronews.com/next",
            "https://www.euronews.com/next/tech",
        ],
    },
    {
        "name": "Economic Times Tech",
        "url": "https://tech.economictimes.indiatimes.com/",
        "test_urls": [
            "https://tech.economictimes.indiatimes.com/",
            "https://tech.economictimes.indiatimes.com/news/artificial-intelligence",
        ],
    },
    {
        "name": "NASSCOM",
        "url": "https://nasscom.in/",
        "test_urls": [
            "https://nasscom.in/",
            "https://nasscom.in/knowledge-center/publications",
        ],
    },
    {
        "name": "Pulse News Korea",
        "url": "https://pulsenews.co.kr/",
        "test_urls": [
            "https://pulsenews.co.kr/",
            "https://pulsenews.co.kr/list.php?ct=a0600",  # IT section
        ],
    },
    {
        "name": "KED Global",
        "url": "https://kedglobal.com/",
        "test_urls": [
            "https://www.kedglobal.com/",  # Note: www subdomain
            "https://www.kedglobal.com/tech",
        ],
    },
    {
        "name": "The National News UAE",
        "url": "https://www.thenationalnews.com/business/technology/",
        "test_urls": [
            "https://www.thenationalnews.com/business/technology/",
            "https://www.thenationalnews.com/",
        ],
    },
    {
        "name": "Biz Chosun",
        "url": "https://biz.chosun.com/",
        "test_urls": [
            "https://biz.chosun.com/",
            "https://biz.chosun.com/it-science",
        ],
    },
    {
        "name": "EPNC Korea",
        "url": "https://www.epnc.co.kr/",
        "test_urls": [
            "https://www.epnc.co.kr/",
        ],
    },
    {
        "name": "The Rundown AI",
        "url": "https://www.rundown.ai/",
        "test_urls": [
            "https://www.rundown.ai/",
        ],
    },
    {
        "name": "Baobab Network",
        "url": "https://baobabnetwork.com/",
        "test_urls": [
            "https://baobabnetwork.com/",
            "https://baobabnetwork.com/blog/",
        ],
    },
    {
        "name": "Finance ME",
        "url": "https://financeme.com/",
        "test_urls": [
            "https://financeme.com/",
        ],
    },
]


@dataclass
class FetchResult:
    """Result of a fetch attempt."""
    url: str
    success: bool
    status_code: Optional[int]
    content_length: int
    is_cloudflare: bool
    is_captcha: bool
    error: Optional[str]
    extracted_text_length: int


def check_for_blocking(html: str) -> tuple[bool, bool]:
    """
    Check if the response indicates blocking.

    Returns:
        Tuple of (is_cloudflare, is_captcha)
    """
    html_lower = html.lower()

    # Cloudflare detection
    is_cloudflare = (
        ('just a moment' in html_lower and ('cloudflare' in html_lower or 'cf-' in html_lower))
        or 'checking your browser' in html_lower
        or 'cf-browser-verification' in html_lower
        or 'cloudflare ray id' in html_lower
    )

    # General CAPTCHA/bot detection
    is_captcha = (
        'captcha' in html_lower
        or 'robot' in html_lower and 'not a robot' in html_lower
        or 'verify you are human' in html_lower
        or 'access denied' in html_lower
        or 'blocked' in html_lower and 'request' in html_lower
    )

    return is_cloudflare, is_captcha


def test_fetch_url(url: str, timeout: int = 15) -> FetchResult:
    """
    Test fetching a single URL.

    Args:
        url: URL to fetch
        timeout: Request timeout in seconds

    Returns:
        FetchResult with details
    """
    try:
        response = httpx.get(
            url,
            timeout=timeout,
            headers=BROWSER_HEADERS,
            follow_redirects=True,
        )

        html = response.text
        is_cloudflare, is_captcha = check_for_blocking(html)

        # Try to extract article text
        extracted_text = ""
        if response.status_code == 200 and not is_cloudflare and not is_captcha:
            extracted_text = extract_article_text(html)

        return FetchResult(
            url=url,
            success=response.status_code == 200 and not is_cloudflare and not is_captcha,
            status_code=response.status_code,
            content_length=len(html),
            is_cloudflare=is_cloudflare,
            is_captcha=is_captcha,
            error=None,
            extracted_text_length=len(extracted_text),
        )

    except httpx.TimeoutException:
        return FetchResult(
            url=url,
            success=False,
            status_code=None,
            content_length=0,
            is_cloudflare=False,
            is_captcha=False,
            error="Timeout",
            extracted_text_length=0,
        )
    except httpx.ConnectError as e:
        return FetchResult(
            url=url,
            success=False,
            status_code=None,
            content_length=0,
            is_cloudflare=False,
            is_captcha=False,
            error=f"Connection error: {e}",
            extracted_text_length=0,
        )
    except Exception as e:
        return FetchResult(
            url=url,
            success=False,
            status_code=None,
            content_length=0,
            is_cloudflare=False,
            is_captcha=False,
            error=str(e),
            extracted_text_length=0,
        )


def test_source(source: dict) -> dict:
    """
    Test all URLs for a source.

    Args:
        source: Source dict with name, url, test_urls

    Returns:
        Dict with test results
    """
    results = []
    for url in source["test_urls"]:
        result = test_fetch_url(url)
        results.append(result)

    # Determine overall status
    any_success = any(r.success for r in results)
    all_cloudflare = all(r.is_cloudflare for r in results if r.status_code == 200)
    all_captcha = all(r.is_captcha for r in results if r.status_code == 200)

    return {
        "name": source["name"],
        "base_url": source["url"],
        "results": results,
        "http_fetch_works": any_success,
        "blocked_by": "cloudflare" if all_cloudflare else ("captcha" if all_captcha else None),
    }


def print_result(result: FetchResult, indent: str = "  "):
    """Print a single fetch result."""
    status = "✓" if result.success else "✗"

    if result.error:
        print(f"{indent}{status} {result.url}")
        print(f"{indent}  Error: {result.error}")
    else:
        blocking = ""
        if result.is_cloudflare:
            blocking = " [CLOUDFLARE]"
        elif result.is_captcha:
            blocking = " [CAPTCHA/BOT]"

        print(f"{indent}{status} {result.url}")
        print(f"{indent}  Status: {result.status_code}, HTML: {result.content_length:,} chars, Extracted: {result.extracted_text_length:,} chars{blocking}")


def run_tests():
    """Run all tests and print results."""
    print("=" * 70)
    print("HTML FETCH TEST FOR UNAVAILABLE RSS SOURCES")
    print("=" * 70)
    print()

    all_results = []

    for source in SOURCES_TO_TEST:
        print(f"Testing: {source['name']}")
        print(f"  Base URL: {source['url']}")
        print()

        result = test_source(source)
        all_results.append(result)

        for r in result["results"]:
            print_result(r)

        # Summary for this source
        if result["http_fetch_works"]:
            print(f"  → HTTP fetch WORKS")
        else:
            if result["blocked_by"]:
                print(f"  → BLOCKED by {result['blocked_by'].upper()}")
            else:
                print(f"  → HTTP fetch FAILED")

        print()
        print("-" * 70)
        print()

    # Overall summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print()

    works = [r for r in all_results if r["http_fetch_works"]]
    blocked = [r for r in all_results if r["blocked_by"]]
    failed = [r for r in all_results if not r["http_fetch_works"] and not r["blocked_by"]]

    print(f"Total sources tested: {len(all_results)}")
    print(f"  ✓ HTTP fetch works: {len(works)}")
    print(f"  ✗ Blocked (Cloudflare/Captcha): {len(blocked)}")
    print(f"  ✗ Failed (other): {len(failed)}")
    print()

    if works:
        print("Sources where HTTP fetch WORKS:")
        for r in works:
            print(f"  - {r['name']} ({r['base_url']})")
        print()

    if blocked:
        print("Sources BLOCKED by bot protection:")
        for r in blocked:
            print(f"  - {r['name']} ({r['base_url']}) [{r['blocked_by']}]")
        print()

    if failed:
        print("Sources FAILED (connection/other errors):")
        for r in failed:
            print(f"  - {r['name']} ({r['base_url']})")
        print()

    return all_results


if __name__ == "__main__":
    run_tests()
