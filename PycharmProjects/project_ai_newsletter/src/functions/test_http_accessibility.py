"""
Test HTTP Accessibility Node

Tests whether sources can be accessed via HTTP and checks for bot protection.
"""

import time
from typing import TypedDict

import httpx

from src.tracking import debug_log, track_time


# Browser-like headers
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

REQUEST_TIMEOUT = 20


class AccessibilityResult(TypedDict):
    """Result of HTTP accessibility test."""
    url: str
    accessible: bool
    status_code: int | None
    blocked_by: str | None  # "cloudflare", "captcha", "js_redirect", None
    html_length: int
    requires_javascript: bool
    html_content: str | None  # Stored for later analysis
    error: str | None


def check_for_blocking(html: str) -> tuple[str | None, bool]:
    """
    Check if the response indicates bot protection or JS requirement.

    Args:
        html: HTML content

    Returns:
        Tuple of (blocked_by, requires_javascript)
    """
    html_lower = html.lower()

    # Cloudflare detection
    if (
        ('just a moment' in html_lower and ('cloudflare' in html_lower or 'cf-' in html_lower))
        or 'checking your browser' in html_lower
        or 'cf-browser-verification' in html_lower
        or 'cloudflare ray id' in html_lower
    ):
        return "cloudflare", False

    # General CAPTCHA/bot detection
    if (
        'captcha' in html_lower
        or ('robot' in html_lower and 'not a robot' in html_lower)
        or 'verify you are human' in html_lower
        or ('access denied' in html_lower and len(html) < 5000)
        or ('blocked' in html_lower and 'request' in html_lower and len(html) < 5000)
    ):
        return "captcha", False

    # JavaScript redirect detection (minimal HTML with JS redirect)
    if len(html) < 500:
        if 'window.location' in html_lower or 'location.href' in html_lower:
            return "js_redirect", True
        if '<noscript>' in html_lower:
            return None, True

    # Check for heavy JS requirement (minimal actual content)
    if len(html) > 1000:
        # Count actual text content vs script/style
        import re
        text_only = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        text_only = re.sub(r'<style[^>]*>.*?</style>', '', text_only, flags=re.DOTALL | re.IGNORECASE)
        text_only = re.sub(r'<[^>]+>', '', text_only)
        text_only = re.sub(r'\s+', ' ', text_only).strip()

        # If very little text content relative to HTML size, likely JS-heavy
        text_ratio = len(text_only) / len(html)
        if text_ratio < 0.05 and len(text_only) < 500:
            return None, True

    return None, False


def test_single_url(url: str) -> AccessibilityResult:
    """
    Test accessibility of a single URL.

    Args:
        url: URL to test

    Returns:
        AccessibilityResult with test details
    """
    try:
        response = httpx.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers=BROWSER_HEADERS,
            follow_redirects=True,
        )

        html = response.text
        blocked_by, requires_javascript = check_for_blocking(html)

        # Determine if accessible
        accessible = (
            response.status_code == 200
            and blocked_by is None
            and not requires_javascript
        )

        return AccessibilityResult(
            url=url,
            accessible=accessible,
            status_code=response.status_code,
            blocked_by=blocked_by,
            html_length=len(html),
            requires_javascript=requires_javascript,
            html_content=html if accessible or requires_javascript else None,
            error=None,
        )

    except httpx.TimeoutException:
        return AccessibilityResult(
            url=url,
            accessible=False,
            status_code=None,
            blocked_by=None,
            html_length=0,
            requires_javascript=False,
            html_content=None,
            error="Timeout",
        )
    except httpx.ConnectError as e:
        return AccessibilityResult(
            url=url,
            accessible=False,
            status_code=None,
            blocked_by=None,
            html_length=0,
            requires_javascript=False,
            html_content=None,
            error=f"Connection error: {str(e)[:100]}",
        )
    except Exception as e:
        return AccessibilityResult(
            url=url,
            accessible=False,
            status_code=None,
            blocked_by=None,
            html_length=0,
            requires_javascript=False,
            html_content=None,
            error=str(e)[:200],
        )


def test_http_accessibility(state: dict) -> dict:
    """
    Test HTTP accessibility for all sources.

    Args:
        state: Pipeline state with 'sources_to_test'

    Returns:
        Dict with 'accessibility_results' list
    """
    with track_time("test_http_accessibility"):
        debug_log("[NODE: test_http_accessibility] Entering")

        sources = state.get("sources_to_test", [])
        debug_log(f"[NODE: test_http_accessibility] Testing {len(sources)} sources")

        results: list[AccessibilityResult] = []

        for source in sources:
            url = source["url"]
            debug_log(f"[NODE: test_http_accessibility] Testing: {url}")

            result = test_single_url(url)
            results.append(result)

            # Log result
            if result["accessible"]:
                debug_log(f"[NODE: test_http_accessibility]   ACCESSIBLE ({result['html_length']:,} chars)")
            elif result["blocked_by"]:
                debug_log(f"[NODE: test_http_accessibility]   BLOCKED by {result['blocked_by'].upper()}")
            elif result["requires_javascript"]:
                debug_log(f"[NODE: test_http_accessibility]   REQUIRES JS")
            elif result["error"]:
                debug_log(f"[NODE: test_http_accessibility]   ERROR: {result['error']}")
            else:
                debug_log(f"[NODE: test_http_accessibility]   FAILED (status {result['status_code']})")

            # Rate limiting
            time.sleep(1)

        # Summary
        accessible_count = sum(1 for r in results if r["accessible"])
        blocked_count = sum(1 for r in results if r["blocked_by"])
        js_count = sum(1 for r in results if r["requires_javascript"])

        debug_log(f"[NODE: test_http_accessibility] Summary:")
        debug_log(f"[NODE: test_http_accessibility]   Accessible: {accessible_count}")
        debug_log(f"[NODE: test_http_accessibility]   Blocked: {blocked_count}")
        debug_log(f"[NODE: test_http_accessibility]   Requires JS: {js_count}")

        return {"accessibility_results": results}
