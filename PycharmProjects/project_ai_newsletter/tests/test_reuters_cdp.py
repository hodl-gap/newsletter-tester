"""
Test Reuters scraping using Chrome DevTools Protocol (CDP).

This connects to an existing Chrome instance instead of launching a new one,
which often bypasses bot detection since it's a "real" browser.

SETUP:
1. Close all Chrome instances
2. Start Chrome with remote debugging:

   Linux:
   google-chrome --remote-debugging-port=9222 --user-data-dir="/tmp/chrome-debug" &

   Or with chromium:
   chromium --remote-debugging-port=9222 --user-data-dir="/tmp/chrome-debug" &

   Windows:
   chrome.exe --remote-debugging-port=9222 --user-data-dir="C:\chrome-debug"

   Mac:
   /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir="/tmp/chrome-debug" &

3. Run this script:
   python tests/test_reuters_cdp.py

"""

import subprocess
import time
import sys
from typing import Optional
from dataclasses import dataclass


@dataclass
class ScrapingResult:
    method: str
    success: bool
    articles_found: int
    sample_titles: list[str]
    sample_urls: list[str]
    error: Optional[str] = None


CDP_PORT = 9222
REUTERS_TECH_URL = "https://www.reuters.com/technology/"
REUTERS_AI_URL = "https://www.reuters.com/technology/artificial-intelligence/"


