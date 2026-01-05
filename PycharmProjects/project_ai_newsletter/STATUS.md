# Project Status

**Last Updated:** 2026-01-05

## Current Phase

Layer 2 - Content Aggregation: **COMPLETE & TESTED**

## Layer 1: RSS Discovery - COMPLETE

- **Input:** 51 newsletter URLs
- **Output:** 27 available feeds discovered
- **Results:** `data/rss_availability.json`
- **Cost:** ~$0.025 per run

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
- `is_feed_fresh()` checks if feed is within 7 days (configurable)
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

## Recent Improvements

### 2026-01-05 (Latest)

1. **Adaptive Batch Retry for JSON Parse Errors**
   - `filter_business_news.py` now retries failed batches with smaller sizes
   - Retry sequence: 25 → 15 → 10 articles per batch
   - Increased `max_tokens` for smaller batches (2048 → 3072)
   - **Result:** 100% recovery rate on failed batches (was 45% failure rate)
   - Previously ~225 articles lost to `parse_error_discard`, now 0

2. **Discarded Articles Export**
   - New output file: `data/discarded_news.csv`
   - Contains all filtered-out articles with LLM-generated discard reasons
   - Schema: `source_name, title, url, pub_date, discard_reason`
   - Enables analysis of filtering decisions and potential false negatives

3. **Layer 1 Time Tracking Added**
   - Added `track_time` to all Layer 1 node functions
   - `test_rss_preset.py`, `test_ai_category.py`, `discover_rss_agent.py`, `classify_feeds.py`

4. **Excluded General News Sources**
   - Removed RFI and Euronews from available feeds (status → "excluded")
   - These are general news sources that polluted results with non-AI articles
   - Now 26 available feeds

5. **Changed Default Behavior to DISCARD**
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

### Medium Priority
5. Consider scheduled runs (cron/GitHub Actions)
6. Add deduplication across runs (by URL, across multiple pipeline runs)
7. Build frontend/newsletter output format

### Low Priority
8. **Add database for historical comparison**
   - Store aggregated news in SQLite/PostgreSQL
   - Track articles across runs to detect duplicates
   - Enable historical analysis and trend tracking
   - Compare today's news with previous days/weeks

9. **Add date filter to Layer 2**
   - Filter articles by publication date (e.g., last 24 hours, last 7 days)
   - Prevent old articles from stale feeds from being processed
   - Configurable via `run(max_age_days=7)` parameter
