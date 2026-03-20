"""Simple browser-use test - just fetch page HTML."""

import asyncio
from dotenv import load_dotenv

load_dotenv()

from browser_use import Browser
from bs4 import BeautifulSoup


async def test_site_fetch(url: str, base_url: str, article_pattern: str):
    """Fetch a news site using browser-use (bypasses CAPTCHA)."""

    print(f"Starting browser to fetch {url} ...")
    print("-" * 60)

    # Use persistent profile + non-headless for Cloudflare sites
    browser = Browser(
        headless=False,  # Cloudflare often blocks headless
        disable_security=True,
        minimum_wait_page_load_time=5.0,
        wait_for_network_idle_page_load_time=10.0,
        user_data_dir="/tmp/browser-use-profile",  # Persistent profile
    )

    try:
        # Start the browser
        await browser.start()

        # Navigate to the page
        print(f"Navigating to {url} ...")
        await browser.navigate_to(url)

        # Wait for content to load (longer for Cloudflare challenge)
        print("Waiting for Cloudflare challenge to complete...")
        await asyncio.sleep(15)

        # Get the current page
        page = await browser.get_current_page()
        if page is None:
            print("❌ No page found")
            return []

        # Check current URL
        current_url = await page.get_url()
        print(f"Current URL: {current_url}")

        # Get page HTML using evaluate (requires arrow function format)
        html = await page.evaluate("() => document.documentElement.outerHTML")

        print(f"Page loaded! HTML length: {len(html)} chars")

        # Debug: show first 500 chars of HTML
        print(f"HTML preview: {html[:500]}...")
        print("=" * 60)

        # Parse with BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")

        # Find article links
        articles = []

        # Look for article links in various containers
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            text = link.get_text(strip=True)

            # Filter for article links
            if article_pattern in href and len(text) > 20:
                # Skip navigation/meta text
                if text.startswith("http"):
                    continue

                # Make absolute URL
                if href.startswith("/"):
                    href = base_url + href

                # Avoid duplicates
                if href not in [a["url"] for a in articles]:
                    articles.append({"title": text[:120], "url": href})

                if len(articles) >= 10:
                    break

        print(f"\n✅ Extracted {len(articles)} Articles:")
        print("-" * 60)
        for i, article in enumerate(articles[:10], 1):
            print(f"{i}. {article['title']}")
            print(f"   {article['url']}\n")

        await browser.stop()
        return articles

    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return []


async def test_reuters():
    """Test Reuters technology section."""
    return await test_site_fetch(
        url="https://www.reuters.com/technology/",
        base_url="https://www.reuters.com",
        article_pattern="/technology/"
    )


async def test_scmp():
    """Test SCMP tech section."""
    return await test_site_fetch(
        url="https://www.scmp.com/tech",
        base_url="https://www.scmp.com",
        article_pattern="/article/"
    )


if __name__ == "__main__":
    import sys
    site = sys.argv[1] if len(sys.argv) > 1 else "reuters"

    if site == "reuters":
        asyncio.run(test_reuters())
    elif site == "scmp":
        asyncio.run(test_scmp())
    else:
        print(f"Unknown site: {site}")
