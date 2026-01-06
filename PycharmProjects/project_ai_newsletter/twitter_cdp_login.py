#!/usr/bin/env python3
"""
Twitter CDP Login Script

Connect to an existing Chrome browser via Chrome DevTools Protocol.
This avoids all automation detection since it's a real browser.

Step 1: Launch Chrome manually with remote debugging:

    Linux:
        google-chrome --remote-debugging-port=9222 --user-data-dir="$HOME/chrome-twitter"

    Windows:
        chrome.exe --remote-debugging-port=9222 --user-data-dir="C:\chrome-twitter"

    Mac:
        /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir="$HOME/chrome-twitter"

Step 2: Log in to Twitter manually in that browser

Step 3: Run this script to copy cookies to our chrome_data folder:
    python twitter_cdp_login.py

Usage:
    python twitter_cdp_login.py [--port 9222] [--test]
"""

import argparse
import json
import os
import shutil
from pathlib import Path
from playwright.sync_api import sync_playwright

BROWSER_DATA_DIR = Path(__file__).parent / "chrome_data"


def connect_and_copy_cookies(port: int = 9222):
    """Connect to Chrome via CDP and copy cookies."""

    cdp_url = f"http://localhost:{port}"
    print(f"Connecting to Chrome at {cdp_url}...")

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(cdp_url)
            print("Connected successfully!")

            # Get the default context (the one with all the cookies)
            contexts = browser.contexts
            if not contexts:
                print("No browser contexts found. Make sure you have a tab open.")
                return False

            context = contexts[0]

            # Get all cookies
            cookies = context.cookies()
            twitter_cookies = [c for c in cookies if 'twitter' in c.get('domain', '') or 'x.com' in c.get('domain', '')]

            print(f"Found {len(twitter_cookies)} Twitter/X cookies")

            if not twitter_cookies:
                print("\nNo Twitter cookies found!")
                print("Make sure you're logged in to Twitter in the Chrome browser.")
                return False

            # Check for auth cookies
            auth_cookie_names = ['auth_token', 'ct0', 'twid']
            found_auth = [c['name'] for c in twitter_cookies if c['name'] in auth_cookie_names]
            print(f"Auth cookies found: {found_auth}")

            if 'auth_token' not in found_auth:
                print("\nWARNING: 'auth_token' not found - you may not be logged in!")
                print("Please log in to Twitter in the Chrome browser first.")
                return False

            # Save cookies to a file that we can load later
            cookie_file = BROWSER_DATA_DIR / "twitter_cookies.json"
            os.makedirs(BROWSER_DATA_DIR, exist_ok=True)

            with open(cookie_file, 'w') as f:
                json.dump(twitter_cookies, f, indent=2)

            print(f"\nCookies saved to: {cookie_file}")
            print(f"Total cookies: {len(twitter_cookies)}")

            # Don't disconnect - leave the browser running
            return True

        except Exception as e:
            print(f"Failed to connect: {e}")
            print("\nMake sure Chrome is running with remote debugging enabled:")
            print(f"  google-chrome --remote-debugging-port={port} --user-data-dir=\"$HOME/chrome-twitter\"")
            return False


def test_scrape(port: int = 9222):
    """Test scraping using the CDP connection directly."""

    cdp_url = f"http://localhost:{port}"
    print(f"Testing scrape via CDP at {cdp_url}...")

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(cdp_url)
            context = browser.contexts[0]
            page = context.new_page()

            print("Navigating to @SawyerMerritt...")

            # Capture the API response
            with page.expect_response(
                lambda r: "UserTweets" in r.url and r.status == 200,
                timeout=15000
            ) as response_info:
                page.goto("https://x.com/SawyerMerritt", wait_until="domcontentloaded")

            response = response_info.value
            json_data = response.json()

            # Extract tweets
            tweets = extract_tweets(json_data)
            print(f"\nExtracted {len(tweets)} tweets")

            # Show recent tweets
            print("\nMost recent tweets:")
            sorted_tweets = sorted(tweets, key=lambda x: x.get('created_at', ''), reverse=True)
            for t in sorted_tweets[:10]:
                created = t.get('created_at', 'N/A')
                text = t.get('full_text', '')[:60]
                print(f"  {created[:20]} | {text}...")

            page.close()
            return True

        except Exception as e:
            print(f"Error: {e}")
            return False


def extract_tweets(data):
    """Recursively extract tweets from API response."""
    tweets = []
    if isinstance(data, dict):
        for key, value in data.items():
            if key == "full_text":
                tweets.append(data)
                break
            elif isinstance(value, (dict, list)):
                tweets.extend(extract_tweets(value))
    elif isinstance(data, list):
        for item in data:
            tweets.extend(extract_tweets(item))
    return tweets


def main():
    parser = argparse.ArgumentParser(description="Connect to Chrome via CDP for Twitter")
    parser.add_argument("--port", type=int, default=9222, help="Chrome debugging port (default: 9222)")
    parser.add_argument("--test", action="store_true", help="Test scrape after copying cookies")
    args = parser.parse_args()

    print("=" * 60)
    print("TWITTER CDP CONNECTION")
    print("=" * 60)
    print(f"\nStep 1: Make sure Chrome is running with remote debugging:")
    print(f"  google-chrome --remote-debugging-port={args.port} --user-data-dir=\"$HOME/chrome-twitter\"")
    print(f"\nStep 2: Log in to Twitter in that browser")
    print(f"\nStep 3: Press Enter to connect and copy cookies...")
    input()

    success = connect_and_copy_cookies(args.port)

    if success and args.test:
        print("\n" + "=" * 60)
        print("TESTING SCRAPE")
        print("=" * 60)
        test_scrape(args.port)

    if success:
        print("\n" + "=" * 60)
        print("SUCCESS!")
        print("=" * 60)
        print("\nCookies saved. Now update the scraper to load these cookies.")


if __name__ == "__main__":
    main()
