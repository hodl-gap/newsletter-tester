"""
Test different scraping approaches for Reuters Technology news.

Run with: pytest tests/test_reuters_scraping.py -v -s
Or directly: python tests/test_reuters_scraping.py
"""

import httpx
from bs4 import BeautifulSoup
import json
import time
from typing import Optional
from dataclasses import dataclass


@dataclass
class ScrapingResult:
    method: str
    success: bool
    articles_found: int
    sample_titles: list[str]
    sample_content: list[str]
    error: Optional[str] = None


REUTERS_TECH_URL = "https://www.reuters.com/technology/"
REUTERS_ARTICLE_URL = "https://www.reuters.com/technology/artificial-intelligence/"

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}


def test_httpx_simple() -> ScrapingResult:
    """Test 1: Simple httpx request with browser headers."""
    print("\n" + "=" * 60)
    print("TEST 1: Simple httpx with browser headers")
    print("=" * 60)

    try:
        with httpx.Client(headers=BROWSER_HEADERS, follow_redirects=True, timeout=30) as client:
            response = client.get(REUTERS_TECH_URL)

        print(f"Status code: {response.status_code}")
        print(f"Content length: {len(response.text)} bytes")

        # Check for Cloudflare or bot detection
        if "challenge" in response.text.lower() or "cloudflare" in response.text.lower():
            print("⚠️  Cloudflare challenge detected!")
            return ScrapingResult(
                method="httpx_simple",
                success=False,
                articles_found=0,
                sample_titles=[],
                sample_content=[],
                error="Cloudflare challenge detected"
            )

        # Parse HTML
        soup = BeautifulSoup(response.text, "html.parser")

        # Try to find article titles
        titles = []
        content_samples = []

        # Reuters uses various selectors for articles
        # Try data-testid attributes
        article_elements = soup.find_all("article")
        print(f"Found {len(article_elements)} <article> elements")

        # Try finding headlines
        headlines = soup.find_all(["h2", "h3"], class_=lambda x: x and "headline" in x.lower() if x else False)
        print(f"Found {len(headlines)} headline elements")

        # Try all h2/h3 with links
        for h in soup.find_all(["h2", "h3"]):
            link = h.find("a")
            if link and link.get("href", "").startswith("/"):
                titles.append(link.get_text(strip=True))
                if len(titles) >= 5:
                    break

        # Check for JSON-LD structured data
        json_ld = soup.find("script", type="application/ld+json")
        if json_ld:
            try:
                data = json.loads(json_ld.string)
                print(f"Found JSON-LD data: {type(data)}")
                if isinstance(data, list):
                    for item in data[:3]:
                        if item.get("@type") == "NewsArticle":
                            titles.append(item.get("headline", ""))
            except json.JSONDecodeError:
                pass

        # Check page content
        body_text = soup.get_text()
        has_content = len(body_text) > 5000

        print(f"\nTitles found: {len(titles)}")
        for i, t in enumerate(titles[:5], 1):
            print(f"  {i}. {t[:80]}...")

        success = len(titles) > 0

        return ScrapingResult(
            method="httpx_simple",
            success=success,
            articles_found=len(titles),
            sample_titles=titles[:5],
            sample_content=content_samples[:3],
            error=None if success else "No articles found - likely JS-rendered content"
        )

    except Exception as e:
        print(f"❌ Error: {e}")
        return ScrapingResult(
            method="httpx_simple",
            success=False,
            articles_found=0,
            sample_titles=[],
            sample_content=[],
            error=str(e)
        )


