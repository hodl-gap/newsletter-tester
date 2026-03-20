"""Test browser-use Agent on various sites."""

import asyncio
import sys
from dotenv import load_dotenv

load_dotenv()

from browser_use import Agent, Browser, ChatAnthropic


async def test_site(url: str, site_name: str):
    """Test a site with browser-use Agent (LLM-driven browsing)."""

    print(f"Starting browser-use Agent on {site_name}...")
    print("-" * 60)

    # Use Claude Sonnet for better action handling
    llm = ChatAnthropic(model="claude-sonnet-4-20250514")

    # Non-headless so we can see what's happening
    browser = Browser(headless=False)

    task = f"""
    Go to {url} and:
    1. Wait for the page to fully load (there may be a loading screen or CAPTCHA)
    2. Once the page loads, extract the titles of the first 5 news headlines you can see
    3. Return them as a simple list

    IMPORTANT: Just return the article titles, one per line.
    """

    agent = Agent(
        task=task,
        llm=llm,
        browser=browser,
    )

    try:
        history = await agent.run(max_steps=20)

        print("\n" + "=" * 60)
        print("RESULT:")
        print("=" * 60)

        final = history.final_result()
        if final:
            print(f"\n{final}")
        else:
            print("No final result")

        print(f"\n📊 Total steps: {len(history.history)}")

    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    site = sys.argv[1] if len(sys.argv) > 1 else "economictimes"

    sites = {
        "reuters": ("https://www.reuters.com/technology/", "Reuters Tech"),
        "economictimes": ("https://tech.economictimes.indiatimes.com/", "Economic Times Tech"),
        "cnbc": ("https://www.cnbc.com/technology/", "CNBC Tech"),
        "nationalnews": ("https://www.thenationalnews.com/business/technology/", "The National News"),
        "scmp": ("https://www.scmp.com/tech", "SCMP Tech"),
    }

    if site in sites:
        url, name = sites[site]
        asyncio.run(test_site(url, name))
    else:
        print(f"Unknown site: {site}")
        print(f"Available: {', '.join(sites.keys())}")
