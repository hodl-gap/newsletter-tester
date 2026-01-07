# Project Status

**Last Updated:** 2026-01-07

## Current Phase

HTML Layer 2 - Content Scraping: **COMPLETE** (2026-01-06)
HTML Layer 1 - Scrapability Discovery: **COMPLETE** (2026-01-06)
Layer 3 - Deduplication: **COMPLETE** (2026-01-06)
Layer 2 - Content Aggregation: **COMPLETE & TESTED**

## Layer 0: Source Quality Assessment - DISABLED (2026-01-06)

**Status: DISABLED** - Not currently in use due to reliability issues with DuckDuckGo search.

### Original Implementation (2026-01-05)

New Layer 0 runs **before** Layer 1 to assess source credibility using web search.

### Pipeline
```
load_urls → fetch_source_reputation → assess_credibility → save_quality_results
```

### Features
- Uses DuckDuckGo search (DDGS package) to gather reputation signals
- Searches for: publication info, Wikipedia page, ownership/history
- LLM (Claude Sonnet) assesses credibility based on search results + pre-trained knowledge
- Outputs `source_quality: "quality"` or `"crude"` per source
- Results saved to `data/source_quality.json`

### Latest Run Results
- **Total:** 54 sources
- **Quality:** 41 (76%)
- **Crude:** 13 (24%)
- **Cost:** ~$0.57

### Integration with Layer 1
- Layer 1 reads from `source_quality.json` if it exists
- Only processes sources marked as `"quality"`
- Falls back to `input_urls.json` if Layer 0 hasn't been run

### Files Created
- `layer0_orchestrator.py` - Main orchestrator
- `src/functions/fetch_source_reputation.py` - Web search for reputation signals
- `src/functions/assess_credibility.py` - LLM batch assessment
- `prompts/assess_credibility_system_prompt.md` - Credibility criteria

### Known Limitations

1. **DuckDuckGo search returns regionally-biased results**
   - DDGS often returns Chinese/Korean search results instead of English
   - Publication names may match unrelated content (e.g., "Axios" → Axios JS library)
   - Mitigation: Prompt instructs LLM to ignore irrelevant results and use pre-trained knowledge

2. **Wikipedia detection unreliable**
   - `site:wikipedia.org` searches often return no results even for major publications
   - 0/54 Wikipedia pages detected in latest run despite many publications having pages
   - LLM compensates using its training knowledge

3. **False negatives for lesser-known publications**
   - Regional/niche publications without strong English web presence may be marked "crude"
   - Examples: pulsenews.co.kr (Maeil Business), kedglobal.com (Korea Economic Daily)
   - Manual review recommended for edge cases

4. **Rate limiting**
   - 2-second delay between searches to avoid DuckDuckGo blocking
   - Full run takes ~10 minutes for 54 sources (162 searches)

5. **Spam/copypasta detection not implemented**
   - Would require RSS content analysis (Layer 1 dependency)
   - Planned as future enhancement

---

## Layer 1: RSS Discovery - COMPLETE

- **Input:** 58 newsletter URLs
- **Output:** 31 available feeds discovered
- **Results:** `data/rss_availability.json`
- **Cost:** ~$0.025 per run

### RSS Directory Scanning - IMPLEMENTED (2026-01-06)

Layer 1 now scans RSS directory pages (e.g., `/about/rss`, `/feeds`) to discover topic-specific feeds that use non-standard URL patterns.

**Problem Solved:**
- Fox News tech feed at `moxie.foxnews.com/google-publisher/tech.xml` was not discoverable via standard preset paths
- Many sites list all available feeds on directory pages

**Implementation:**
- New node `scan_rss_directories` runs after `test_main_rss`
- Scans common paths: `/about/rss`, `/about/feeds`, `/feeds`, `/help/rss`, `/rss-feeds`
- Parses HTML for feed links matching topic keywords (tech, AI, science)
- Validates discovered feed URLs
- No LLM cost (pure HTTP + regex)

**New fields in `rss_availability.json`:**
- `tech_feed_url: string | null` - Technology-specific feed
- `science_feed_url: string | null` - Science-specific feed
- `directory_page_url: string | null` - URL where feeds were discovered

**Feed Selection Logic:**
- For non-AI-focused sites: prefer `tech_feed_url` > `ai_feed_url` > `main_feed_url`
- For AI-focused sites: use `main_feed_url` (all content is relevant)

**Example (Fox News):**
```json
{
  "url": "https://www.foxnews.com/",
  "main_feed_url": "https://www.foxnews.com/rss",
  "tech_feed_url": "https://moxie.foxnews.com/google-publisher/tech.xml",
  "science_feed_url": "https://moxie.foxnews.com/google-publisher/science.xml",
  "directory_page_url": "https://www.foxnews.com/about/rss",
  "recommended_feed": "tech_feed_url",
  "recommended_feed_url": "https://moxie.foxnews.com/google-publisher/tech.xml",
  "method": "directory_scan"
}
```

**Pipeline Flow (updated):**
```
load_urls -> test_main_rss -> scan_rss_directories -> test_ai_category ->
discover_with_agent -> classify_all_feeds -> merge_results -> save_results
```

### Full Content Detection - IMPLEMENTED (2026-01-05)

Layer 1 now detects whether RSS feeds include `<content:encoded>` and whether HTTP fetch works for articles.

**New fields in `rss_availability.json`:**
- `has_full_content: boolean` - Whether RSS has content:encoded
- `http_fetch_works: boolean | null` - Whether article URLs can be fetched via HTTP (null if not tested, i.e., has full content)

**Summary stats added:**
- `with_full_content` - Count of sources with RSS full content
- `with_http_fetch` - Count of sources where HTTP fetch works
- `no_content_access` - Count of sources with neither (e.g., Cloudflare blocked)

