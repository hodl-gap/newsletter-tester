# Project Status

**Last Updated:** 2026-01-04

## Current Phase

Layer 2 - Content Aggregation: **COMPLETE & TESTED**

## Layer 1: RSS Discovery - COMPLETE

- **Input:** 51 newsletter URLs
- **Output:** 27 available feeds discovered
- **Results:** `data/rss_availability.json`
- **Cost:** ~$0.025 per run

## Layer 2: Content Aggregation - COMPLETE

### Pipeline Flow

```
load_available_feeds → fetch_rss_content → filter_business_news
→ evaluate_content_sufficiency → extract_metadata → generate_summaries
→ build_output_dataframe → save_aggregated_content
```

### Latest Test Run (2026-01-04)

| Metric | Value |
|--------|-------|
| **Model** | Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) |
| **Sources Tested** | Techcabal, Weetracker, 36Kr |
| **Articles Fetched** | 48 |
| **After Filtering** | 32 kept, 16 discarded |
| **Total Cost** | $0.34 |
| **LLM Calls** | 6 |

### Output Distribution

**By Region:**
- East Asia: 16
- Africa: 9
- North America: 2
- Middle East: 2
- Global: 1

**By Category:**
- Product Launch: 8
- Funding: 7
- Expansion: 4
- Earnings: 3
- Executive: 2
- Acquisition: 2
- IPO: 1
- Layoff: 1

**By AI Layer:**
- B2B Applications: 15
- Chips & Infrastructure: 7
- Consumer Applications: 5
- Foundation Models: 4
- Fine-tuning & MLOps: 1

### Output Files

- `data/aggregated_news.json` - Structured JSON with metadata
- `data/aggregated_news.csv` - Tabular format

## Recent Improvements

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
| filter_business_news | Haiku 4.5 | ~$0.18 |
| extract_metadata | Haiku 4.5 | ~$0.13 |
| evaluate_content_sufficiency | Haiku 4.5 | ~$0.02 |
| generate_summaries | Haiku 4.5 | ~$0.08 (if needed) |
| **Total** | | **~$0.34** |

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

1. Run full test with all 27 sources
2. Add more AI-focused RSS sources
3. Consider scheduled runs (cron/GitHub Actions)
4. Add deduplication across runs
5. Build frontend/newsletter output format