def test_playwright_scraping() -> ScrapingResult:
    """Test 2: Playwright headless browser scraping."""
    print("\n" + "=" * 60)
    print("TEST 2: Playwright headless browser")
    print("=" * 60)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("❌ Playwright not installed. Install with: pip install playwright && playwright install chromium")
        return ScrapingResult(
            method="playwright",
            success=False,
            articles_found=0,
            sample_titles=[],
            sample_content=[],
            error="Playwright not installed"
        )

    try:
        with sync_playwright() as p:
            # Launch browser
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=BROWSER_HEADERS["User-Agent"],
                viewport={"width": 1920, "height": 1080}
            )
            page = context.new_page()

            print(f"Navigating to {REUTERS_TECH_URL}...")
            page.goto(REUTERS_TECH_URL, wait_until="networkidle", timeout=60000)

            # Wait for content to load
            time.sleep(3)

            # Get page content
            content = page.content()
            print(f"Page content length: {len(content)} bytes")

            # Parse with BeautifulSoup
            soup = BeautifulSoup(content, "html.parser")

            titles = []
            content_samples = []

            # Find article links
            for h in soup.find_all(["h2", "h3"]):
                link = h.find("a")
                if link:
                    href = link.get("href", "")
                    if href.startswith("/") or "reuters.com" in href:
                        title = link.get_text(strip=True)
                        if title and len(title) > 10:
                            titles.append(title)

            # Also try direct selector
            headline_links = page.query_selector_all("a[data-testid='Heading']")
            print(f"Found {len(headline_links)} headline links via Playwright selector")

            for link in headline_links[:10]:
                text = link.inner_text()
                if text:
                    titles.append(text)

            # Dedupe
            titles = list(dict.fromkeys(titles))

            print(f"\nTitles found: {len(titles)}")
            for i, t in enumerate(titles[:5], 1):
                print(f"  {i}. {t[:80]}...")

            # Try to get an article's content
            if titles:
                # Find first article link
                first_link = page.query_selector("article a[href*='/technology/']")
                if first_link:
                    href = first_link.get_attribute("href")
                    if href:
                        if not href.startswith("http"):
                            href = f"https://www.reuters.com{href}"
                        print(f"\nFetching article: {href[:60]}...")

                        page.goto(href, wait_until="networkidle", timeout=60000)
                        time.sleep(2)

                        # Get article content
                        article_body = page.query_selector("article")
                        if article_body:
                            paragraphs = article_body.query_selector_all("p")
                            for p in paragraphs[:3]:
                                text = p.inner_text()
                                if len(text) > 50:
                                    content_samples.append(text)
                            print(f"Article content sample: {content_samples[0][:200] if content_samples else 'None'}...")

            browser.close()

            success = len(titles) > 0

            return ScrapingResult(
                method="playwright",
                success=success,
                articles_found=len(titles),
                sample_titles=titles[:5],
                sample_content=content_samples[:3],
                error=None if success else "No articles found"
            )

    except Exception as e:
        print(f"❌ Error: {e}")
        return ScrapingResult(
            method="playwright",
            success=False,
            articles_found=0,
            sample_titles=[],
            sample_content=[],
            error=str(e)
        )


def test_reuters_api() -> ScrapingResult:
    """Test 3: Check if Reuters has any public API endpoints."""
    print("\n" + "=" * 60)
    print("TEST 3: Reuters API endpoints")
    print("=" * 60)

    # Try common API patterns
    api_endpoints = [
        "https://www.reuters.com/pf/api/v3/content/fetch/articles-by-section-alias-or-id-v1?query=%7B%22section_id%22%3A%22%2Ftechnology%2F%22%2C%22size%22%3A20%7D",
        "https://www.reuters.com/arc/outboundfeeds/v3/all/?outputType=json&size=20",
    ]

    titles = []

    for endpoint in api_endpoints:
        try:
            print(f"Trying: {endpoint[:60]}...")
            with httpx.Client(headers=BROWSER_HEADERS, follow_redirects=True, timeout=15) as client:
                response = client.get(endpoint)

            if response.status_code == 200:
                try:
                    data = response.json()
                    print(f"✅ Got JSON response: {type(data)}")

                    # Try to extract articles
                    if isinstance(data, dict):
                        items = data.get("result", {}).get("articles", [])
                        if not items:
                            items = data.get("items", [])
                        if not items:
                            items = data.get("articles", [])

                        for item in items[:10]:
                            if isinstance(item, dict):
                                title = item.get("title") or item.get("headline") or item.get("basic", {}).get("headline")
                                if title:
                                    titles.append(title)

                        if titles:
                            print(f"Found {len(titles)} articles via API")
                            break

                except json.JSONDecodeError:
                    print("  Not JSON")
            else:
                print(f"  Status: {response.status_code}")

        except Exception as e:
            print(f"  Error: {e}")

    success = len(titles) > 0

    return ScrapingResult(
        method="reuters_api",
        success=success,
        articles_found=len(titles),
        sample_titles=titles[:5],
        sample_content=[],
        error=None if success else "No public API endpoints found"
    )


def print_summary(results: list[ScrapingResult]):
    """Print summary of all scraping tests."""
    print("\n" + "=" * 60)
    print("SUMMARY: Reuters Scraping Test Results")
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
        print(f"✅ RECOMMENDED METHOD: {best.method} ({best.articles_found} articles)")
    else:
        print("❌ No successful scraping method found")
        print("   Consider: Reuters API subscription or alternative sources")


if __name__ == "__main__":
    results = []

    # Test 1: Simple HTTP
    results.append(test_httpx_simple())

    # Test 2: Playwright
    results.append(test_playwright_scraping())

    # Test 3: API endpoints
    results.append(test_reuters_api())

    # Summary
    print_summary(results)