### Feed Freshness Check - IMPLEMENTED (2026-01-05)

Layer 1 now validates freshness of AI-specific feeds and falls back to main feed if stale.

**Problem Solved:**
- Some AI tag/category feeds (e.g., Crunchbase AI tag) are not maintained by publishers
- Crunchbase AI tag feed was returning articles from July 2024 instead of current content

**Implementation:**
- `extract_latest_date()` extracts most recent article date from RSS/Atom feeds
- `is_feed_fresh()` checks if feed is within 7 days (configurable via `max_stale_days`)
- `determine_recommended_feed()` falls back to main feed if AI feed is stale

**New fields in `rss_availability.json`:**
- `main_feed_latest_date: string | null` - ISO date of latest article in main feed
- `ai_feed_latest_date: string | null` - ISO date of latest article in AI feed
- `fallback_reason: string | null` - Why main feed was used (e.g., "stale_ai_feed")

**Example:**
```json
{
  "url": "https://news.crunchbase.com/",
  "ai_feed_url": "https://news.crunchbase.com/tag/artificial-intelligence/feed/",
  "ai_feed_latest_date": "2024-07-17",
  "main_feed_latest_date": "2026-01-02",
  "recommended_feed_url": "https://news.crunchbase.com/feed",
  "fallback_reason": "stale_ai_feed"
}
```

### Layer 1 Re-Run Behavior

**Important:** Layer 1 is NOT incremental - it re-checks ALL sources every run.

**Behavior:**
1. `load_urls` loads ALL URLs from `input_urls.json`
2. All pipeline nodes (test_main_rss, test_ai_category, etc.) run for every URL
3. `save_results` **merges** new results with existing `rss_availability.json`:
   - Existing entries are updated with fresh data
   - New entries are added
   - Old entries not in current run are preserved (not deleted)
4. Use `url_filter` to limit which sources get re-checked

**Why this matters:**
- Old entries may lack newer fields (e.g., `ai_feed_latest_date`, `fallback_reason`)
- To get freshness check for old entries, re-run Layer 1 for those sources
- Example: `rss_orchestrator.run(url_filter=['techcabal'])` to update one source

**Example of stale entry (pre-freshness-check):**
```json
{
  "url": "https://techcabal.com/",
  "recommended_feed": "ai_feed_url",
  "ai_feed_latest_date": null,       // Missing - entry is old
  "fallback_reason": null            // Missing - entry is old
}
```

**After re-running Layer 1:**
```json
{
  "url": "https://techcabal.com/",
  "recommended_feed": "main_feed_url",
  "ai_feed_latest_date": "2025-12-25",
  "fallback_reason": "stale_ai_feed"  // AI feed was stale, fell back
}
```

### HTTP Article Fetch - IMPLEMENTED (2026-01-05)

Layer 2 now automatically fetches article HTML for sources where:
- RSS does NOT have `content:encoded`
- HTTP fetch is confirmed to work (tested during Layer 1 discovery)

**Implementation:**
- `fetch_rss_content.py` receives `http_fetch_works` flag from Layer 1
- When flag is True and no RSS content, fetches article URL with browser headers
- Extracts main content from `<article>` or `<main>` tags
- Falls back to description if fetch fails

**Known blocked sources (Cloudflare JS challenge):**
- AI Business
- Others TBD (will be detected during Layer 1 run)

---

## HTML Layer 1: Scrapability Discovery - COMPLETE (2026-01-06)

Automated pipeline to analyze "unavailable" sources from RSS Layer 1 and determine if they can be scraped via HTTP.

### Architecture

```
RSS Layer 1 (existing)
    │
    ├── status: "available" → rss_availability.json → RSS Layer 2
    │
    └── status: "unavailable" ──┐
                                │
                                ▼
                    ┌───────────────────────┐
                    │    HTML Layer 1       │
                    │  (Scrapability Check) │
                    └───────────┬───────────┘
                                │
                    ┌───────────┴───────────┐
                    │                       │
              scrapable: true         scrapable: false
                    │                       │
                    ▼                       ▼
           html_availability.json      (excluded)
                    │
                    ▼
              HTML Layer 2 (future)
```

### Pipeline Flow

```
load_unavailable_sources → test_http_accessibility → analyze_listing_page →
analyze_article_page → classify_html_source → merge_html_results →
save_html_availability
```

### Features

1. **Source Filtering**
   - Reads from `rss_availability.json`, filters `status == "unavailable"`
   - Excludes known-blocked sources (Reuters/DataDome, WSJ/paywalled)
   - Excludes non-news sources (law firms, think tanks, annual reports)

2. **HTTP Accessibility Testing**
   - Tests HTTP fetch with browser-like headers
   - Detects bot protection: Cloudflare challenge, CAPTCHA, JS-only redirects
   - Reports HTML length and status code

3. **LLM-Powered Listing Page Analysis**
   - Uses Claude Haiku to analyze homepage HTML structure
   - Identifies article URL patterns (regex)
   - Extracts sample article URLs
   - Classifies listing type (news_grid, magazine, blog)

4. **LLM-Powered Article Page Analysis**
   - Fetches sample article from discovered URLs
   - Identifies CSS selectors for extraction:
     - Title selector
     - Content selector
     - Date selector (+ format)
     - Author selector
   - Extracts sample content to verify extraction works

5. **Source Classification**
   - `scrapable` - Full HTTP access, article links + content extractable
   - `requires_js` - Needs Playwright for JavaScript rendering
   - `blocked` - CAPTCHA, Cloudflare, or JS-redirect protection
   - `not_scrapable` - Inaccessible or no article structure found

### Test Results (2026-01-06)

| Status | Count | Sources |
|--------|-------|---------|
| **Scrapable** | 4 | Rundown AI, Pulse News Korea, EPNC Korea, Biz Chosun |
| **Blocked** | 6 | SCMP, CNBC, Economic Times, Finance ME, The National News, Baobab Network |
| **Not Scrapable** | 3 | KED Global (SSL), NASSCOM (502), Euronews (SPA) |

