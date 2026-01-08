# Status Archive - Detailed Implementation History

**Note:** This file contains detailed implementation notes. For current status, see STATUS.md.

---

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
2. **Wikipedia detection unreliable**
3. **False negatives for lesser-known publications**
4. **Rate limiting** - 2-second delay between searches
5. **Spam/copypasta detection not implemented**

---

## Layer 1: RSS Discovery - COMPLETE

- **Input:** 58 newsletter URLs
- **Output:** 31 available feeds discovered
- **Results:** `data/rss_availability.json`
- **Cost:** ~$0.025 per run

### RSS Directory Scanning - IMPLEMENTED (2026-01-06)

Layer 1 now scans RSS directory pages (e.g., `/about/rss`, `/feeds`) to discover topic-specific feeds.

**Implementation:**
- New node `scan_rss_directories` runs after `test_main_rss`
- Scans common paths: `/about/rss`, `/about/feeds`, `/feeds`, `/help/rss`, `/rss-feeds`
- Parses HTML for feed links matching topic keywords (tech, AI, science)

**New fields in `rss_availability.json`:**
- `tech_feed_url`, `science_feed_url`, `directory_page_url`

**Feed Selection Logic:**
- For non-AI-focused sites: prefer `tech_feed_url` > `ai_feed_url` > `main_feed_url`

### Full Content Detection - IMPLEMENTED (2026-01-05)

**New fields:** `has_full_content`, `http_fetch_works`

### Feed Freshness Check - IMPLEMENTED (2026-01-05)

**New fields:** `main_feed_latest_date`, `ai_feed_latest_date`, `fallback_reason`

### Layer 1 Re-Run Behavior

**Important:** Layer 1 is NOT incremental - it re-checks ALL sources every run.

### HTTP Article Fetch - IMPLEMENTED (2026-01-05)

Layer 2 now automatically fetches article HTML for sources where RSS lacks content.

---

## HTML Layer 1: Scrapability Discovery - COMPLETE (2026-01-06)

Automated pipeline to analyze "unavailable" sources from RSS Layer 1.

### Pipeline Flow
```
load_unavailable_sources → test_http_accessibility → analyze_listing_page →
analyze_article_page → classify_html_source → merge_html_results →
save_html_availability
```

### Features

1. **Source Filtering** - Reads from `rss_availability.json`, filters unavailable
2. **HTTP Accessibility Testing** - Detects bot protection
3. **LLM-Powered Listing Page Analysis** - Identifies article URL patterns
4. **LLM-Powered Article Page Analysis** - Identifies CSS selectors
5. **Source Classification** - scrapable, requires_js, blocked, not_scrapable

### Test Results (2026-01-06)

| Status | Count | Sources |
|--------|-------|---------|
| **Scrapable** | 4 | Rundown AI, Pulse News Korea, EPNC Korea, Biz Chosun |
| **Blocked** | 6 | SCMP, CNBC, Economic Times, Finance ME, The National News, Baobab Network |
| **Not Scrapable** | 3 | KED Global (SSL), NASSCOM (502), Euronews (SPA) |

### Cost
- LLM Calls: 10, Input Tokens: 156k, Total Cost: $0.53

---

## HTML Layer 2: Content Scraping - COMPLETE (2026-01-06)

Scrapes articles from sources discovered as "scrapable" in HTML Layer 1.

### Pipeline Flow
```
load_scrapable_sources → fetch_listing_pages → extract_article_urls →
fetch_html_articles → parse_article_content → adapt_html_to_articles →
filter_by_date → filter_business_news → extract_metadata →
generate_summaries → build_output_dataframe → save_html_content
```

### Test Run (2026-01-06)

| Metric | Value |
|--------|-------|
| **Sources Processed** | 3 |
| **Articles Scraped** | 45 |
| **After LLM Filter** | 7 kept, 26 discarded |
| **LLM Cost** | $0.26 |

---

## Layer 2: Content Aggregation - COMPLETE

### Mandatory English Summaries - IMPLEMENTED (2026-01-05)

**All articles now get LLM-generated English summaries** (1-2 sentences).

### Pipeline Flow
```
load_available_feeds → fetch_rss_content → filter_business_news
→ extract_metadata → generate_summaries → build_output_dataframe
→ save_aggregated_content
```

---

## Layer 3: Deduplication - COMPLETE (2026-01-06)

Semantic deduplication using SQLite + OpenAI embeddings + LLM confirmation.

### Features

1. **URL Deduplication (L2 Integration)**
2. **Semantic Deduplication (L3 Pipeline)** - Three-tier: unique (<0.75), ambiguous (0.75-0.90), duplicate (>0.90)
3. **First Run Behavior** - Seeds database without deduplication

### Pipeline Flow
```
load_new_articles → generate_embeddings → load_historical_embeddings →
compare_similarities → llm_confirm_duplicates → store_articles →
export_dedup_report
```

### Cost Estimate
- Embeddings: ~$0.001, LLM confirmation: ~$0.01-0.02, **Total: ~$0.02-0.03**

---

## Twitter Pipeline - L1/L2 SPLIT (2026-01-06)

### Twitter Layer 1: Account Discovery
```
load_twitter_accounts → fetch_twitter_content → analyze_account_activity →
save_twitter_availability
```

### Twitter Layer 2: Content Aggregation
```
load_available_accounts → load_cached_tweets → filter_by_date_twitter →
adapt_tweets_to_articles → filter_business_news → extract_metadata →
generate_summaries → build_twitter_output → save_twitter_content
```

### Twitter Scraper Fixed via CDP Cookie Injection (2026-01-06)

**Problem:** Twitter serves curated "highlights" to non-authenticated users.

**Solution:** CDP cookie extraction from logged-in browser, injection into Playwright.

---

## Historical Improvements

### 2026-01-06

1. **Cross-Pipeline Deduplication Implemented**
2. **HTML Layer 2: Content Scraping Implemented**
3. **HTML Layer 1: Scrapability Discovery Implemented**
4. **Twitter Scraper Fixed**
5. **Layer 3: Deduplication System Implemented**
6. **Twitter Pipeline Split into L1/L2**
7. **RSS Directory Scanning Added**
8. **Layer 0 Disabled**
9. **New Sources Added** (Fox News, FinAI News, Rundown AI, MarkTechPost)

### 2026-01-05

1. **Twitter Pipeline Implemented**
2. **Date Cutoff Filter Added**
3. **Adaptive Batch Retry for JSON Parse Errors**
4. **Discarded Articles Export**
5. **Layer 1 Time Tracking Added**
6. **Excluded General News Sources**
7. **Changed Default Behavior to DISCARD**

### 2026-01-04

1. **Model Optimization** - Sonnet 4 → Haiku 4.5 (~85% cost savings)
2. **Retry Logic Added**
3. **Source Filter Added**
4. **AI-Relevance Filter Strengthened**
