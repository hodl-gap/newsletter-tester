"""
Test alternative ways to get Reuters content since direct scraping is blocked.

Run with: python tests/test_reuters_alternatives.py
"""

import httpx
from bs4 import BeautifulSoup
import feedparser
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


HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
}


def test_reuters_rss_feeds():
    """Test if Reuters has any working RSS feeds."""
    print("\n" + "=" * 60)
    print("TEST 1: Reuters RSS Feeds")
    print("=" * 60)

    rss_urls = [
        "https://www.reuters.com/technology/rss",
        "https://www.reuters.com/rssFeed/technologyNews",
        "https://feeds.reuters.com/reuters/technologyNews",
        "https://www.reuters.com/arc/outboundfeeds/v3/all/?outputType=xml",
        "https://www.reutersagency.com/feed/",
    ]

    for url in rss_urls:
        print(f"\nTrying: {url}")
        try:
            feed = feedparser.parse(url)
            if feed.entries:
                print(f"  ✅ Found {len(feed.entries)} entries!")
                for entry in feed.entries[:3]:
                    print(f"    - {entry.get('title', 'No title')[:60]}...")
                return ScrapingResult(
                    method="reuters_rss",
                    success=True,
                    articles_found=len(feed.entries),
                    sample_titles=[e.get('title', '') for e in feed.entries[:5]],
                    sample_urls=[e.get('link', '') for e in feed.entries[:5]]
                )
            else:
                status = feed.get('status', 'unknown')
                print(f"  ❌ No entries (status: {status})")
        except Exception as e:
            print(f"  ❌ Error: {e}")

    return ScrapingResult(
        method="reuters_rss",
        success=False,
        articles_found=0,
        sample_titles=[],
        sample_urls=[],
        error="No working RSS feeds found"
    )


def test_wayback_machine():
    """Test fetching Reuters from Wayback Machine (archive.org)."""
    print("\n" + "=" * 60)
    print("TEST 2: Wayback Machine (archive.org)")
    print("=" * 60)

    # Get latest snapshot URL
    api_url = "https://archive.org/wayback/available?url=https://www.reuters.com/technology/"

    try:
        with httpx.Client(headers=HEADERS, timeout=30) as client:
            response = client.get(api_url)

        data = response.json()
        print(f"Wayback API response: {data}")

        if data.get("archived_snapshots", {}).get("closest"):
            snapshot = data["archived_snapshots"]["closest"]
            snapshot_url = snapshot["url"]
            timestamp = snapshot["timestamp"]
            print(f"✅ Found snapshot from {timestamp}")
            print(f"   URL: {snapshot_url}")

            # Fetch the archived page
            archive_response = client.get(snapshot_url)
            if archive_response.status_code == 200:
                soup = BeautifulSoup(archive_response.text, 'html.parser')
                titles = []
                for h in soup.find_all(['h2', 'h3']):
                    link = h.find('a')
                    if link:
                        text = link.get_text(strip=True)
                        if text and len(text) > 10:
                            titles.append(text)

                titles = list(dict.fromkeys(titles))[:10]
                print(f"   Titles found: {len(titles)}")
                for t in titles[:3]:
                    print(f"   - {t[:60]}...")

                return ScrapingResult(
                    method="wayback_machine",
                    success=len(titles) > 0,
                    articles_found=len(titles),
                    sample_titles=titles[:5],
                    sample_urls=[],
                    error=f"Note: Data from {timestamp} (may be stale)"
                )
        else:
            print("❌ No archived snapshots available")

    except Exception as e:
        print(f"❌ Error: {e}")

    return ScrapingResult(
        method="wayback_machine",
        success=False,
        articles_found=0,
        sample_titles=[],
        sample_urls=[],
        error="No archived snapshots available"
    )


def test_newsapi():
    """Test NewsAPI.org (has Reuters as source, but requires API key)."""
    print("\n" + "=" * 60)
    print("TEST 3: NewsAPI.org (check if Reuters available)")
    print("=" * 60)

    # Check sources endpoint (doesn't require API key)
    sources_url = "https://newsapi.org/v2/top-headlines/sources"

    try:
        with httpx.Client(headers=HEADERS, timeout=15) as client:
            response = client.get(sources_url)

        if response.status_code == 401:
            print("ℹ️  NewsAPI requires API key (free tier available)")
            print("   - Free: 100 requests/day")
            print("   - Has Reuters as source")
            print("   - Get key at: https://newsapi.org/register")

            return ScrapingResult(
                method="newsapi",
                success=False,
                articles_found=0,
                sample_titles=[],
                sample_urls=[],
                error="Requires API key (free tier: 100 req/day)"
            )
    except Exception as e:
        print(f"❌ Error: {e}")

    return ScrapingResult(
        method="newsapi",
        success=False,
        articles_found=0,
        sample_titles=[],
        sample_urls=[],
        error="Requires API key"
    )