**Scrapable Sources with Full Extraction Config:**

| Source | Article Pattern | Confidence |
|--------|----------------|------------|
| rundown.ai | `/articles/[a-z0-9\-]+` | 93.5% |
| pulsenews.co.kr | `/news/english/\d+` | 95% |
| epnc.co.kr | `/news/articleView.html?idxno=\d+` | 95% |
| biz.chosun.com | `/[a-z_]+/[a-z_]+/\d{4}/\d{2}/\d{2}/[A-Z0-9]+/` | 51%* |

*Biz Chosun has listing config but article extraction needs verification.

### Files Created

| File | Description |
|------|-------------|
| `html_layer1_orchestrator.py` | Main orchestrator |
| `src/functions/load_unavailable_sources.py` | Load from rss_availability.json |
| `src/functions/test_http_accessibility.py` | Bot protection detection |
| `src/functions/analyze_listing_page.py` | LLM listing analysis |
| `src/functions/analyze_article_page.py` | LLM article analysis |
| `src/functions/classify_html_source.py` | Source classification |
| `src/functions/merge_html_results.py` | Result merging |
| `src/functions/save_html_availability.py` | Save output |
| `prompts/analyze_listing_page_system_prompt.md` | Listing analysis prompt |
| `prompts/analyze_article_page_system_prompt.md` | Article analysis prompt |

### Output

**File:** `data/html_availability.json`

```json
{
  "results": [{
    "url": "https://www.rundown.ai/",
    "status": "scrapable",
    "accessibility": {
      "http_works": true,
      "blocked_by": null,
      "requires_javascript": false
    },
    "listing_page": {
      "article_url_pattern": "/articles/[a-z0-9\\-]+",
      "sample_urls": ["..."],
      "listing_type": "news_grid"
    },
    "article_page": {
      "has_full_content": true,
      "title_selector": "h1.h2",
      "content_selector": ".rich-text.w-richtext",
      "date_selector": "p.body-s.u-text-secondary",
      "date_format": "MMMM D, YYYY"
    },
    "recommendation": {
      "approach": "http_simple",
      "confidence": 0.935
    }
  }],
  "total": 13,
  "scrapable": 4,
  "blocked": 6,
  "not_scrapable": 3
}
```

### Cost

| Metric | Value |
|--------|-------|
| LLM Calls | 10 |
| Input Tokens | 156k |
| Output Tokens | 4.4k |
| Total Cost | $0.53 |
| Time | 1m 17s |

### Usage

```python
import html_layer1_orchestrator

# Run full discovery
html_layer1_orchestrator.run()

# Run for specific URLs only (substring match)
html_layer1_orchestrator.run(url_filter=['pulsenews', 'rundown'])
```

---

## HTML Layer 2: Content Scraping - COMPLETE (2026-01-06)

Scrapes articles from sources discovered as "scrapable" in HTML Layer 1.

### Architecture

```
HTML Layer 1 output
    │
    └── status: "scrapable" + full config ──┐
                                            │
                                            ▼
                              ┌─────────────────────────┐
                              │      HTML Layer 2       │
                              │   (Content Scraping)    │
                              └───────────┬─────────────┘
                                          │
                            ┌─────────────┴─────────────┐
                            │                           │
                   scraped articles            (reused L2 nodes)
                            │                           │
                            ▼                           ▼
                   html_news.json          filter → metadata → summaries
```

### Pipeline Flow

```
load_scrapable_sources → fetch_listing_pages → extract_article_urls →
fetch_html_articles → parse_article_content → adapt_html_to_articles →
filter_by_date → filter_business_news → extract_metadata →
generate_summaries → build_output_dataframe → save_html_content
```

### Features

1. **Source Loading**
   - Reads from `html_availability.json`
   - Filters to sources with `status="scrapable"` AND full config
   - Sources without `article_page` config are skipped (e.g., biz.chosun.com)

2. **Listing Page Scraping**
   - Fetches homepage for each source
   - Extracts article URLs using regex patterns from HTML L1
   - Rate-limited (1s between sources)

3. **Article Scraping**
   - Fetches individual article pages
   - Max 20 articles per source (configurable)
   - Rate-limited (0.5s between articles)

4. **Content Extraction**
   - Uses CSS selectors discovered in HTML L1
   - Extracts: title, content, date, author
   - Parses dates using discovered formats

5. **L2 Pipeline Reuse**
   - Converts scraped articles to RSSArticle format
   - Feeds into existing L2 nodes (filter, metadata, summaries)
   - Same output schema as RSS pipeline

### Test Run (2026-01-06)

| Metric | Value |
|--------|-------|
| **Sources Processed** | 3 (Rundown, Pulsenews, Epnc) |
| **Sources Skipped** | 1 (biz.chosun.com - no article_page) |
| **Articles Scraped** | 45 |
| **After Date Filter** | 33 (24h cutoff) |
| **After LLM Filter** | 7 kept, 26 discarded |
| **LLM Cost** | $0.26 |
| **Total Time** | ~64 seconds |

**Sample Articles Extracted:**

| Source | Title | Category |
|--------|-------|----------|
| Rundown | Alexa+ comes for ChatGPT's web turf | Product Launch |
| Rundown | Agibot's tiny, portable humanoid | Product Launch |
| Rundown | Meta's AI chief scientist leaves with parting shots | Executive |
| Epnc | HBM Memory Supercycle (Korean) | Earnings |
| Epnc | 팀스파르타 AI Education (Korean) | Expansion |
| Epnc | Nvidia Rubin Platform (Korean) | Product Launch |
| Epnc | Samsung AI Strategy at CES (Korean) | Product Launch |

