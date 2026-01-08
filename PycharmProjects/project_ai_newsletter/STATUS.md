# Project Status

**Last Updated:** 2026-01-08

## Current Phase

All layers complete and operational:
- Layer 0 (Source Quality): DISABLED
- Layer 1 (RSS Discovery): COMPLETE
- HTML Layer 1/2 (Scrapability + Scraping): COMPLETE
- Layer 2 (Content Aggregation): COMPLETE
- Layer 3 (Deduplication): COMPLETE
- Twitter Layer 1/2: COMPLETE

**For detailed implementation notes, see STATUS_ARCHIVE.md**

---

## Available Configs

| Config | Description | Sources |
|--------|-------------|---------|
| `business_news` | AI business news (funding, M&A, launches) | 60+ RSS feeds, 7 Twitter accounts |
| `ai_tips` | AI usage tips, tutorials, workflows | marktechpost.com, byhand.ai, @Sumanth_077 |

---

## Recent Improvements (2026-01-08)

1. **Korean Translation for Titles and Summaries**
   - All output now in Korean (한국어) instead of English
   - LLM generates both `title` (Korean headline) and `summary` (Korean content)
   - Terse wire-service style: "~기록.", "~예정." (no "~다" endings)
   - Company names kept in original form (OpenAI, not 오픈에이아이)
   - Already-Korean titles preserved (not regenerated)
   - Modified: `generate_summary_system_prompt.md`, `generate_summaries.py`, `build_twitter_output.py`

2. **HTML Exclusions Moved to Config**
   - Moved hardcoded `EXCLUDED_SOURCES` from Python to `config.json`
   - Per-config exclusions with reasons (`html_exclusions` field)
   - No code changes needed to add/remove exclusions

3. **Fixed Failed Summary Detection**
   - Added "generate" to `FAILED_SUMMARY_PATTERNS` regex
   - Now correctly discards articles with "Unable to generate summary..." errors
   - Fixed in: `build_output_dataframe.py`, `build_twitter_output.py`

---

## Recent Improvements (2026-01-07)

1. **Config-Driven Pipeline Architecture**
   - Multiple configs supported (e.g., `business_news`, `ai_tips`)
   - Each config has isolated: prompts, input URLs, twitter accounts, output data
   - Usage: `python content_orchestrator.py --config=ai_tips`

2. **Database Storage for Discarded Articles**
   - New `discarded_articles` table in SQLite
   - Expanded `dedup_log` with full article content

3. **New Config: `ai_tips`**
   - AI tips, tutorials, workflow guides
   - Sources: marktechpost.com, byhand.ai, @Sumanth_077
   - Custom metadata: category (prompting, image_gen, agents, etc.), layer (text_llm, image_gen, etc.)

4. **Twitter Scraper Fix: Conversation Threads**
   - Fixed parsing of `TimelineTimelineModule` entries
   - Now captures all tweets including threaded posts

---

## Cost Breakdown

| Node | Model | Est. Cost per Run |
|------|-------|-------------------|
| filter_business_news | Haiku 4.5 | ~$0.15 |
| extract_metadata | Haiku 4.5 | ~$0.05 |
| generate_summaries | Haiku 4.5 | ~$0.19 |
| **Total L2** | | **~$0.39** |

---

## Next Steps

### High Priority
- Add more AI-focused RSS sources
- Enhance filtering & metadata quality

### Medium Priority
- Add alternative content fetching for blocked/paywalled sources
- Make Layer 1 incremental (skip already-identified sources)
- Consider scheduled runs (cron/GitHub Actions)
- Build frontend/newsletter output format