def check_chrome_running() -> bool:
    """Check if Chrome is running with remote debugging."""
    import httpx
    try:
        response = httpx.get(f"http://localhost:{CDP_PORT}/json/version", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Chrome detected: {data.get('Browser', 'unknown')}")
            return True
    except:
        pass
    return False


def start_chrome_debug():
    """Attempt to start Chrome with remote debugging."""
    print("Attempting to start Chrome with remote debugging...")

    # Try different Chrome executables
    chrome_commands = [
        ["google-chrome", "--remote-debugging-port=9222", "--user-data-dir=/tmp/chrome-debug"],
        ["chromium", "--remote-debugging-port=9222", "--user-data-dir=/tmp/chrome-debug"],
        ["chromium-browser", "--remote-debugging-port=9222", "--user-data-dir=/tmp/chrome-debug"],
    ]

    for cmd in chrome_commands:
        try:
            print(f"Trying: {cmd[0]}...")
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(3)  # Give Chrome time to start

            if check_chrome_running():
                return process
        except FileNotFoundError:
            continue

    return None


def test_cdp_connection() -> ScrapingResult:
    """Test connecting to existing Chrome via CDP."""
    print("\n" + "=" * 60)
    print("TEST: Chrome DevTools Protocol (CDP) Connection")
    print("=" * 60)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return ScrapingResult(
            method="cdp_connection",
            success=False,
            articles_found=0,
            sample_titles=[],
            sample_urls=[],
            error="Playwright not installed"
        )

    # Check if Chrome is already running with debug port
    chrome_process = None
    if not check_chrome_running():
        print(f"\n❌ No Chrome instance found on port {CDP_PORT}")
        print("   Attempting to start Chrome automatically...")
        chrome_process = start_chrome_debug()

        if not chrome_process or not check_chrome_running():
            print("\n⚠️  Could not start Chrome automatically.")
            print("   Please start Chrome manually with:")
            print(f"   google-chrome --remote-debugging-port={CDP_PORT} --user-data-dir=/tmp/chrome-debug &")
            return ScrapingResult(
                method="cdp_connection",
                success=False,
                articles_found=0,
                sample_titles=[],
                sample_urls=[],
                error="Chrome not running with remote debugging"
            )

    try:
        with sync_playwright() as p:
            # Connect to existing Chrome instance via CDP
            print(f"\nConnecting to Chrome on port {CDP_PORT}...")
            browser = p.chromium.connect_over_cdp(f"http://localhost:{CDP_PORT}")

            # Get existing context or create new one
            contexts = browser.contexts
            if contexts:
                context = contexts[0]
                print(f"Using existing context with {len(context.pages)} pages")
            else:
                context = browser.new_context()
                print("Created new context")

            # Create new page
            page = context.new_page()

            print(f"\nNavigating to {REUTERS_TECH_URL}...")
            response = page.goto(REUTERS_TECH_URL, wait_until="networkidle", timeout=60000)

            status = response.status if response else "unknown"
            print(f"Response status: {status}")

            # Wait for content
            time.sleep(3)

            # Check current URL
            current_url = page.url
            print(f"Current URL: {current_url}")

            # Get page content length
            content = page.content()
            print(f"Page content: {len(content)} bytes")

            # Take screenshot
            page.screenshot(path="tests/reuters_cdp_screenshot.png")
            print("Screenshot saved: tests/reuters_cdp_screenshot.png")

            # Check for block page
            if "Access blocked" in content or len(content) < 5000:
                print("⚠️  Still blocked or minimal content")
                page.close()
                return ScrapingResult(
                    method="cdp_connection",
                    success=False,
                    articles_found=0,
                    sample_titles=[],
                    sample_urls=[],
                    error=f"Blocked (status: {status}, content: {len(content)} bytes)"
                )

            # Try to find articles
            titles = []
            urls = []

            # Wait for articles to potentially load
            try:
                page.wait_for_selector("article", timeout=10000)
            except:
                pass

            # Various selectors to try
            selectors = [
                "article h3 a",
                "article h2 a",
                "[data-testid='Heading']",
                "[data-testid='TitleLink']",
                "a[href*='/technology/']",
                ".media-story-card__headline a",
            ]

            for selector in selectors:
                try:
                    elements = page.query_selector_all(selector)
                    if elements:
                        print(f"Found {len(elements)} elements with: {selector}")
                        for el in elements[:15]:
                            text = el.inner_text()
                            href = el.get_attribute("href")
                            if text and len(text) > 10:
                                titles.append(text.strip())
                                if href:
                                    if href.startswith("/"):
                                        href = f"https://www.reuters.com{href}"
                                    urls.append(href)
                except:
                    pass

            # Dedupe
            seen = set()
            unique_titles = []
            unique_urls = []
            for t, u in zip(titles, urls):
                if t not in seen:
                    seen.add(t)
                    unique_titles.append(t)
                    unique_urls.append(u)

            print(f"\nArticles found: {len(unique_titles)}")
            for i, (t, u) in enumerate(zip(unique_titles[:5], unique_urls[:5]), 1):
                print(f"  {i}. {t[:60]}...")
                print(f"     {u[:70]}...")

            page.close()

            return ScrapingResult(
                method="cdp_connection",
                success=len(unique_titles) > 0,
                articles_found=len(unique_titles),
                sample_titles=unique_titles[:5],
                sample_urls=unique_urls[:5],
                error=None if unique_titles else f"No articles found (status: {status})"
            )

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return ScrapingResult(
            method="cdp_connection",
            success=False,
            articles_found=0,
            sample_titles=[],
            sample_urls=[],
            error=str(e)
        )


def test_fetch_article_content(url: str) -> Optional[str]:
    """Test fetching full article content via CDP."""
    if not url:
        return None

    print(f"\n--- Testing article fetch: {url[:60]}... ---")

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://localhost:{CDP_PORT}")
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.new_page()

            page.goto(url, wait_until="networkidle", timeout=60000)
            time.sleep(2)

            # Extract article content
            content_selectors = [
                "article p",
                "[data-testid='paragraph']",
                ".article-body p",
            ]

            paragraphs = []
            for selector in content_selectors:
                elements = page.query_selector_all(selector)
                if elements:
                    for el in elements[:10]:
                        text = el.inner_text()
                        if text and len(text) > 50:
                            paragraphs.append(text)
                    break

            page.close()

            if paragraphs:
                content = "\n\n".join(paragraphs[:5])
                print(f"Content preview ({len(content)} chars):")
                print(content[:500] + "...")
                return content

    except Exception as e:
        print(f"Error fetching article: {e}")

    return None


if __name__ == "__main__":
    result = test_cdp_connection()

    print("\n" + "=" * 60)
    print("RESULT")
    print("=" * 60)

    if result.success:
        print(f"✅ SUCCESS: Found {result.articles_found} articles via CDP!")
        print("\nSample articles:")
        for t in result.sample_titles[:5]:
            print(f"  - {t}")

        # Try to fetch first article content
        if result.sample_urls:
            test_fetch_article_content(result.sample_urls[0])
    else:
        print(f"❌ FAILED: {result.error}")
        print("\nThe CDP method also failed. Reuters DataDome protection")
        print("likely uses additional signals beyond browser fingerprinting.")