**Distribution:**
- By Source: Epnc (4), Rundown (3)
- By Region: North America (4), East Asia (3)
- By Category: Product Launch (4), Earnings (1), Expansion (1), Executive (1)

**Notes:**
- Korean articles from Epnc are automatically translated to English summaries by the LLM
- All 20 Pulsenews articles were discarded (general Korea business news, not AI-specific)
- **TODO:** Integrate with Layer 3 dedup to avoid duplicates with RSS pipeline

### Output Files

| File | Description |
|------|-------------|
| `data/html_news.json` | Scraped AI business news with metadata |
| `data/html_news.csv` | CSV format output |
| `data/html_discarded.csv` | Filtered-out articles with discard reasons |

### Files Created

| File | Description |
|------|-------------|
| `html_layer2_orchestrator.py` | Main orchestrator |
| `src/functions/load_scrapable_sources.py` | Load from html_availability.json |
| `src/functions/fetch_listing_pages.py` | Fetch listing pages |
| `src/functions/extract_article_urls.py` | Extract URLs via regex |
| `src/functions/fetch_html_articles.py` | Fetch article pages |
| `src/functions/parse_article_content.py` | Extract via CSS selectors |
| `src/functions/adapt_html_to_articles.py` | Convert to RSSArticle format |
| `src/functions/save_html_content.py` | Save output files |

### Usage

```python
import html_layer2_orchestrator

# Run full scraping
html_layer2_orchestrator.run()

# Run for specific URLs only
html_layer2_orchestrator.run(url_filter=['rundown'])

# Custom article age cutoff
html_layer2_orchestrator.run(max_age_hours=48)
```

---

## Layer 2: Content Aggregation - COMPLETE

### Mandatory English Summaries - IMPLEMENTED (2026-01-05)

**All articles now get LLM-generated English summaries** (1-2 sentences).

**Changes:**

1. **Removed `evaluate_content_sufficiency` node** - No longer needed since we always summarize
2. **Always generate summaries** (`generate_summaries.py`)
   - All articles processed through LLM summarization
   - Non-English sources (e.g., 36Kr) are translated to English
   - Summaries are 1-2 sentences, under 80 words
3. **Model changed to Haiku 4.5** - Cost-optimized from Sonnet 4
4. **Adaptive batch retry** - On JSON parse errors, retries with smaller batches (10→7→5)
5. **Prompt enhanced** (`generate_summary_system_prompt.md`)
   - Must output in English (translate if source is non-English)
   - Exactly 1-2 sentences
   - Must include: company name, action, key numbers, geography
   - Must explain what the company/product does

### Pipeline Flow

```
load_available_feeds → fetch_rss_content → filter_business_news
→ extract_metadata → generate_summaries → build_output_dataframe
→ save_aggregated_content
```

### Latest Test Run (2026-01-05)

| Metric | Value |
|--------|-------|
| **Model** | Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) |
| **Sources Processed** | 26 available feeds |
| **Articles Fetched** | 465 (deduplicated) |
| **After Filtering** | 131 kept, 334 discarded |
| **Total Cost** | $1.60 |
| **LLM Calls** | 43 |
| **Total Time** | ~11 minutes |

### Output Distribution

**By Region:**
- North America: 59
- East Asia: 27
- Europe: 13
- Global: 9
- Middle East: 8
- Africa: 6
- South Asia: 5
- Southeast Asia: 2
- Oceania: 1

**By Category:**
- Funding: 40
- Product Launch: 38
- Acquisition: 14
- IPO: 11
- Expansion: 9
- Partnership: 8
- Other: 6
- Earnings: 4
- Executive: 1

**By AI Layer:**
- B2B Applications: 53
- Foundation Models: 33
- Chips & Infrastructure: 21
- Consumer Applications: 15
- Fine-tuning & MLOps: 9

### Output Files

- `data/aggregated_news.json` - Structured JSON with metadata
- `data/aggregated_news.csv` - Tabular format (131 articles)
- `data/discarded_news.csv` - Discarded articles with reasons (334 articles)

---

## Layer 3: Deduplication - COMPLETE (2026-01-06)

Semantic deduplication system using SQLite + OpenAI embeddings + LLM confirmation.

### Features

1. **URL Deduplication (L2 Integration)**
   - New node `check_url_duplicates` in L2 pipeline
   - Checks URLs against historical DB before LLM processing
   - Saves LLM costs by skipping already-processed articles

2. **Semantic Deduplication (L3 Pipeline)**
   - Uses OpenAI `text-embedding-3-small` for embeddings
   - Compares new articles against last 48h of stored articles
   - Three-tier classification:
     - Unique: similarity < 0.75 (keep, no LLM)
     - Ambiguous: 0.75 ≤ similarity < 0.90 (LLM confirmation)
     - Duplicate: similarity ≥ 0.90 (auto-discard, no LLM)
   - LLM (Haiku) confirms only ambiguous cases

3. **First Run Behavior**
   - If DB empty, skips deduplication
   - Seeds database with all L2 articles + embeddings

### Pipeline Flow

```
load_new_articles → generate_embeddings → load_historical_embeddings →
compare_similarities → llm_confirm_duplicates → store_articles →
export_dedup_report
```

### Files Created

| File | Description |
|------|-------------|
| `dedup_orchestrator.py` | L3 orchestrator |
| `src/database.py` | SQLite helper class |
| `src/functions/check_url_duplicates.py` | L2: URL dedup node |
| `src/functions/generate_embeddings.py` | OpenAI embeddings |
| `src/functions/load_historical_embeddings.py` | Load from DB |
| `src/functions/compare_similarities.py` | Cosine similarity |
| `src/functions/llm_confirm_duplicates.py` | LLM confirmation |
| `src/functions/store_articles.py` | Store to SQLite |
| `src/functions/export_dedup_report.py` | Generate report |
| `prompts/confirm_duplicate_system_prompt.md` | LLM prompt |