def test_bing_news_rss():
    """Test Bing News RSS for Reuters content."""
    print("\n" + "=" * 60)
    print("TEST 4: Bing News RSS (Reuters AI content)")
    print("=" * 60)

    # Bing News RSS with site filter
    bing_url = "https://www.bing.com/news/search?q=site%3Areuters.com+artificial+intelligence&format=rss"

    try:
        feed = feedparser.parse(bing_url)
        print(f"Status: {feed.get('status', 'unknown')}")

        if feed.entries:
            print(f"✅ Found {len(feed.entries)} entries!")
            titles = []
            urls = []
            for entry in feed.entries[:10]:
                title = entry.get('title', '')
                link = entry.get('link', '')
                if title:
                    titles.append(title)
                    urls.append(link)
                    print(f"  - {title[:60]}...")
                    print(f"    URL: {link[:80]}...")

            return ScrapingResult(
                method="bing_news_rss",
                success=len(titles) > 0,
                articles_found=len(titles),
                sample_titles=titles[:5],
                sample_urls=urls[:5]
            )
        else:
            print("❌ No entries found")

    except Exception as e:
        print(f"❌ Error: {e}")

    return ScrapingResult(
        method="bing_news_rss",
        success=False,
        articles_found=0,
        sample_titles=[],
        sample_urls=[],
        error="No entries found"
    )


def test_duckduckgo_news():
    """Test DuckDuckGo news search."""
    print("\n" + "=" * 60)
    print("TEST 5: DuckDuckGo News API")
    print("=" * 60)

    # DDG doesn't have official API but we can try the lite version
    ddg_url = "https://duckduckgo.com/news.js?q=site:reuters.com+artificial+intelligence"

    try:
        with httpx.Client(headers=HEADERS, timeout=15) as client:
            response = client.get(ddg_url)

        print(f"Status: {response.status_code}")
        print(f"Content length: {len(response.text)}")

        if response.status_code == 200 and len(response.text) > 100:
            # DDG returns vqd token, not direct results
            print("ℹ️  DDG requires browser session for news")

    except Exception as e:
        print(f"❌ Error: {e}")

    return ScrapingResult(
        method="duckduckgo",
        success=False,
        articles_found=0,
        sample_titles=[],
        sample_urls=[],
        error="Requires browser session"
    )


def test_feedly_opml():
    """Check Feedly's public OPML for Reuters feeds."""
    print("\n" + "=" * 60)
    print("TEST 6: Check known working news aggregators")
    print("=" * 60)

    # Alternative news sources that cover AI and might have Reuters-level content
    alternatives = [
        ("TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/"),
        ("VentureBeat AI", "https://venturebeat.com/category/ai/feed/"),
        ("The Verge AI", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
        ("Ars Technica AI", "https://feeds.arstechnica.com/arstechnica/technology-lab"),
        ("Wired AI", "https://www.wired.com/feed/tag/ai/latest/rss"),
    ]

    working = []
    for name, url in alternatives:
        try:
            feed = feedparser.parse(url)
            if feed.entries:
                print(f"✅ {name}: {len(feed.entries)} entries")
                working.append((name, len(feed.entries)))
            else:
                print(f"❌ {name}: No entries")
        except Exception as e:
            print(f"❌ {name}: {e}")

    if working:
        return ScrapingResult(
            method="alternative_feeds",
            success=True,
            articles_found=sum(w[1] for w in working),
            sample_titles=[f"{w[0]}: {w[1]} articles" for w in working],
            sample_urls=[],
            error="These are alternatives to Reuters, not Reuters itself"
        )

    return ScrapingResult(
        method="alternative_feeds",
        success=False,
        articles_found=0,
        sample_titles=[],
        sample_urls=[],
        error="No working alternatives found"
    )


def print_summary(results: list[ScrapingResult]):
    """Print final summary."""
    print("\n" + "=" * 60)
    print("SUMMARY: Reuters Alternative Access Methods")
    print("=" * 60)

    for r in results:
        status = "✅" if r.success else "❌"
        print(f"\n{status} {r.method}: {r.articles_found} articles")
        if r.error:
            print(f"   Note: {r.error}")
        if r.sample_urls:
            print(f"   URLs work: Yes")

    print("\n" + "-" * 60)
    print("CONCLUSION:")
    print("-" * 60)

    successful = [r for r in results if r.success]
    if successful:
        for r in successful:
            print(f"✅ {r.method} works!")
    else:
        print("""
❌ Reuters blocks ALL automated access methods:
   - Direct scraping: Blocked by DataDome
   - RSS feeds: Not available
   - Google News: Only headlines, no URLs
   - Bing News RSS: May work (check results above)

📋 VIABLE OPTIONS:
   1. NewsAPI.org - Free tier (100 req/day), has Reuters
   2. Use alternative sources (TechCrunch, VentureBeat, etc.)
   3. Manual curation + RSS reader
   4. Reuters paid API (enterprise pricing)
        """)


if __name__ == "__main__":
    results = []

    results.append(test_reuters_rss_feeds())
    results.append(test_wayback_machine())
    results.append(test_newsapi())
    results.append(test_bing_news_rss())
    results.append(test_duckduckgo_news())
    results.append(test_feedly_opml())

    print_summary(results)
