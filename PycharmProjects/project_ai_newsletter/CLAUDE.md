# CLAUDE.md - Project Guidelines

AI Newsletter Aggregator - collects and aggregates AI news from RSS, HTML scraping, browser-use, and Twitter using LangGraph/LangChain orchestration. Outputs Korean summaries with metadata.

Development coding rules archived in `CLAUDE_ARCHIVE.md`.

---

## Pipeline Layers

| Layer | Orchestrator | Description |
|-------|-------------|-------------|
| L0 | `layer0_orchestrator.py` | Source quality assessment (DISABLED) |
| RSS L1 | `rss_orchestrator.py` | RSS feed discovery (incremental, 7-day refresh) |
| RSS Fetch | `rss_fetch_orchestrator.py` | Cache RSS articles (no LLM, runs hourly) |
| RSS L2 | `content_orchestrator.py` | Content aggregation from RSS (filter, metadata, Korean summaries) |
| HTML L1 | `html_layer1_orchestrator.py` | Scrapability discovery for non-RSS sources |
| HTML L2 | `html_layer2_orchestrator.py` | Content scraping via HTTP + CSS selectors |
| Browser-Use L2 | `browser_use_orchestrator.py` | Scrape CAPTCHA/Cloudflare-blocked sources via `browser-use` + Claude Sonnet (~$0.30-0.50/source) |
| Twitter L1 | `twitter_layer1_orchestrator.py` | Tweet scraping via HTTP GraphQL API (direct, no browser) |
| Twitter L2 | `twitter_layer2_orchestrator.py` | Tweet content aggregation (same schema as RSS) |
| Dedup L3 | `dedup_orchestrator.py` | Semantic dedup using OpenAI embeddings + LLM confirmation |

**L2 common pipeline:** filter → extract_metadata → generate_summaries → build_output_dataframe → save

---

## Config-Driven Architecture

Each config has its own prompts, sources, and output data:
- **Prompts:** `configs/{name}/prompts/` (filter, metadata, summary)
- **Sources:** `configs/{name}/input_urls.json`, `twitter_accounts.json`
- **Settings:** `configs/{name}/config.json` (html_exclusions, valid_regions/categories/layers)
- **Output:** `data/{name}/`
- **Shared prompts** (L0/L1/L3): `prompts/`

| Config | Description |
|--------|-------------|
| `business_news` | AI business news (funding, M&A, launches) — 60+ RSS feeds + Twitter |
| `ai_tips` | AI usage tips, tutorials, workflows |
| `research` | AI/ML research papers, benchmarks, technical analysis |

`ai_tips` and `research` share sources but use mutually exclusive filter prompts.

---

## Usage

### Main Orchestrator (Recommended)

```bash
# Single config
python orchestrator.py --config business_news

# Multiple configs (Twitter automatically consolidated)
python orchestrator.py --configs business_news ai_tips

# Skip discovery layers (reuse existing L1 data)
python orchestrator.py --configs business_news ai_tips --skip-rss-l1 --skip-html-l1

# Only run specific layers
python orchestrator.py --configs business_news ai_tips --only twitter dedup

# Disable cache workflow
python orchestrator.py --configs business_news ai_tips --no-cache
```

**Pipeline Order:**
1. RSS L1 → RSS Fetch → RSS L2 (per config)
2. HTML L1 → HTML L2 (per config)
3. Browser-Use L2 (per config)
4. Twitter L1 (consolidated) → Twitter L2 (per config)
5. Dedup L3 (per config)

### Cron Schedule

```bash
# Every 1 hour - cache RSS (fast, no LLM cost)
0 * * * * cd /path/to/project && python rss_fetch_orchestrator.py --configs business_news ai_tips

# Every 12 hours - full pipeline
0 */12 * * * cd /path/to/project && python orchestrator.py --configs business_news ai_tips --skip-rss-fetch --skip-rss-l1 --skip-html-l1
```

### Individual Layers

```bash
# RSS L1 (incremental by default, --full-rescan to force)
python rss_orchestrator.py --config business_news
python rss_orchestrator.py --config business_news --full-rescan

# HTML L1 (same incremental behavior)
python html_layer1_orchestrator.py --config business_news

# RSS L2 (from cache or live)
python content_orchestrator.py --config business_news --from-cache
python content_orchestrator.py --config business_news --source-filter techcrunch

# HTML L2
python html_layer2_orchestrator.py --config business_news

# Browser-Use L2
python browser_use_orchestrator.py --config business_news

# Twitter (multi-config consolidated)
python twitter_layer1_orchestrator.py --configs business_news ai_tips --run-all

# Twitter L2 (use shared cache after multi-config L1)
python twitter_layer2_orchestrator.py --config business_news --use-shared-cache

# Dedup L3
python dedup_orchestrator.py --config business_news
```

### Adding a New Config

```bash
mkdir -p configs/new_config/prompts
cp configs/business_news/prompts/*.md configs/new_config/prompts/
# Edit prompts, create input_urls.json, config.json
python orchestrator.py --config new_config
```

