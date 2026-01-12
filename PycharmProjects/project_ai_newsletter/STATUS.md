# Project Status

**Last Updated:** 2026-01-12

## Current Phase

All layers complete and operational:
- Layer 0 (Source Quality): DISABLED
- Layer 1 (RSS Discovery): COMPLETE
- HTML Layer 1/2 (Scrapability + Scraping): COMPLETE
- Layer 2 (Content Aggregation): COMPLETE + **Validation/Retry**
- Layer 3 (Deduplication): COMPLETE
- Twitter Layer 1/2: COMPLETE
- **Main Orchestrator: COMPLETE** (multi-config with Twitter consolidation)

**For detailed implementation notes, see STATUS_ARCHIVE.md**

---

## Available Configs

| Config | Description | Sources |
|--------|-------------|---------|
| `business_news` | AI business news (funding, M&A, launches) | 60+ RSS feeds, 7 Twitter accounts |
| `ai_tips` | AI usage tips, tutorials, workflows | marktechpost.com, byhand.ai, @Sumanth_077 |

---

## Recent Improvements (2026-01-12)

### URL Content Fetching for Link-Only Tweets

**Problem:** Link-only tweets (just URL or minimal text with URL) passed through with either:
- Hallucinated summaries (bad)
- Filtered as "no content" (missed valuable links)

**Solution Implemented:**

1. **New Pipeline Node** (`src/functions/fetch_link_content.py`)
   - Detects link-only tweets: text without URL < 50 chars
   - Expands t.co URLs via HEAD request redirects
   - Fetches page content (title + meta description)
   - Populates `description` and `full_text` with fetched content

2. **Pipeline Integration** (`twitter_layer2_orchestrator.py`)
   - New node `fetch_link_content` inserted between `filter_by_date_twitter` and `adapt_tweets_to_articles`
   - Failed fetches are discarded with `discard_reason: "url_fetch_failed"`

3. **Behavior:**
   - Success: Tweet gets full article context for better filtering/summarization
   - Failure: Tweet discarded and logged to `twitter_discarded.csv`

---

## Recent Improvements (2026-01-10)

### Summary Validation & Retry System

**Problem Found:** Analysis of existing DB revealed quality issues:
- 30 articles with too-long summaries (700-2100+ chars instead of ~150)
- 16 articles with English summaries instead of Korean

**Solution Implemented:**

1. **Validation Function** (`_validate_summary` in `generate_summaries.py`)
   - Checks summary length < 250 chars
   - Checks Korean character ratio ≥ 30%
   - Checks summary is not just truncated original content

2. **Automatic Retry** (`_retry_single_article`)
   - Up to 3 retry attempts for failed validations
   - Stronger prompt based on failure reason (too_long, not_korean, not_summarized)
   - Uses same model (gpt-5-mini) with explicit bad/good examples

3. **Fallback Tracking**
   - New fields: `content_source` (llm_summary, llm_summary_retry, description_fallback)
   - New field: `fallback_reason` (validation_failed:too_long, llm_no_response, etc.)
   - Validation stats logged per run

4. **Prompt Improvements**
   - Added "CRITICAL: What NOT to Return" section with explicit bad/good examples
   - Added 200 char limit requirement
   - Modified: `configs/*/prompts/generate_summary_system_prompt.md`

5. **Regeneration Script** (`regenerate_summaries.py`)
   - Finds articles needing regeneration via `db.get_articles_needing_regeneration()`
   - Applies same retry logic with validation
   - Usage: `python regenerate_summaries.py --config business_news --dry-run`
   - Export: `python regenerate_summaries.py --configs business_news ai_tips --export`

6. **Database Methods Added** (`src/database.py`)
   - `update_summary(url, new_summary, new_title)` - Update existing article
   - `get_articles_needing_regeneration(max_length)` - Find bad summaries

---

## Recent Improvements (2026-01-09)

1. **Main Orchestrator with Multi-Config Support**
   - `orchestrator.py` now runs the full pipeline for one or multiple configs
   - Usage: `python orchestrator.py --configs business_news ai_tips`
   - Supports `--skip-*` flags and `--only` for selective layer execution

