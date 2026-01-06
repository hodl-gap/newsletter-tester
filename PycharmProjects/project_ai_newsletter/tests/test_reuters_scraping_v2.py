"""
Test advanced scraping approaches for Reuters Technology news.
Uses stealth techniques to bypass bot detection.

Run with: python tests/test_reuters_scraping_v2.py
"""

import time
from typing import Optional
from dataclasses import dataclass


@dataclass
class ScrapingResult:
    method: str
    success: bool
    articles_found: int
    sample_titles: list[str]
    error: Optional[str] = None


REUTERS_TECH_URL = "https://www.reuters.com/technology/"
REUTERS_AI_URL = "https://www.reuters.com/technology/artificial-intelligence/"


def test_playwright_stealth() -> ScrapingResult:
    """Test Playwright with stealth settings to avoid detection."""
    print("\n" + "=" * 60)
    print("TEST 1: Playwright with stealth/anti-detection settings")
    print("=" * 60)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return ScrapingResult(
            method="playwright_stealth",
            success=False,
            articles_found=0,
            sample_titles=[],
            error="Playwright not installed"
        )

    try:
        with sync_playwright() as p:
            # Launch with more realistic browser settings
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-infobars',
                    '--window-size=1920,1080',
                    '--start-maximized',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                ]
            )

            # Create context with full browser fingerprint
            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='en-US',
                timezone_id='America/New_York',
                geolocation={'latitude': 40.7128, 'longitude': -74.0060},
                permissions=['geolocation'],
                color_scheme='light',
                java_script_enabled=True,
            )

            page = context.new_page()

            # Add stealth scripts to hide automation
            page.add_init_script("""
                // Override webdriver property
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });

                // Override plugins
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });

                // Override languages
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en']
                });

                // Chrome specific
                window.chrome = {
                    runtime: {}
                };
            """)

            print(f"Navigating to {REUTERS_TECH_URL}...")
            response = page.goto(REUTERS_TECH_URL, wait_until="domcontentloaded", timeout=60000)

            print(f"Response status: {response.status if response else 'None'}")

            # Wait for potential JS rendering
            time.sleep(5)

            # Check current URL (might have redirected)
            current_url = page.url
            print(f"Current URL: {current_url}")

            # Get page content
            content = page.content()
            print(f"Page content length: {len(content)} bytes")

            # Check for common blocking patterns
            if "Access Denied" in content or "403" in content:
                print("⚠️  Access Denied detected")
            if "robot" in content.lower() or "captcha" in content.lower():
                print("⚠️  Bot detection triggered")

            # Take screenshot for debugging
            page.screenshot(path="tests/reuters_screenshot.png")
            print("Screenshot saved to tests/reuters_screenshot.png")

            # Try to find articles
            titles = []

            # Wait for articles to load
            try:
                page.wait_for_selector("article", timeout=10000)
            except:
                print("No <article> elements found after waiting")

            # Try various selectors
            selectors_to_try = [
                "article h3 a",
                "article h2 a",
                "[data-testid='Heading'] a",
                "[data-testid='TitleLink']",
                ".story-card h3",
                ".media-story-card__headline a",
                "a[href*='/technology/']",
            ]

            for selector in selectors_to_try:
                elements = page.query_selector_all(selector)
                if elements:
                    print(f"Found {len(elements)} elements with selector: {selector}")
                    for el in elements[:10]:
                        text = el.inner_text()
                        href = el.get_attribute("href")
                        if text and len(text) > 10 and href:
                            titles.append(text.strip())

            # Dedupe
            titles = list(dict.fromkeys(titles))[:10]

            print(f"\nTitles found: {len(titles)}")
            for i, t in enumerate(titles[:5], 1):
                print(f"  {i}. {t[:70]}...")

            browser.close()

            return ScrapingResult(
                method="playwright_stealth",
                success=len(titles) > 0,
                articles_found=len(titles),
                sample_titles=titles[:5],
                error=None if titles else f"No articles found (status: {response.status if response else 'unknown'})"
            )

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return ScrapingResult(
            method="playwright_stealth",
            success=False,
            articles_found=0,
            sample_titles=[],
            error=str(e)
        )


def test_playwright_headed() -> ScrapingResult:
    """Test with headed browser (visible window) - sometimes helps bypass detection."""
    print("\n" + "=" * 60)
    print("TEST 2: Playwright HEADED mode (visible browser)")
    print("=" * 60)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return ScrapingResult(
            method="playwright_headed",
            success=False,
            articles_found=0,
            sample_titles=[],
            error="Playwright not installed"
        )

    try:
        with sync_playwright() as p:
            # Try headed mode (visible browser window)
            browser = p.chromium.launch(
                headless=False,  # Visible window
                args=['--disable-blink-features=AutomationControlled']
            )

            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
            )
            page = context.new_page()

            print(f"Navigating to {REUTERS_TECH_URL} (headed mode)...")
            response = page.goto(REUTERS_TECH_URL, wait_until="networkidle", timeout=60000)

            print(f"Response status: {response.status if response else 'None'}")

            # Give time for manual inspection if needed
            time.sleep(5)

            content = page.content()
            print(f"Page content length: {len(content)} bytes")

            titles = []
            for selector in ["article h3 a", "article h2 a", "a[href*='/technology/']"]:
                elements = page.query_selector_all(selector)
                for el in elements[:10]:
                    text = el.inner_text()
                    if text and len(text) > 10:
                        titles.append(text.strip())

            titles = list(dict.fromkeys(titles))[:10]
            print(f"Titles found: {len(titles)}")

            browser.close()

            return ScrapingResult(
                method="playwright_headed",
                success=len(titles) > 0,
                articles_found=len(titles),
                sample_titles=titles[:5],
                error=None if titles else "No articles found"
            )

    except Exception as e:
        print(f"❌ Error: {e}")
        return ScrapingResult(
            method="playwright_headed",
            success=False,
            articles_found=0,
            sample_titles=[],
            error=str(e)
        )


