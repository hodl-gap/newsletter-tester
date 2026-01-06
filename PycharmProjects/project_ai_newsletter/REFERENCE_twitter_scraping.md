# Twitter/X API Interception Reference

> **NOTE**: This file is for reference only. Do not read unless explicitly asked.

---

## Overview

Twitter/X uses GraphQL API endpoints to fetch tweet data. By intercepting these API responses with Playwright, we can extract structured JSON data instead of parsing rendered HTML.

## Key API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `api.x.com/graphql/.../UserTweets` | Fetches tweets for a user profile |
| `api.x.com/graphql/.../UserByScreenName` | Fetches user profile data |
| `api.x.com/graphql/.../TweetDetail` | Fetches single tweet details |

## Working Code

```python
import json
from playwright.sync_api import sync_playwright

captured_responses = []

def handle_response(response):
    url = response.url
    # Capture Twitter API responses
    if 'api' in url or 'graphql' in url or 'UserTweets' in url or 'UserByScreenName' in url:
        try:
            if response.status == 200:
                content_type = response.headers.get('content-type', '')
                if 'json' in content_type:
                    body = response.json()
                    captured_responses.append({
                        'url': url,
                        'data': body
                    })
                    print(f"Captured: {url[:100]}...")
        except Exception as e:
            pass

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    )
    page = context.new_page()

    # Listen for responses
    page.on('response', handle_response)

    print("Navigating to https://x.com/Balancer...")
    try:
        page.goto('https://x.com/Balancer', wait_until='networkidle', timeout=30000)
        page.wait_for_timeout(5000)  # Wait for additional API calls
    except Exception as e:
        print(f"Navigation error: {e}")  # Timeout is okay, data is still captured

    browser.close()

# Save captured responses
with open('/tmp/twitter_api_responses.json', 'w') as f:
    json.dump(captured_responses, f, indent=2)
```

## Parsing UserTweets Response

```python
import json

with open('/tmp/twitter_api_responses.json', 'r') as f:
    responses = json.load(f)

for resp in responses:
    if 'UserTweets' in resp['url']:
        data = resp['data']

        # Navigate GraphQL structure
        timeline = data['data']['user']['result']['timeline']['timeline']['instructions']

        for instruction in timeline:
            entries = []

            if instruction.get('type') == 'TimelineAddEntries':
                entries = instruction.get('entries', [])
            elif instruction.get('type') == 'TimelinePinEntry':
                entries = [instruction.get('entry')]

            for entry in entries:
                if not entry:
                    continue
                content = entry.get('content', {})
                if content.get('entryType') == 'TimelineTimelineItem':
                    item = content.get('itemContent', {})
                    if item.get('itemType') == 'TimelineTweet':
                        tweet_result = item.get('tweet_results', {}).get('result', {})

                        # Extract tweet data
                        legacy = tweet_result.get('legacy', {})
                        full_text = legacy.get('full_text', '')
                        created_at = legacy.get('created_at', '')
                        tweet_id = tweet_result.get('rest_id', '')

                        # Engagement metrics
                        views = tweet_result.get('views', {}).get('count', '0')
                        likes = legacy.get('favorite_count', 0)
                        retweets = legacy.get('retweet_count', 0)
                        replies = legacy.get('reply_count', 0)

                        # Quoted tweet (if exists)
                        quoted = tweet_result.get('quoted_status_result', {}).get('result', {})
                        quoted_text = quoted.get('legacy', {}).get('full_text', '')

                        print(f"ID: {tweet_id}")
                        print(f"Date: {created_at}")
                        print(f"Text: {full_text}")
                        print(f"Views: {views}, Likes: {likes}, RTs: {retweets}")
```

## Response Structure

```
data
└── user
    └── result
        └── timeline (or timeline_v2)
            └── timeline
                └── instructions[]
                    ├── type: "TimelinePinEntry"
                    │   └── entry
                    └── type: "TimelineAddEntries"
                        └── entries[]
                            └── content
                                └── itemContent
                                    └── tweet_results
                                        └── result
                                            ├── rest_id (tweet ID)
                                            ├── legacy
                                            │   ├── full_text
                                            │   ├── created_at
                                            │   ├── favorite_count
                                            │   ├── retweet_count
                                            │   └── reply_count
                                            ├── views
                                            │   └── count
                                            └── quoted_status_result (if quote tweet)
```

## Notes

1. **Timeout is expected**: The page may timeout waiting for `networkidle`, but API responses are still captured before timeout
2. **User agent matters**: Some requests may be blocked without a proper user agent
3. **No authentication needed**: Public profiles can be scraped without login
4. **Rate limits apply**: Twitter may block IPs with too many requests

## Example Output (2025-12-30 @Balancer tweet)

```json
{
  "rest_id": "2005970761937477678",
  "legacy": {
    "created_at": "Tue Dec 30 11:54:33 +0000 2025",
    "full_text": "A new vlAURA market right on time. 🎄 \n\nNow protocols can deposit vote incentives for vlAURA or veBAL votes on @StakeDAOHQ  Votemarket.",
    "favorite_count": 17,
    "retweet_count": 4,
    "reply_count": 8
  },
  "views": {
    "count": "2386"
  }
}
```
