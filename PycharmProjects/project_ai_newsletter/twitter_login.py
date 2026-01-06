#!/usr/bin/env python3
"""
Twitter Login Script

Run this from a terminal with display (not headless) to log in to Twitter.
The session cookies will be saved to chrome_data/ for future scraping.

Usage:
    cd PycharmProjects/project_ai_newsletter
    source .venv/bin/activate
    python twitter_login.py
"""

import os
from pathlib import Path
from playwright.sync_api import sync_playwright

BROWSER_DATA_DIR = Path(__file__).parent / "chrome_data"


def main():
    browser_data_dir = str(BROWSER_DATA_DIR.resolve())
    os.makedirs(browser_data_dir, exist_ok=True)

    print("=" * 60)
    print("TWITTER LOGIN HELPER")
    print("=" * 60)
    print(f"\nBrowser data will be saved to: {browser_data_dir}")
    print("\nA browser window will open. Please:")
    print("  1. Log in to Twitter/X with your account")
    print("  2. After successful login, close the browser window")
    print("\nThe session will be saved for future scraping.\n")

    input("Press Enter to open browser...")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=browser_data_dir,
            headless=False,  # Visible browser for manual login
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            # Hide automation signals
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--no-first-run",
                "--no-default-browser-check",
            ],
            ignore_default_args=["--enable-automation"],
        )

        page = context.new_page()
        page.goto("https://x.com/login")

        print("\nBrowser opened. Please log in to Twitter.")
        print("Close the browser window when done.\n")

        # Wait for user to close browser
        try:
            page.wait_for_event("close", timeout=300000)  # 5 min timeout
        except:
            pass

        context.close()

    print("\n" + "=" * 60)
    print("LOGIN COMPLETE")
    print("=" * 60)
    print(f"\nSession saved to: {browser_data_dir}")
    print("\nYou can now run the Twitter scraper:")
    print("  python -c \"import twitter_layer1_orchestrator; twitter_layer1_orchestrator.run()\"")
    print()


if __name__ == "__main__":
    main()