### Output Files

- `data/articles.db` - SQLite database with articles and embeddings
- `data/aggregated_news_deduped.json` - Deduplicated articles
- `data/aggregated_news_deduped.csv` - CSV format
- `data/dedup_report.json` - Deduplication statistics

### Cost Estimate

| Component | Cost per Run |
|-----------|--------------|
| Embeddings (OpenAI) | ~$0.001 |
| LLM confirmation (Haiku) | ~$0.01-0.02 |
| **Total** | **~$0.02-0.03** |

### Usage

```python
import dedup_orchestrator

# Run after Layer 2 completes
dedup_orchestrator.run()

# Custom lookback (e.g., 7 days)
dedup_orchestrator.run(lookback_hours=168)
```

---

## Twitter Pipeline - L1/L2 SPLIT (2026-01-06)

Split into two layers following RSS pattern.

### Twitter Layer 1: Account Discovery

```
load_twitter_accounts → fetch_twitter_content → analyze_account_activity →
save_twitter_availability
```

**Features:**
- Scrapes all configured accounts via Playwright GraphQL interception
- Analyzes posting frequency (tweets per day, last tweet date)
- Marks accounts as "active" or "inactive" (no tweets in 14 days)
- Caches raw tweets for Layer 2 (no re-scraping needed)
- Results merge with existing `twitter_availability.json`

**Output Files:**
- `data/twitter_availability.json` - Account status and metrics
- `data/twitter_raw_cache.json` - Raw tweets for Layer 2

### Twitter Layer 2: Content Aggregation

```
load_available_accounts → load_cached_tweets → filter_by_date_twitter →
adapt_tweets_to_articles → filter_business_news → extract_metadata →
generate_summaries → build_twitter_output → save_twitter_content
```

**Features:**
- Reads from L1 output (only active accounts)
- Uses cached tweets (no re-scraping)
- Reuses LLM nodes from RSS Layer 2
- Same 8-field output schema

### Files Created

| File | Description |
|------|-------------|
| `twitter_layer1_orchestrator.py` | L1 orchestrator |
| `twitter_layer2_orchestrator.py` | L2 orchestrator |
| `src/functions/analyze_account_activity.py` | L1: Activity analysis |
| `src/functions/save_twitter_availability.py` | L1: Save status + cache |
| `src/functions/load_available_twitter_accounts.py` | L2: Load active accounts |
| `src/functions/load_cached_tweets.py` | L2: Load from cache |

### Test Run (2026-01-06)

**Layer 1:**
| Account | Status | Last Tweet | Tweets in 14d |
|---------|--------|------------|---------------|
| @rohanpaul_ai | inactive | 2025-11-18 | 0 |
| @TheRundownAI | active | 2026-01-05 | 11 |

**Layer 2:**
- Skipped @rohanpaul_ai (inactive)
- Loaded 17 cached tweets for @TheRundownAI
- After date filter (24h): 2 tweets
- After LLM filter: 0 (news roundups, not business news)
- LLM cost: $0.0067

### Usage

```python
# Step 1: Run Layer 1 (scrape + analyze)
import twitter_layer1_orchestrator
twitter_layer1_orchestrator.run()

# Step 2: Run Layer 2 (process cached tweets)
import twitter_layer2_orchestrator
twitter_layer2_orchestrator.run()
```

### Configuration

```json
{
  "settings": {
    "scrape_delay_min": 55,
    "scrape_delay_max": 65,
    "max_age_hours": 24,
    "inactivity_threshold_days": 14,
    "cache_ttl_hours": 24
  }
}
```

### Known Limitations

1. **Rate limiting required** - 55-65s randomized delay between accounts to avoid bans
2. **Authentication required** - Must provide session cookies from logged-in browser
3. **Cookie expiration** - Cookies may expire after a few weeks, requiring re-authentication
4. **Ban risk** - Aggressive scraping may result in account suspension
5. **Cache must be fresh** - Run L1 before L2

### Twitter Scraper Fixed via CDP Cookie Injection (2026-01-06)

**Status: FIXED** - Twitter pipeline now returns chronological recent tweets.

**Problem (was):**
- Twitter/X restricts what non-authenticated users can see
- Profile pages for unauthenticated visitors show only "highlight" or "top" tweets
- These were old viral tweets (2022-2024), NOT the chronological timeline