---

## Twitter Scraping

Uses direct HTTP requests to Twitter's internal GraphQL API with session cookies. No browser is launched during scraping — eliminates bot detection from browser fingerprinting.

### Architecture

| Component | Location | Purpose |
|-----------|----------|---------|
| `src/twitter_client.py` | HTTP client | `TwitterClient` (GraphQL requests, pagination) + `AccountPool` (multi-account rotation) |
| `src/functions/fetch_twitter_content.py` | Pipeline node | Calls `TwitterClient`, parses GraphQL responses into `RawTweet` dicts |
| `twitter_cdp_login.py` | Cookie extraction | Connects to real Chrome via CDP to extract session cookies (manual login) |

### Cookie Setup

```bash
# 1. Launch Chrome with remote debugging
google-chrome --remote-debugging-port=9222 --user-data-dir="$HOME/chrome-twitter"

# 2. Log in to Twitter manually, then extract cookies
python twitter_cdp_login.py --port 9222 --test
```

Cookies saved to `chrome_data/twitter_cookies.json` (legacy format, auto-converted on first use).

### Account Pool

Supports multiple accounts for rate limit rotation. Accounts stored in `chrome_data/twitter_accounts.json`:

```json
[
  {"name": "main", "cookies": {"ct0": "...", "auth_token": "..."}, "proxy": null},
  {"name": "backup", "cookies": {"ct0": "...", "auth_token": "..."}, "proxy": "http://proxy:8080"}
]
```

On first run, the pool auto-migrates from the legacy `twitter_cookies.json`. To add accounts later, edit `twitter_accounts.json` directly.

### Key behaviors

- **No browser**: Pure HTTP via `httpx` to Twitter's GraphQL endpoints (bearer token + session cookies)
- **Pagination**: Cursor-based, configurable via `max_pages` setting (default: 1 page per account)
- **Inter-account delay**: 3-8s (configurable), much shorter than the old browser-based 55-65s
- **Cookie expiry detection**: Fails fast on 401/403 with clear error pointing to `twitter_cdp_login.py`
- **Rate limit handling**: Reads `x-rate-limit-remaining`/`x-rate-limit-reset` headers, locks account until reset, rotates to next available
- **GraphQL query IDs**: Hardcoded in `src/twitter_client.py` (`QUERY_IDS`). These change when Twitter updates their web client — if scraping breaks, check twikit/twscrape repos for updated IDs

---

## Output Files

All outputs in `data/{config}/`. Final exports copied to `output/`:

| Export | Source |
|--------|--------|
| `output/news.json` | `data/business_news/all_articles.json` |
| `output/tips.json` | `data/ai_tips/all_articles.json` |
| `output/research.json` | `data/research/all_articles.json` |

**Key data files per config:**
| File | Layer | Description |
|------|-------|-------------|
| `rss_availability.json` | L1 | RSS feed discovery results |
| `rss_cache.json` | Fetch | Cached raw articles for batch processing |
| `aggregated_news.json/csv` | L2 | Filtered AI news with metadata |
| `discarded_news.csv` | L2 | Filtered-out articles with reasons |
| `html_availability.json` | HTML L1 | Scrapability configs with CSS selectors |
| `html_news.json/csv` | HTML L2 | Scraped content |
| `browser_use_news.json/csv` | BU L2 | Content from blocked sources |
| `twitter_news.json/csv` | Tw L2 | Aggregated tweet content |
| `merged_news_deduped.json/csv` | L3 | Deduplicated news from all sources |
| `all_articles.json/csv` | L3 | Full DB export with `is_new` flag |
| `articles.db` | L3 | SQLite with articles, embeddings, dedup logs |

### Database Tables (`articles.db`)

| Table | Key Columns |
|-------|-------------|
| `articles` | url_hash, title, summary, source, source_type, embedding, created_at |
| `discarded_articles` | url, title, source, source_type, pub_date, discard_reason |
| `dedup_log` | original_url, duplicate_of_url, similarity_score, dedup_type, llm_reason |

---

## Metadata Schema

Each config defines valid `region`, `category`, `layer` values in `config.json`. The `extract_metadata` function validates LLM output against them. See each config's `config.json` for current values.

---

## Key Source Files

| Component | Location |
|-----------|----------|
| Main orchestrator | `orchestrator.py` |
| Node functions | `src/functions/` (one file per function) |
| Twitter HTTP client | `src/twitter_client.py` (GraphQL client + account pool) |
| LLM models | `src/models.py` |
| Config management | `src/config.py` |
| Tracking/logging | `src/tracking.py` |
| Database | `src/database.py` |
| Config-specific prompts | `configs/{name}/prompts/` |
| Shared prompts | `prompts/` |

### Cleanup Scripts

```bash
# Remove garbage articles from DB
python cleanup_garbage.py --configs business_news ai_tips --dry-run

# Fix bad summaries
python regenerate_summaries.py --configs business_news ai_tips --dry-run
```