2. **Twitter Multi-Config Consolidation**
   - When running multiple configs, Twitter handles are deduplicated across configs
   - Each handle is scraped only ONCE, cached in `data/shared/twitter_raw_cache.json`
   - Twitter L2 runs per-config using the shared cache
   - Prevents redundant scraping and reduces rate-limiting risk

3. **Layer 1 Incremental Mode (RSS + HTML)**
   - Both RSS Layer 1 and HTML Layer 1 now skip sources checked within 7 days (default)
   - RSS entries have `last_checked`, HTML entries have `analyzed_at` timestamps
   - New CLI flags: `--full-rescan`, `--refresh-days N`
   - Output shows `last_run_processed` and `last_run_skipped` counts
   - **Main orchestrator uses incremental mode by default** - daily runs are fast
   - To force full L1 rescan: `python rss_orchestrator.py --full-rescan`

4. **New Functions Added**
   - `src/config.py`: `get_shared_data_dir()`, `get_shared_twitter_cache_path()`
   - `src/functions/load_twitter_accounts.py`: `load_multi_config_twitter_accounts()`
   - `src/functions/save_twitter_availability.py`: `save_shared_twitter_cache()`
   - `src/functions/load_unavailable_sources.py`: `filter_recently_checked_html()`
   - `twitter_layer1_orchestrator.py`: `run_multi()`, `run_all()`
   - `twitter_layer2_orchestrator.py`: `use_shared_cache` parameter
   - `rss_orchestrator.py`: `filter_recently_checked()`, incremental parameters
   - `html_layer1_orchestrator.py`: `full_rescan`, `refresh_days` parameters

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
- Consider scheduled runs (cron/GitHub Actions)
- Build frontend/newsletter output format
- Use `browser-use` package for anti-bot news sources (Cloudflare, CAPTCHA-protected sites)

---

## TODO: Garbage Filtering (Twitter)

**Problem:** Low-quality tweets passing through filters despite having no information value.

**Examples of garbage that passed:**
| Type | Example | Source |
|------|---------|--------|
| Sarcasm/joke | "Claude Code already took my job" | @donvito |
| Pure reaction | "22222222 🤣🤣🤣🤣" | @seti_park |
| Wishful comment | "If only we had unlimited @ManusAI creds" | @donvito |
| Generic shill | "99% of people don't know... You're ahead. Don't stop." | @alexfinn |
| Empty hype | "Here's the truth nobody wants to admit: [generic claim]" | @hasantoxr |

**Proposed Filter Additions (for `filter_system_prompt.md`):**

```markdown
## REJECT: Low-Quality / No-Information Content

Reject tweets that contain NO concrete or actionable information:

1. **Sarcasm/Jokes** - Ironic statements with no literal meaning
   - "X already took my job" (sarcastic, not factual)
   - Excessive emojis/reactions without content ("🤣🤣🤣", "wow", "lol")

2. **Wishful/Hypothetical** - Speculation without facts
   - "If only we had...", "Imagine if..."
   - Questions without answers or insights

3. **Generic Encouragement/Shill** - Flattery with no specific content
   - "99% of people don't know...", "You're ahead of the competition"
   - Motivational statements without actionable tips

4. **Empty Hype Claims** - Bold claims without supporting detail
   - "Here's the truth nobody wants to admit:" followed by generic opinion
   - Exaggerated claims with no specifics

NOTE: Keep content that has substance even if clickbait-y:
- "BREAKING: [actual news with details]" → KEEP (has info)
- Reviews/후기 with actual insights → KEEP (has experience)
- Link-only tweets → Now handled by `fetch_link_content` node (2026-01-12)
```

**Implementation Options:**
1. Add to existing `filter_system_prompt.md` (recommended - no new LLM call)
2. Separate quality filter step after business filter (more accurate but +cost)

---

## COMPLETE: URL Content Fetching for Link-Only Tweets

**Implemented:** 2026-01-12 (see Recent Improvements section above)
