"""Test browser-use on a blocked source (SCMP)."""

import asyncio
import json
from dotenv import load_dotenv

load_dotenv()

from browser_use import Agent, Browser, ChatAnthropic


async def test_scmp_scrape():
    """Test scraping SCMP tech section with browser-use."""

    # Use Claude Haiku for cost efficiency
    llm = ChatAnthropic(model="claude-haiku-4-5-20251001")

    # Configure browser (headless mode)
    browser = Browser(headless=True)

    task = """
    Go to https://www.scmp.com/tech and:
    1. Wait for the page to fully load
    2. Extract the titles and URLs of the first 5 article headlines you can see
    3. Return them as a JSON array with objects containing 'title' and 'url' keys

    IMPORTANT: Return ONLY the JSON array, nothing else.
    """

    agent = Agent(
        task=task,
        llm=llm,
        browser=browser,
    )

    print("Starting browser-use agent on SCMP (blocked source)...")
    print("-" * 60)

    try:
        history = await agent.run(max_steps=10)

        print("\n" + "=" * 60)
        print("RESULT:")
        print("=" * 60)

        # Get the final result
        final = history.final_result()
        if final:
            print(f"\nFinal Result:\n{final}")

            # Try to parse as JSON
            try:
                articles = json.loads(final)
                print(f"\n✅ Successfully extracted {len(articles)} articles!")
                for i, article in enumerate(articles, 1):
                    print(f"  {i}. {article.get('title', 'N/A')}")
                    print(f"     URL: {article.get('url', 'N/A')}")
            except json.JSONDecodeError:
                print("(Could not parse as JSON)")
        else:
            print("No final result returned")

        # Print step count
        print(f"\n📊 Total steps: {len(history.history)}")

    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_scmp_scrape())