def test_curl_simulation() -> ScrapingResult:
    """Test with curl-like request (simulating direct browser request)."""
    print("\n" + "=" * 60)
    print("TEST 3: Direct curl-style request")
    print("=" * 60)

    import subprocess

    try:
        # Use actual curl with full browser headers
        result = subprocess.run([
            'curl', '-s', '-w', '%{http_code}',
            '-H', 'User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
            '-H', 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            '-H', 'Accept-Language: en-US,en;q=0.9',
            '-H', 'Accept-Encoding: gzip, deflate, br',
            '-H', 'Connection: keep-alive',
            '--compressed',
            '-L',  # Follow redirects
            REUTERS_TECH_URL
        ], capture_output=True, text=True, timeout=30)

        output = result.stdout
        # Last 3 chars are status code from -w
        status_code = output[-3:] if len(output) >= 3 else "???"
        content = output[:-3]

        print(f"Status code: {status_code}")
        print(f"Content length: {len(content)} bytes")

        if status_code == "200":
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(content, 'html.parser')

            titles = []
            for h in soup.find_all(['h2', 'h3']):
                link = h.find('a')
                if link:
                    text = link.get_text(strip=True)
                    if text and len(text) > 10:
                        titles.append(text)

            titles = list(dict.fromkeys(titles))[:10]
            print(f"Titles found: {len(titles)}")

            return ScrapingResult(
                method="curl_direct",
                success=len(titles) > 0,
                articles_found=len(titles),
                sample_titles=titles[:5],
                error=None if titles else "No articles found"
            )
        else:
            return ScrapingResult(
                method="curl_direct",
                success=False,
                articles_found=0,
                sample_titles=[],
                error=f"HTTP {status_code}"
            )

    except Exception as e:
        print(f"❌ Error: {e}")
        return ScrapingResult(
            method="curl_direct",
            success=False,
            articles_found=0,
            sample_titles=[],
            error=str(e)
        )


def test_google_cache() -> ScrapingResult:
    """Test fetching from Google Cache."""
    print("\n" + "=" * 60)
    print("TEST 4: Google Cache")
    print("=" * 60)

    import httpx
    from bs4 import BeautifulSoup

    cache_url = f"https://webcache.googleusercontent.com/search?q=cache:{REUTERS_TECH_URL}"

    try:
        with httpx.Client(follow_redirects=True, timeout=30) as client:
            response = client.get(cache_url, headers={
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
            })

        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            titles = []
            for h in soup.find_all(['h2', 'h3']):
                link = h.find('a')
                if link:
                    text = link.get_text(strip=True)
                    if text and len(text) > 10:
                        titles.append(text)

            titles = list(dict.fromkeys(titles))[:10]
            print(f"Titles found: {len(titles)}")

            return ScrapingResult(
                method="google_cache",
                success=len(titles) > 0,
                articles_found=len(titles),
                sample_titles=titles[:5],
                error=None
            )
        else:
            return ScrapingResult(
                method="google_cache",
                success=False,
                articles_found=0,
                sample_titles=[],
                error=f"HTTP {response.status_code}"
            )

    except Exception as e:
        print(f"❌ Error: {e}")
        return ScrapingResult(
            method="google_cache",
            success=False,
            articles_found=0,
            sample_titles=[],
            error=str(e)
        )


def print_summary(results: list[ScrapingResult]):
    """Print summary of all scraping tests."""
    print("\n" + "=" * 60)
    print("SUMMARY: Reuters Advanced Scraping Results")
    print("=" * 60)

    for r in results:
        status = "✅ SUCCESS" if r.success else "❌ FAILED"
        print(f"\n{r.method}: {status}")
        print(f"  Articles found: {r.articles_found}")
        if r.error:
            print(f"  Error: {r.error}")
        if r.sample_titles:
            print(f"  Sample titles:")
            for t in r.sample_titles[:3]:
                print(f"    - {t[:60]}...")

    print("\n" + "-" * 60)
    successful = [r for r in results if r.success]
    if successful:
        best = max(successful, key=lambda x: x.articles_found)
        print(f"✅ RECOMMENDED: {best.method} ({best.articles_found} articles)")
    else:
        print("❌ Reuters actively blocks automated access")
        print("   Options:")
        print("   1. Reuters paid API subscription")
        print("   2. Use alternative AI news sources")
        print("   3. Newsletter email ingestion (if available)")


if __name__ == "__main__":
    results = []

    # Test 1: Stealth mode
    results.append(test_playwright_stealth())

    # Test 2: Headed mode (skip in CI environments)
    # results.append(test_playwright_headed())

    # Test 3: Direct curl
    results.append(test_curl_simulation())

    # Test 4: Google Cache
    results.append(test_google_cache())

    print_summary(results)