**Root Cause Analysis:**
- Compared with working [x-crawler](https://github.com/factomind-technologies/x-crawler) implementation
- Key difference: x-crawler used `launch_persistent_context` with session cookies
- Twitter serves different content based on authentication state
- Even Playwright's anti-detection flags (`--disable-blink-features=AutomationControlled`) weren't enough

**Solution Implemented:**
1. **Chrome DevTools Protocol (CDP) cookie extraction**
   - User launches Chrome manually with `--remote-debugging-port=9222`
   - User logs in to Twitter in that real browser (no automation detection)
   - Script connects via CDP and extracts session cookies
   - Cookies saved to `chrome_data/twitter_cookies.json`

2. **Cookie injection in scraper**
   - `fetch_twitter_content.py` loads cookies from JSON file
   - Injects cookies into Playwright context before navigation
   - Twitter sees authenticated session, returns full chronological timeline

**Files Changed:**
- `src/functions/fetch_twitter_content.py` - Added persistent context, cookie loading, stealth flags
- `twitter_cdp_login.py` - New script for CDP cookie extraction
- `twitter_login.py` - Alternative Playwright-based login (less reliable)

**Test Results (2026-01-06):**
```
Before (broken):
  Oct 11, 2024 - "BREAKING: Tesla's Cybercab..."
  Jan 18, 2023 - "Boston Dynamics robots..."

After (fixed):
  Jan 06, 2026 - "NEWS: Elon Musk has confirmed that xAI..."
  Jan 06, 2026 - "NEWS: All @Tesla Model Ys trims in China..."
  Jan 06, 2026 - "NEWS: Tesla China has just announced..."
```

**⚠️ CAUTION: Aggressive scraping may result in account suspension.**
- Use a secondary/throwaway Twitter account
- Keep 30+ second delays between accounts
- Limit to a few scraping sessions per day
- See CLAUDE.md "Twitter Rate Limiting & Ban Prevention" for details

---

## Recent Improvements

### 2026-01-07 (Latest)

1. **Database Storage for Discarded Articles and Full Dedup Content**
   - New `discarded_articles` table stores all filtered-out articles from L2 pipelines
   - Fields: url, url_hash, title, source, source_type, pub_date, discard_reason, run_timestamp
   - Expanded `dedup_log` table with 8 new columns for full article content:
     - original_title, original_summary, original_source, original_source_type
     - duplicate_of_title, duplicate_of_summary, duplicate_of_source, llm_reason
   - Auto-migration for existing databases (ALTER TABLE adds new columns)
   - Integration: save_aggregated_content.py, save_html_content.py, save_twitter_content.py
   - Enables debugging and historical analysis of filtering/dedup decisions
   - **Files modified:** database.py, store_articles.py, save_aggregated_content.py, save_html_content.py, save_twitter_content.py

**Test Run Results (2026-01-07):**
- Discarded articles stored: 237 total (205 RSS, 22 HTML, 10 Twitter)
- Dedup log entries with full content: 12

### 2026-01-06

1. **Cross-Pipeline Deduplication Implemented**
   - Layer 3 now merges RSS, HTML, and Twitter outputs before deduplication
   - New `merge_pipeline_outputs` node combines all sources with URL priority (RSS > HTML > Twitter)
   - Tracks `source_type` field for each article ("rss", "html", "twitter")
   - Cross-source duplicates detected via semantic similarity
   - Report includes `by_source_type` breakdown and `cross_source_duplicates` count
   - Output renamed: `merged_news_deduped.json` (was `aggregated_news_deduped.json`)
   - Database schema updated with `source_type` column (auto-migrates existing DBs)
   - New files: `src/functions/merge_pipeline_outputs.py`
   - Modified: `dedup_orchestrator.py`, `export_dedup_report.py`, `src/database.py`

2. **HTML Layer 2: Content Scraping Implemented**
   - New pipeline to scrape articles from sources discovered as "scrapable" in HTML L1
   - Fetches listing pages, extracts article URLs via regex patterns
   - Fetches articles, extracts content via CSS selectors
   - Reuses existing L2 pipeline nodes (filter, metadata, summaries)
   - Test run: 3 sources processed, 45 articles scraped, 7 kept after filtering
   - Outputs: `data/html_news.json`, `data/html_news.csv`, `data/html_discarded.csv`
   - New files: `html_layer2_orchestrator.py`, 7 node functions
   - Cost: $0.26 for full pipeline run

2. **HTML Layer 1: Scrapability Discovery Implemented**
   - New pipeline to analyze "unavailable" RSS sources for HTML scraping potential
   - LLM-powered analysis of listing page structure and article extraction patterns
   - Detects bot protection (Cloudflare, CAPTCHA, JS-redirect)
   - Found 4 scrapable sources out of 13 tested:
     - Rundown AI, Pulse News Korea, EPNC Korea, Biz Chosun
   - Outputs CSS selectors, URL patterns, and extraction configs
   - Results saved to `data/html_availability.json`
   - New files: `html_layer1_orchestrator.py`, 7 node functions, 2 LLM prompts
   - Cost: $0.53 for full pipeline run

2. **Twitter Scraper Fixed**
   - Root cause: Twitter serves curated "highlights" to non-authenticated users
   - Solution: CDP (Chrome DevTools Protocol) cookie extraction from logged-in browser
   - New script `twitter_cdp_login.py` connects to Chrome with remote debugging
   - Cookies saved to `chrome_data/twitter_cookies.json`, auto-loaded by scraper
   - Added stealth flags (`--disable-blink-features=AutomationControlled`)
   - Added `launch_persistent_context` for session state persistence
   - Test confirmed: Now returns chronological recent tweets (2026-01-06)

2. **Layer 3: Deduplication System Implemented**
   - New `dedup_orchestrator.py` for semantic deduplication
   - SQLite database for article storage with embeddings
   - OpenAI `text-embedding-3-small` for vector embeddings
   - Three-tier classification: unique (<0.75), ambiguous (0.75-0.90), duplicate (>0.90)
   - LLM confirmation only for ambiguous cases (cost-optimized)
   - URL dedup integrated into L2 pipeline (`check_url_duplicates` node)
   - First run seeds database without deduplication
   - Cost: ~$0.02-0.03 per run

2. **Twitter Pipeline Split into L1/L2**
   - Layer 1: Account discovery (scrape, analyze activity, cache tweets)
   - Layer 2: Content aggregation (read cache, filter, enrich)
   - Inactive accounts (no tweets in 14 days) are skipped in L2
   - No re-scraping: L2 uses cached tweets from L1
   - New files: `twitter_layer1_orchestrator.py`, `twitter_layer2_orchestrator.py`
   - New functions: `analyze_account_activity`, `save_twitter_availability`, `load_available_twitter_accounts`, `load_cached_tweets`

2. **RSS Directory Scanning Added**
   - New node `scan_rss_directories` in Layer 1 pipeline
   - Scans common RSS directory pages (`/about/rss`, `/feeds`, etc.)
   - Discovers topic-specific feeds (tech, AI, science) from directory pages
   - No LLM cost (pure HTTP + regex parsing)
   - For non-AI-focused sites, prefers tech feed over main feed
   - Example: Fox News tech feed `moxie.foxnews.com/google-publisher/tech.xml` now discovered

2. **Layer 0 Disabled**
   - Source quality assessment disabled due to DuckDuckGo regional bias issues
   - Layer 1 now reads directly from `input_urls.json`
   - Code preserved but not in use

3. **New Sources Added**
   - Added 4 new URLs: Fox News, FinAI News, Rundown AI, MarkTechPost
   - Total sources: 58 (31 available, 8 paywalled, 19 unavailable)

### 2026-01-05

1. **Twitter Pipeline Implemented**
   - New `twitter_orchestrator.py` for scraping Twitter/X accounts
   - Uses Playwright to intercept GraphQL API responses
   - 30-second rate limiting between accounts
   - Reuses existing LLM nodes (filter, metadata, summaries)
   - Same 8-field output schema as RSS pipeline
   - Test run: 3 AI business tweets extracted from @rohanpaul_ai

2. **Date Cutoff Filter Added**
   - New node `filter_by_date` runs before LLM filtering
   - Drops articles older than `max_age_hours` (default: 24)
   - Reduces LLM costs by filtering old articles before API calls
   - Usage: `content_orchestrator.run(max_age_hours=48)`

2. **Adaptive Batch Retry for JSON Parse Errors**
   - `filter_business_news.py` now retries failed batches with smaller sizes
   - Retry sequence: 25 → 15 → 10 articles per batch
   - Increased `max_tokens` for smaller batches (2048 → 3072)
   - **Result:** 100% recovery rate on failed batches (was 45% failure rate)
   - Previously ~225 articles lost to `parse_error_discard`, now 0

3. **Discarded Articles Export**
   - New output file: `data/discarded_news.csv`
   - Contains all filtered-out articles with LLM-generated discard reasons
   - Schema: `source_name, title, url, pub_date, discard_reason`
   - Enables analysis of filtering decisions and potential false negatives

4. **Layer 1 Time Tracking Added**
   - Added `track_time` to all Layer 1 node functions
   - `test_rss_preset.py`, `test_ai_category.py`, `discover_rss_agent.py`, `classify_feeds.py`

5. **Excluded General News Sources**
   - Removed RFI and Euronews from available feeds (status → "excluded")
   - These are general news sources that polluted results with non-AI articles
   - Now 26 available feeds

6. **Changed Default Behavior to DISCARD**
   - `filter_business_news.py` now defaults to DISCARD on errors/missing classifications
   - Previously defaulted to KEEP, which let non-AI articles slip through
   - Safer for filtering quality; may lose some valid articles on transient errors

### 2026-01-04

1. **Model Optimization**
   - Switched from Sonnet 4 ($3/$15 per M) to Haiku 4.5 ($1/$5 per M)
   - Cost reduced from ~$2.50 to ~$0.34 per run (~85% savings)
   - GPT-5 mini tested but had JSON output issues due to reasoning mode

2. **Retry Logic Added**
   - `fetch_rss_content.py` now retries failed feeds (2 retries, 5s delay)
   - Timeout increased from 15s to 20s
   - Weetracker now successfully fetches (was timing out)

3. **Source Filter Added**
   - `content_orchestrator.py` accepts `source_filter` parameter
   - Can run tests on specific sources: `run(source_filter=['techcabal', '36kr'])`

4. **AI-Relevance Filter Strengthened**
   - Updated `filter_business_news_system_prompt.md`
   - Now explicitly requires articles to be about AI value chain companies
   - Added examples: Warren Buffett = DISCARD, OpenAI funding = KEEP

## Cost Breakdown

| Node | Model | Est. Cost per Run |
|------|-------|-------------------|
| filter_business_news | Haiku 4.5 | ~$0.15 |
| extract_metadata | Haiku 4.5 | ~$0.05 |
| generate_summaries | Haiku 4.5 | ~$0.19 (always runs) |
| **Total** | | **~$0.39** |

*Note: `evaluate_content_sufficiency` removed from pipeline (2026-01-05)*

## Configuration

### Models Used

```python
# filter_business_news.py, extract_metadata.py, evaluate_content_sufficiency.py
model = "claude-haiku-4-5-20251001"
```

### Retry Configuration

```python
# fetch_rss_content.py
MAX_RETRIES = 2       # Number of retry attempts
RETRY_DELAY = 5       # Seconds between retries
REQUEST_TIMEOUT = 20  # Request timeout in seconds
```

## Next Steps

### High Priority
1. ~~Run full test with all 27 sources~~ (Done 2026-01-05)
2. ~~Add retry logic for LLM parse errors~~ (Done 2026-01-05 - adaptive batch sizing)
3. ~~Add feed freshness check~~ (Done 2026-01-05 - stale AI feeds fall back to main)
4. Add more AI-focused RSS sources (replace excluded general news sources)
5. ~~**Add news source quality checker**~~ (Done 2026-01-05 - Layer 0 implemented)
   - Implemented as Layer 0 (runs before Layer 1)
   - Fetches homepage/about page, LLM assesses credibility
   - Outputs `source_quality: "quality"` or `"crude"` per source
   - Layer 1 automatically filters to quality sources only
6. **Enhance filtering & metadata quality**
   - Filter correctly discarded "Grok sexualized photos" scandal stories
   - Kept business news: "xAI launches Grok Business and Enterprise"
   - Monitor for edge cases where scandal/controversy slips through
   - **Fix region classification errors:**
     - Korean news incorrectly categorized as "South Asia" (should be "East Asia")
     - **Clarify region definition:** company HQ vs. activity location?
       - Example: SORA Technology (Japan-based) raising funds for Africa operations → classified as "Africa"
       - Should this be "East Asia" (HQ) or "Africa" (activity) or both?
     - Review region extraction prompt for geographic accuracy
     - Consider validating region against source country as sanity check
   - **Fix "Unable to summarize" failures:**
     - Example: AI Business NVIDIA article → "Unable to summarize - insufficient full content provided"
     - If recurring, articles with failed summaries should be discarded (not kept with placeholder text)
     - Add post-processing validation to filter out articles with invalid/failed summaries
7. ~~**FIX: Twitter scraper returns old/curated tweets instead of chronological timeline**~~ (Done 2026-01-06)
   - Fixed via CDP cookie injection from authenticated Chrome browser
   - See "Twitter Scraper Fixed" section under Twitter Pipeline for details
8. ~~**Add comprehensive deduplication**~~ (Done 2026-01-06)
   - Implemented cross-pipeline deduplication (RSS + HTML + Twitter)
   - Layer 3 now merges all sources before deduplication
   - URL dedup at merge point (priority: RSS > HTML > Twitter)
   - Semantic dedup handles cross-source duplicates
   - Output: `data/merged_news_deduped.json` with `source_type` field
   - See "Cross-Pipeline Deduplication" section below

### Medium Priority
9. ~~**Add HTML fetch checker for unavailable sources**~~ (Done 2026-01-06 - HTML Layer 1)
   - Implemented as `html_layer1_orchestrator.py`
   - Tests HTTP accessibility, bot protection detection
   - LLM analyzes listing page structure and article extraction patterns
   - Results saved to `data/html_availability.json`
   - Found 4 scrapable sources: Rundown AI, Pulse News Korea, EPNC Korea, Biz Chosun

10. ~~**Implement HTML Layer 2: Content Scraping**~~ (Done 2026-01-06)
    - Implemented as `html_layer2_orchestrator.py`
    - Scrapes articles from sources with full config in `html_availability.json`
    - Uses regex patterns for URL extraction, CSS selectors for content
    - Reuses existing L2 pipeline nodes (filter, metadata, summaries)
    - Sources processed: Rundown AI, Pulse News Korea, EPNC Korea
    - Sources skipped: Biz Chosun (no article_page config)
    - Output: `data/html_news.json`, `data/html_news.csv`

11. ~~**Integrate HTML Layer 2 with Layer 3 deduplication**~~ (Done 2026-01-06)
    - Merged into item #8 (comprehensive deduplication)
    - Layer 3 now automatically includes HTML sources via `merge_pipeline_outputs`

12. **Move HTML exclusions from hardcoded Python to `html_availability.json`**
    - Currently excluded sources are hardcoded in `load_unavailable_sources.py` (EXCLUDED_SOURCES list)
    - Should be stored in `html_availability.json` with `status: "excluded"` and `exclusion_reason`
    - Makes exclusions discoverable alongside other HTML L1 results
    - Affected sources: asiatechreview.com, hai.stanford.edu, whitecase.com, foreignaffairsforum.ae, reuters.com, wsj.com

13. **Add alternative content fetching for blocked/paywalled sources**
    - 6 sources blocked by CAPTCHA/Cloudflare (SCMP, CNBC, Economic Times, etc.)
    - 8 sources paywalled (Bloomberg, FT, Axios)
    - Options: NewsAPI.org, paid APIs, newsletter email ingestion
    - **Google News RSS investigated (2026-01-05):** Works for any indexed source (incl. paywalled), but only provides title/date/source domain - no article URL (JS redirect) or description. Not usable without additional URL resolution.
    - **Reuters scraping investigated (2026-01-05):**
      - Uses DataDome bot protection (enterprise-grade)
      - All methods blocked: httpx, Playwright headless, Playwright stealth, curl, RSS feeds (401)
      - CDP approach (Chrome `--remote-debugging-port=9222`) may work (~50% chance) if:
        - Using Chrome profile with prior manual Reuters visits
        - Different IP (current IP flagged)
      - Alternatives: NewsAPI.org (free 100 req/day), Reuters paid API
      - Test files: `tests/test_reuters_scraping*.py`
14. **Make Layer 1 incremental (skip already-identified sources)**
    - Currently L1 re-checks ALL sources every run, even if already in `rss_availability.json`
    - Should skip sources that already have results unless `force=True`
    - Apply same logic to HTML L1 and Twitter L1
    - Options:
      - Skip if source exists in output JSON (default)
      - `run(force=True)` to re-check all sources
      - `run(url_filter=['...'])` to re-check specific sources (already works)
    - Enables "run entire pipeline" without redundant L1 re-discovery

15. Consider scheduled runs (cron/GitHub Actions)
16. Build frontend/newsletter output format

### Low Priority
17. ~~**Add SQLite database for storage, deduplication, and history**~~ (Done 2026-01-06 - Layer 3 implemented)
    - ~~Store aggregated news in SQLite~~
    - ~~Deduplicate articles across runs (by URL and semantic similarity)~~
    - ~~Enable historical analysis and trend tracking~~
    - ~~Compare today's news with previous days/weeks~~

18. ~~**Add date filter to Layer 2**~~ (Done 2026-01-05)
   - ~~Filter articles by publication date (e.g., last 24 hours, last 7 days)~~
   - ~~Prevent old articles from stale feeds from being processed~~
   - ~~Configurable via `run(max_age_hours=24)` parameter~~

19. ~~**Store discarded articles and full dedup content in database**~~ (Done 2026-01-07)
    - New `discarded_articles` table: url, title, source, source_type, pub_date, discard_reason, run_timestamp
    - Expanded `dedup_log` table: +8 columns for full article content (original_title, original_summary, original_source, original_source_type, duplicate_of_title, duplicate_of_summary, duplicate_of_source, llm_reason)
    - Integration: save_aggregated_content.py, save_html_content.py, save_twitter_content.py now write to DB
    - Auto-migration for existing databases (ALTER TABLE adds new columns safely)
    - Enables historical debugging of filtering and deduplication decisions
