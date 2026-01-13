# CLAUDE.md - Project Guidelines

## Project Overview

AI Newsletter Aggregator - a system to collect and aggregate content from various newsletter sources using LangGraph/LangChain for orchestration.

---

## Project Purpose

### Four Orchestrative Layers

**Layer 0: Source Quality Assessment** (DISABLED - see STATUS.md for known issues)
- Assess source credibility by analyzing homepage/about page
- Mark sources as "quality" (credible) or "crude" (unreliable)
- Output: `data/source_quality.json` with quality ratings
- **Status: Disabled due to DuckDuckGo regional bias and unreliable Wikipedia detection**

**Layer 1: Source Discovery** (standalone, L0 disabled)
- Find ways to access newsletter content (RSS, API, scraping)
- Test availability (public, paywalled, non-existent)
- Reads from `input_urls.json` directly (L0 integration disabled)
- Output: List of sources with access methods

**Layer 2: Content Aggregation** (depends on Layer 1)
- Fetch actual content from discovered sources
- Filter for AI business news
- Generate concise Korean summaries (1-2 sentences, terse wire-service style)
- Generate Korean headlines (preserves already-Korean titles)
- Extract metadata (region, category, AI layer)
- URL deduplication against historical DB (saves LLM costs)
- **Summary validation & retry** (added 2026-01-10):
  - Validates: length < 250 chars, Korean ratio ≥ 30%, not just copied content
  - Auto-retries up to 3x with stronger prompts on validation failure
  - Tracks `content_source` (llm_summary, llm_summary_retry, description_fallback)
  - Tracks `fallback_reason` for debugging failed summaries

**Layer 3: Deduplication** (runs after Layer 2)
- Semantic deduplication using OpenAI embeddings
- Compares new articles against last 48h of stored articles
- Three-tier classification: unique (<0.75), ambiguous (0.75-0.90), duplicate (>0.90)
- LLM confirmation for ambiguous cases only (cost-optimized)
- Stores articles with embeddings to SQLite for future comparison
- Exports full DB with `is_new` flag for dashboard (all historical + new articles)
- Output: `merged_news_deduped.json`, `dedup_report.json`, `all_articles.json`

**HTML Layer 1: Scrapability Discovery** (runs on RSS L1 "unavailable" sources)
- Analyzes sources without RSS to determine if they can be scraped via HTTP
- Tests HTTP accessibility and bot protection (Cloudflare, CAPTCHA)
- LLM analyzes listing page structure (article URL patterns)
- LLM analyzes article page structure (CSS selectors for extraction)
- Output: `data/html_availability.json` with scraping configs

**HTML Layer 2: Content Scraping** (uses HTML L1 configs)
- Scrapes articles from sources marked "scrapable" in HTML L1
- Fetches listing pages, extracts article URLs via regex patterns
- Fetches articles, extracts content via CSS selectors
- Feeds into existing L2 pipeline (filter, metadata, summaries)
- Output: `data/html_news.json`, `data/html_news.csv`, `data/html_discarded.csv`

**Twitter Pipeline** (independent, parallel to Layer 2) - **FIXED (2026-01-06)**
- Scrape tweets from configured Twitter/X accounts
- Uses Playwright to intercept GraphQL API responses
- **Requires authenticated session cookies** (see Twitter Authentication below)
- Same LLM filtering and metadata extraction as Layer 2
- Rate-limited (55-65s randomized delay between accounts)
- **Multi-config consolidation:** When running multiple configs, handles are deduplicated and scraped once
- Output: Same 8-field schema as RSS pipeline

**Browser-Use Layer 2: Blocked Sources** (runs after HTML L2)
- Scrapes sources blocked by CAPTCHA/Cloudflare using `browser-use` package
- Uses Claude Sonnet as LLM-driven browser agent (navigates, waits, extracts)
- Configured in `config.json["browser_use_sources"]`
- Enabled sources: Economic Times, SCMP, CNBC
- Feeds into existing L2 pipeline (filter, metadata, summaries)
- Output: `data/browser_use_news.json`, `data/browser_use_news.csv`
- Cost: ~$0.30-0.50 per source per run

---

## Architecture

### Config-Driven Architecture

The pipeline supports multiple configurations (e.g., `business_news`, `academic_papers`) where each config has its own:
- **Prompts** (`configs/{name}/prompts/`) - LLM prompts that define filtering/extraction behavior
- **Input URLs** (`configs/{name}/input_urls.json`) - Sources to scrape
- **Twitter accounts** (`configs/{name}/twitter_accounts.json`) - Twitter handles to follow
- **HTML exclusions** (`configs/{name}/config.json` → `html_exclusions`) - Sources to skip for HTML scraping
- **Output data** (`data/{name}/`) - All pipeline outputs isolated per config

**Default config:** `business_news`

**Available configs:**
| Config | Description | Sources |
|--------|-------------|---------|
| `business_news` | AI business news (funding, M&A, launches) | 60+ RSS feeds, Twitter accounts |
| `ai_tips` | AI usage tips, tutorials, workflows | marktechpost.com, byhand.ai, @Sumanth_077 |

### Main Orchestrator (Recommended)

The main `orchestrator.py` runs the **full pipeline** for one or multiple configs. When running multiple configs, Twitter scraping is automatically consolidated (each handle scraped once).

```bash
# Single config - runs all layers
python orchestrator.py --config business_news

# Multiple configs - Twitter automatically consolidated
python orchestrator.py --configs business_news ai_tips

# Skip discovery layers (faster, reuse existing L1 data)
python orchestrator.py --configs business_news ai_tips --skip-rss-l1 --skip-html-l1

# Only run specific layers
python orchestrator.py --configs business_news ai_tips --only twitter dedup
```

**Pipeline Order:**
1. RSS L1 (per config) → RSS L2 (per config)
2. HTML L1 (per config) → HTML L2 (per config)
3. Browser-Use L2 (per config) - blocked sources via LLM-driven browser
4. **Twitter L1 (CONSOLIDATED if multi-config)** → Twitter L2 (per config)
5. Dedup L3 (per config)

**Incremental L1 Layers:**
- RSS L1 and HTML L1 run in **incremental mode by default** (skip sources checked within 7 days)
- This makes daily runs fast while still processing all fresh content in L2/L3
- To force full rescan on L1, run the individual orchestrators with `--full-rescan`:
  ```bash
  python rss_orchestrator.py --config business_news --full-rescan
  python html_layer1_orchestrator.py --config business_news --full-rescan
  ```

### Individual Orchestrators

For running specific layers independently:

```python
# RSS Layer 2 only
content_orchestrator.run(config="business_news")

# CLI
python content_orchestrator.py --config=ai_tips
```

**Adding a new config:**
```bash
# 1. Create config directory
mkdir -p configs/academic_papers/prompts

# 2. Create prompts (define your filtering/extraction logic)
cp configs/business_news/prompts/*.md configs/academic_papers/prompts/
# Edit prompts to match new domain

# 3. Create input sources
vim configs/academic_papers/input_urls.json

# 4. Create config.json (optional: html_exclusions, default_max_age_hours)
echo '{"name": "academic_papers", "html_exclusions": []}' > configs/academic_papers/config.json

# 5. Run pipeline - outputs go to data/academic_papers/
python content_orchestrator.py --config=academic_papers
```

### Folder Structure

```
project_ai_newsletter/
├── orchestrator.py           # Main orchestrator (runs full pipeline)
├── layer0_orchestrator.py    # Layer 0: Source quality assessment
├── rss_orchestrator.py       # Layer 1: RSS discovery orchestrator
├── content_orchestrator.py   # Layer 2: Content aggregation orchestrator
├── dedup_orchestrator.py     # Layer 3: Deduplication orchestrator
├── html_layer1_orchestrator.py    # HTML L1: Scrapability discovery
├── html_layer2_orchestrator.py    # HTML L2: Content scraping
├── browser_use_orchestrator.py    # Browser-Use L2: Blocked sources (CAPTCHA/Cloudflare)
├── twitter_orchestrator.py   # Twitter: Tweet scraping pipeline (legacy)
├── twitter_layer1_orchestrator.py  # Twitter L1: Account discovery
├── twitter_layer2_orchestrator.py  # Twitter L2: Content aggregation
├── twitter_cdp_login.py       # Twitter: CDP cookie extraction script
├── twitter_login.py           # Twitter: Alternative Playwright login (less reliable)
├── cleanup_garbage.py         # One-time: Remove garbage articles from DB
├── regenerate_summaries.py    # One-time: Fix bad summaries in DB
├── src/
│   ├── __init__.py
│   ├── config.py             # Config management (set_config, get_data_dir, etc.)
│   ├── models.py             # All LLM model definitions and helpers
│   ├── utils.py              # Utility functions (config-aware prompt loading)
│   ├── tracking.py           # Time and cost tracking utilities
│   ├── database.py           # SQLite database (config-aware path)
│   └── functions/            # Node functions (one file per function)
│       ├── __init__.py
│       │── # Layer 0 functions
│       ├── fetch_source_reputation.py
│       ├── assess_credibility.py
│       │── # Layer 1 functions
│       ├── test_rss_preset.py
│       ├── scan_rss_directory.py
│       ├── test_ai_category.py
│       ├── discover_rss_agent.py
│       ├── classify_feeds.py
│       │── # Layer 2 functions
│       ├── load_available_feeds.py
│       ├── fetch_rss_content.py
│       ├── filter_business_news.py
│       ├── extract_metadata.py
│       ├── generate_summaries.py
│       ├── build_output_dataframe.py
│       ├── save_aggregated_content.py
│       ├── check_url_duplicates.py
│       │── # Layer 3 functions
│       ├── merge_pipeline_outputs.py
│       ├── generate_embeddings.py
│       ├── load_historical_embeddings.py
│       ├── compare_similarities.py
│       ├── llm_confirm_duplicates.py
│       ├── store_articles.py
│       ├── export_dedup_report.py
│       │── # HTML Layer 1 functions
│       ├── load_unavailable_sources.py
│       ├── test_http_accessibility.py
│       ├── analyze_listing_page.py
│       ├── analyze_article_page.py
│       ├── classify_html_source.py
│       ├── merge_html_results.py
│       ├── save_html_availability.py
│       │── # HTML Layer 2 functions
│       ├── load_scrapable_sources.py
│       ├── fetch_listing_pages.py
│       ├── extract_article_urls.py
│       ├── fetch_html_articles.py
│       ├── parse_article_content.py
│       ├── adapt_html_to_articles.py
│       ├── save_html_content.py
│       │── # Browser-Use L2 functions
│       ├── load_browser_use_sources.py
│       ├── fetch_with_browser_agent.py
│       ├── adapt_browser_use_to_articles.py
│       ├── save_browser_use_content.py
│       │── # Twitter L1 functions
│       ├── load_twitter_accounts.py
│       ├── fetch_twitter_content.py
│       ├── analyze_account_activity.py
│       ├── save_twitter_availability.py
│       │── # Twitter L2 functions
│       ├── load_available_twitter_accounts.py
│       ├── load_cached_tweets.py
│       ├── filter_by_date_twitter.py
│       ├── fetch_link_content.py
│       ├── build_twitter_output.py
│       └── save_twitter_content.py
├── configs/                  # Config-specific settings per pipeline type
│   └── business_news/        # Default config (current pipeline)
│       ├── prompts/          # Config-specific LLM prompts
│       │   ├── filter_system_prompt.md       # Filtering criteria
│       │   ├── extract_metadata_system_prompt.md
│       │   └── generate_summary_system_prompt.md
│       ├── input_urls.json   # URLs to process (Layer 0/1 input)
│       ├── twitter_accounts.json  # Twitter accounts to scrape
│       └── config.json       # Config settings (html_exclusions, default_max_age_hours)
├── prompts/                  # Shared prompts (Layer 0/1/3, non-config-specific)
│   │── # Layer 0 prompts
│   ├── assess_credibility_system_prompt.md
│   │── # Layer 1 prompts
│   ├── discover_rss_agent_system_prompt.md
│   ├── classify_feeds_system_prompt.md
│   │── # Layer 3 prompts
│   ├── confirm_duplicate_system_prompt.md
│   │── # HTML Layer 1 prompts
│   ├── analyze_listing_page_system_prompt.md
│   └── analyze_article_page_system_prompt.md
├── data/                     # Output data files (organized by config)
│   ├── shared/               # Shared data across configs
│   │   └── twitter_raw_cache.json  # Multi-config Twitter cache
│   └── business_news/        # Outputs for business_news config
│       ├── rss_availability.json # RSS discovery results (Layer 1 output)
│       ├── aggregated_news.json  # Aggregated content (Layer 2 output)
│       ├── aggregated_news.csv   # CSV format output (Layer 2 output)
│       ├── discarded_news.csv    # Filtered-out articles with reasons
│       ├── articles.db           # SQLite database (Layer 3)
│       ├── merged_news_deduped.json  # Deduplicated content (Layer 3 output)
│       ├── merged_news_deduped.csv   # CSV format output (Layer 3 output)
│       ├── dedup_report.json     # Deduplication report (Layer 3 output)
│       ├── html_availability.json     # HTML L1 output: Scrapability configs
│       ├── html_news.json             # HTML L2 output: Scraped content
│       ├── html_news.csv              # HTML L2 output: CSV format
│       ├── html_discarded.csv         # HTML L2 output: Filtered-out articles
│       ├── browser_use_news.json      # Browser-Use L2 output: Blocked sources content
│       ├── browser_use_news.csv       # Browser-Use L2 output: CSV format
│       ├── browser_use_discarded.csv  # Browser-Use L2 output: Filtered-out articles
│       ├── browser_use_failures.json  # Browser-Use L2 output: Failed sources
│       ├── twitter_availability.json  # Twitter L1 output: Account status
│       ├── twitter_raw_cache.json     # Twitter L1 output: Cached tweets for L2
│       ├── twitter_news.json          # Twitter L2 output: Aggregated content
│       ├── twitter_news.csv           # Twitter L2 output: CSV format
│       └── twitter_discarded.csv      # Twitter L2 output: Filtered-out tweets
├── chrome_data/                   # Browser data (gitignored)
│   └── twitter_cookies.json       # Twitter session cookies (required for scraping)
├── debug.log                 # Debug log file (auto-generated)
├── tests/                    # Test files
│   └── test_{function_name}.py
├── CLAUDE.md                 # Project guidelines
├── STATUS.md                 # Project status and roadmap
└── LAYER2_PLAN.md            # Layer 2 requirements and plan
```

---

## Rules

### 1. Modular Functions

- Each function must be in its own file under `src/functions/`
- File naming: `{function_name}.py`
- Each function file should export a single main function to be used as a LangGraph node

### 2. Orchestrator

- `orchestrator.py` is the main entry point
- Uses LangGraph to define the workflow graph
- Each node in the graph calls a function from `src/functions/`
- No business logic in the orchestrator—only graph structure and node connections

### 3. LLM Models (`src/models.py`)

- **All LLM model definitions** must be centralized in `src/models.py`
- Include helper functions:
  - `get_model(model_name: str)` - Returns the LLM instance
  - `get_default_model()` - Returns the default model
  - Model fallback logic if needed
- When calling an LLM anywhere in the codebase, **always import from `src/models.py`**
- This allows easy updates when models become obsolete

```python
# Example usage in a function file
from src.models import get_model

llm = get_model("gpt-4o")
```

**Cost-Aware Model Selection:**
- Use cheaper models (haiku, gpt-4o-mini) for simple classification tasks
- Use powerful models (sonnet, gpt-4o) for nuanced extraction/generation
- Always track costs per node to identify optimization opportunities

| Task Type | Recommended Model |
|-----------|-------------------|
| Binary classification | claude-haiku / gpt-4o-mini |
| Metadata extraction | claude-sonnet / gpt-4o |
| Content summarization | claude-sonnet / gpt-4o |
| Complex reasoning | claude-sonnet / gpt-4o |

**GPT-5 Notes:**
- Use `max_completion_tokens` (not `max_tokens`) for OpenAI GPT-5 models
- Set higher limits (4096+) for Korean output - JSON truncation causes parse errors

### 4. Prompts

Prompts are stored in two locations:

**Config-specific prompts** (`configs/{name}/prompts/`):
- Define the "business logic" for filtering, extraction, and summarization
- Loaded from active config directory (set via `set_config()`)
- Each config can customize what content to keep/discard
- Files: `filter_system_prompt.md`, `extract_metadata_system_prompt.md`, `generate_summary_system_prompt.md`

**Shared prompts** (`prompts/`):
- Layer 0/1/3 prompts that are config-independent
- Used as fallback if not found in config directory
- Files: `assess_credibility_system_prompt.md`, `discover_rss_agent_system_prompt.md`, `classify_feeds_system_prompt.md`, `confirm_duplicate_system_prompt.md`, etc.

**Rules:**
- Format: Markdown (`.md`)
- Prompts must be loaded from files, never hardcoded in function files
- Use placeholders like `{variable}` for dynamic content

```python
# Example prompt loading (config-aware)
from src.utils import load_prompt

# Loads from configs/{active_config}/prompts/ first, falls back to prompts/
prompt = load_prompt("filter_system_prompt.md")
```

### 5. Tests (`tests/`)

- All test files go in `tests/` folder
- Naming convention: `test_{function_name}.py`
- Use pytest as the test framework

### 6. Debug Logging (`src/tracking.py`)

All debug output is logged to both **console** and **`debug.log`** file using the `debug_log()` function.

**Setup:** Logger is auto-initialized on first use. Log file is overwritten each run.

```python
from src.tracking import debug_log

# Basic logging (defaults to INFO level)
debug_log("Processing started")

# With log level
debug_log("Something went wrong", "error")  # Levels: debug, info, warning, error
```

**LLM Calls:** Log FULL input and output without any truncation.

```python
debug_log(f"[LLM INPUT]: {prompt}")
response = llm.invoke(prompt)
debug_log(f"[LLM OUTPUT]: {response}")
```

**Node Functions:** Each node must log:
- Node name and entry point
- Key input data
- Key output data
- Any errors or edge cases

```python
from src.tracking import debug_log

def my_node(state: State) -> State:
    debug_log(f"[NODE: my_node] Entering")
    debug_log(f"[NODE: my_node] Input: {state['input_field']}")

    # ... processing ...

    debug_log(f"[NODE: my_node] Output: {result}")
    return {"output_field": result}
```

**Log Format:**
```
2026-01-02 17:40:49 | INFO     | [NODE: load_urls] Entering
2026-01-02 17:40:49 | ERROR    | [TOOL: browse_url] Error: 403 Forbidden
```

### 7. Time and Cost Tracking (`src/tracking.py`)

**Node Timing:** Use the `track_time` context manager to measure elapsed time per node.

```python
from src.tracking import track_time

def my_node(state: State) -> dict:
    with track_time("my_node"):
        # ... node logic ...
        return {"result": data}
# Output: [TIME] my_node: 2.34s
```

**LLM Cost Tracking:** Call `track_llm_cost` after each LLM API call.

```python
from src.tracking import track_llm_cost

response = client.messages.create(...)
track_llm_cost(
    model=response.model,
    input_tokens=response.usage.input_tokens,
    output_tokens=response.usage.output_tokens,
)
# Output: [COST] $0.0035 (903 in / 51 out)
```

**Cost Summary:** Reset tracker at start, print summary at end of pipeline.

```python
from src.tracking import cost_tracker, reset_cost_tracker

def run():
    reset_cost_tracker()
    # ... run pipeline ...
    cost_tracker.print_summary()
```

---

## Code Style

- Use type hints for all function parameters and return values
- Follow PEP 8 naming conventions
- Keep functions focused and single-purpose
- Document complex logic with inline comments

---

## Quick Reference

| Component | Location | Naming |
|-----------|----------|--------|
| Orchestrator | `orchestrator.py` | - |
| Layer 0 Orchestrator | `layer0_orchestrator.py` | - |
| RSS Orchestrator | `rss_orchestrator.py` | - |
| Content Orchestrator | `content_orchestrator.py` | - |
| Dedup Orchestrator | `dedup_orchestrator.py` | - |
| Twitter L1 Orchestrator | `twitter_layer1_orchestrator.py` | - |
| Twitter L2 Orchestrator | `twitter_layer2_orchestrator.py` | - |
| Node functions | `src/functions/` | `{name}.py` |
| LLM models | `src/models.py` | - |
| Tracking | `src/tracking.py` | - |
| Prompts | `prompts/` | `{func}_{desc}_prompt.md` |
| Data files | `data/` | `{name}.json` or `{name}.csv` |
| Tests | `tests/` | `test_{name}.py` |

## Output Files

All output files are stored in `data/{config_name}/` (e.g., `data/business_news/`).

| File | Description |
|------|-------------|
| `source_quality.json` | Layer 0 output: Source credibility ratings ("quality" or "crude") |
| `rss_availability.json` | Layer 1 output: RSS feed discovery results |
| `aggregated_news.json` | Layer 2 output: AI business news with metadata |
| `aggregated_news.csv` | Layer 2 output: Same as JSON in tabular format |
| `discarded_news.csv` | Layer 2 output: Filtered-out articles with discard reasons |
| `articles.db` | SQLite database with articles, embeddings, discarded articles, and dedup logs |
| `merged_news_deduped.json` | Layer 3 output: Deduplicated news from all sources (RSS + HTML + Browser-Use + Twitter) |
| `merged_news_deduped.csv` | Layer 3 output: Same as JSON with source_type column |
| `dedup_report.json` | Layer 3 output: Deduplication statistics with cross-source metrics |
| `all_articles.json` | Layer 3 output: Full database export with `is_new` flag (based on `created_at` within lookback period, default 24h) |
| `all_articles.csv` | Layer 3 output: Same as JSON in tabular format |
| `html_availability.json` | HTML L1 output: Scrapability configs with CSS selectors |
| `html_news.json` | HTML L2 output: AI business news from scraped sources |
| `html_news.csv` | HTML L2 output: Same as JSON in tabular format |
| `html_discarded.csv` | HTML L2 output: Filtered-out articles with discard reasons |
| `browser_use_news.json` | Browser-Use L2 output: AI business news from blocked sources |
| `browser_use_news.csv` | Browser-Use L2 output: Same as JSON in tabular format |
| `browser_use_discarded.csv` | Browser-Use L2 output: Filtered-out articles with discard reasons |
| `browser_use_failures.json` | Browser-Use L2 output: Failed sources with error details |
| `twitter_availability.json` | Twitter L1 output: Account status and activity metrics |
| `twitter_raw_cache.json` | Twitter L1 output: Cached tweets for L2 consumption |
| `twitter_news.json` | Twitter L2 output: AI business news from tweets |
| `twitter_news.csv` | Twitter L2 output: Same as JSON in tabular format |
| `twitter_discarded.csv` | Twitter L2 output: Filtered-out tweets with discard reasons |

**Input files** are stored in `configs/{config_name}/`:
| File | Description |
|------|-------------|
| `input_urls.json` | URLs to process (Layer 0/1 input) |
| `twitter_accounts.json` | Twitter accounts to scrape |
| `config.json` | Config settings: `html_exclusions`, `default_max_age_hours`, `valid_regions`, `valid_categories`, `valid_layers` |

### Database Tables (`data/articles.db`)

| Table | Description |
|-------|-------------|
| `articles` | Stored articles with embeddings (url_hash, title, summary, source, source_type, embedding, created_at) |
| `discarded_articles` | Filtered-out articles from all L2 pipelines (url, title, source, source_type, pub_date, discard_reason, run_timestamp) |
| `dedup_log` | Deduplication decisions with full article content (original_url, duplicate_of_url, similarity_score, dedup_type, original_title, original_summary, duplicate_of_title, llm_reason) |

---

## Metadata Schema

Each config defines its own valid values for `region`, `category`, and `layer` fields in `config.json`. The `extract_metadata` function reads these values and validates LLM output against them.

### business_news Config

**region** - Geographic region where the primary company is headquartered:
| Value | Description |
|-------|-------------|
| `north_america` | USA, Canada, Mexico |
| `latin_america` | South America, Central America, Caribbean |
| `europe` | UK, EU countries, Switzerland, Norway |
| `middle_east` | UAE, Saudi Arabia, Israel, etc. |
| `africa` | All African countries |
| `south_asia` | India, Pakistan, Bangladesh, Sri Lanka |
| `southeast_asia` | Singapore, Indonesia, Vietnam, Thailand, Malaysia, Philippines |
| `east_asia` | China, Japan, South Korea, Taiwan, Hong Kong |
| `oceania` | Australia, New Zealand |
| `global` | Multiple companies from different regions |
| `unknown` | Cannot determine headquarters |

**category** - Type of business news (11 categories):
| Value | Description |
|-------|-------------|
| `funding` | Investment rounds (Seed, Series A/B/C/D, growth equity, debt) |
| `acquisition` | M&A activity (acquisitions, mergers, acqui-hires) |
| `product_launch` | New product/service announcements, hardware/software releases |
| `partnership` | Strategic partnerships, collaborations, integrations |
| `earnings` | Revenue reports, profit/loss, financial results, valuations |
| `expansion` | New markets, geographic expansion, new offices, workforce growth |
| `executive` | Leadership changes, key hires, board appointments, workforce reductions |
| `ipo` | IPO filings, SPAC mergers, public listings |
| `regulation` | Regulatory actions, investigations, compliance, legal settlements |
| `strategy` | Corporate strategy announcements, roadmaps, vision statements |
| `research` | Benchmark releases, open-source models, technical milestones |

**layer** - Position in AI value chain (5-tier model):
| Value | Description |
|-------|-------------|
| `chips_infra` | Semiconductors (NVIDIA, AMD), GPUs, TPUs, cloud, data centers |
| `foundation_models` | Base LLM companies (OpenAI, Anthropic, Google DeepMind, Mistral) |
| `finetuning_mlops` | MLOps platforms, fine-tuning tools, vector databases (W&B, HuggingFace) |
| `b2b_apps` | Enterprise AI applications, vertical AI solutions |
| `consumer_apps` | Consumer-facing AI products, chatbots, creative AI tools |

### ai_tips Config

**region** - Always `global` (tips are universal)

**category** - AI topic/domain (9 categories):
| Value | Description |
|-------|-------------|
| `prompting` | Prompt engineering, chain-of-thought, few-shot, templates |
| `image_gen` | Midjourney, DALL-E, Stable Diffusion, ComfyUI, Flux |
| `video_gen` | Runway, Pika, Sora, Kling, video generation/editing |
| `audio` | Voice cloning, text-to-speech, music generation |
| `agents` | AI agents, autonomous systems, tool use, MCP, function calling |
| `coding` | Cursor, Copilot, Claude Code, code generation, debugging |
| `automation` | Workflows, Zapier/Make integrations, no-code AI |
| `rag` | Retrieval augmented generation, embeddings, vector databases |
| `general` | General AI tips that don't fit above categories |

**layer** - AI modality/tool type (6 layers):
| Value | Description |
|-------|-------------|
| `text_llm` | Text-based LLMs (Claude, ChatGPT, Gemini, Llama) |
| `image_gen` | Image generation tools (Midjourney, DALL-E, Stable Diffusion) |
| `video_gen` | Video generation tools (Runway, Pika, Sora) |
| `audio` | Audio/voice tools (ElevenLabs, Suno, Udio, Whisper) |
| `code_assist` | Code assistants (Cursor, Copilot, Claude Code, Windsurf) |
| `multimodal` | Multiple modalities or cross-tool content |

---

## Running the Pipelines

### Layer 0: Source Quality Assessment (Optional)

```python
import layer0_orchestrator

# Run full quality assessment (default config: business_news)
layer0_orchestrator.run()

# Run for specific URLs only (substring match)
layer0_orchestrator.run(url_filter=['techcrunch', 'inc42'])

# Run for a different config
layer0_orchestrator.run(config="academic_papers")
```

**Features:**
- Fetches homepage and about page for each source
- LLM assesses credibility based on domain reputation and content
- Outputs `source_quality: "quality"` or `"crude"` per source
- Results saved to `data/{config}/source_quality.json`

### Layer 1: RSS Discovery

```python
import rss_orchestrator

# Incremental mode (default) - only check stale sources (>7 days)
rss_orchestrator.run()

# Force full rescan - re-check all sources
rss_orchestrator.run(full_rescan=True)

# Custom refresh period (14 days)
rss_orchestrator.run(refresh_days=14)

# Run for specific URLs only (substring match)
rss_orchestrator.run(url_filter=['.co.kr', 'techcrunch'])

# Run for a different config
rss_orchestrator.run(config="academic_papers")
```

**CLI Usage:**
```bash
# Incremental mode (default)
python rss_orchestrator.py --config business_news

# Force full rescan
python rss_orchestrator.py --config business_news --full-rescan

# Custom refresh period
python rss_orchestrator.py --config business_news --refresh-days 14

# Combine with URL filter
python rss_orchestrator.py --config business_news --url-filter techcrunch
```

**Features:**
- Reads from `configs/{config}/input_urls.json`
- **Incremental Mode (Default):** Skips sources checked within `refresh_days` (default: 7)
- URL filter for testing specific sources
- Results merge with existing `rss_availability.json` (doesn't overwrite)
- Freshness check: AI feeds older than 7 days fall back to main feed
- **RSS Directory Scanning:** Scans `/about/rss`, `/feeds` pages for topic-specific feeds
- For non-AI-focused sites, prefers tech feed > AI feed > main feed

**Incremental Behavior:**
- Each result entry has a `last_checked` timestamp
- Sources checked within `refresh_days` are skipped (default: 7 days)
- New URLs (not in file) are always processed
- Entries without `last_checked` are treated as stale and re-checked
- Use `--full-rescan` to force re-checking all sources
- Output shows `last_run_processed` and `last_run_skipped` counts

**Pipeline Flow:**
```
load_urls -> test_main_rss -> scan_rss_directories -> test_ai_category ->
discover_with_agent -> classify_all_feeds -> merge_results -> save_results
```

**Output Fields:**
- `main_feed_url`: Standard RSS feed
- `tech_feed_url`: Technology-specific feed (from directory scan)
- `ai_feed_url`: AI-specific feed (from category test or directory scan)
- `science_feed_url`: Science-specific feed (from directory scan)
- `directory_page_url`: URL where feeds were discovered
- `recommended_feed_url`: Best feed to use based on site type
- `ai_feed_latest_date`: ISO date of latest AI feed article (for freshness)
- `fallback_reason`: Why main feed was used (e.g., "stale_ai_feed")
- `last_checked`: ISO timestamp of when this URL was last checked

### HTML Layer 1: Scrapability Discovery

```python
import html_layer1_orchestrator

# Incremental mode (default) - only check stale sources (>7 days)
html_layer1_orchestrator.run()

# Force full rescan - re-check all sources
html_layer1_orchestrator.run(full_rescan=True)

# Custom refresh period (14 days)
html_layer1_orchestrator.run(refresh_days=14)

# Run for specific URLs only (substring match)
html_layer1_orchestrator.run(url_filter=['pulsenews', 'rundown'])

# Run for a different config
html_layer1_orchestrator.run(config="academic_papers")
```

**CLI Usage:**
```bash
# Incremental mode (default)
python html_layer1_orchestrator.py --config business_news

# Force full rescan
python html_layer1_orchestrator.py --config business_news --full-rescan

# Custom refresh period
python html_layer1_orchestrator.py --config business_news --refresh-days 14
```

**Features:**
- **Incremental Mode (Default):** Skips sources checked within `refresh_days` (default: 7)
- Respects `html_exclusions` from `config.json` (skips specified domains)
- Tests HTTP accessibility with browser-like headers
- Detects bot protection (Cloudflare, CAPTCHA, JS-redirect)
- LLM analyzes listing page structure (article URL patterns)
- LLM analyzes article pages (CSS selectors for extraction)
- Results merge with existing `data/{config}/html_availability.json`

**Incremental Behavior:**
- Each result entry has an `analyzed_at` timestamp
- Sources checked within `refresh_days` are skipped (default: 7 days)
- New sources (not in file) are always processed
- Use `--full-rescan` to force re-checking all sources
- Output shows `last_run_processed` and `last_run_skipped` counts

**Pipeline Flow:**
```
load_unavailable_sources → test_http_accessibility → analyze_listing_page →
analyze_article_page → classify_html_source → merge_html_results →
save_html_availability
```

**Output Fields:**
- `status`: "scrapable", "requires_js", "blocked", "not_scrapable"
- `listing_page.article_url_pattern`: Regex for article URLs
- `listing_page.sample_urls`: Example article URLs found
- `article_page.title_selector`: CSS selector for title
- `article_page.content_selector`: CSS selector for content
- `article_page.date_selector`: CSS selector for date
- `recommendation.approach`: "http_simple", "playwright", "not_recommended"
- `recommendation.confidence`: 0.0-1.0
- `analyzed_at`: ISO timestamp of when this source was last analyzed

### HTML Layer 2: Content Scraping

```python
import html_layer2_orchestrator

# Run full scraping (default config: business_news)
html_layer2_orchestrator.run()

# Run for specific URLs only (substring match)
html_layer2_orchestrator.run(url_filter=['rundown', 'pulsenews'])

# Custom article age cutoff (e.g., last 48 hours)
html_layer2_orchestrator.run(max_age_hours=48)

# Run for a different config
html_layer2_orchestrator.run(config="academic_papers")
```

**Features:**
- Loads sources with `status="scrapable"` and full config from HTML L1
- Fetches listing pages and extracts article URLs via regex patterns
- Fetches individual articles and extracts content via CSS selectors
- Parses dates using discovered formats
- Reuses L2 pipeline nodes (filter, metadata, summaries)
- Outputs to `data/{config}/html_news.json/csv`

**Pipeline Flow:**
```
load_scrapable_sources → fetch_listing_pages → extract_article_urls →
fetch_html_articles → parse_article_content → adapt_html_to_articles →
filter_by_date → filter_business_news → extract_metadata →
generate_summaries → build_output_dataframe → save_html_content
```

**Limitations:**
- Sources without full config (missing article_page) are skipped
- Max 20 articles per source to avoid overwhelming sites
- 0.5s delay between article fetches

**Output:**
- `data/{config}/html_news.json` - Scraped AI business news with metadata
- `data/{config}/html_news.csv` - CSV format output
- `data/{config}/html_discarded.csv` - Filtered-out articles with discard reasons

### Browser-Use Layer 2: Blocked Sources

```python
import browser_use_orchestrator

# Run full scraping (default config: business_news)
browser_use_orchestrator.run()

# Run for specific URLs only (substring match)
browser_use_orchestrator.run(url_filter=['economictimes', 'scmp'])

# Custom article age cutoff (e.g., last 48 hours)
browser_use_orchestrator.run(max_age_hours=48)

# Run for a different config
browser_use_orchestrator.run(config="academic_papers")
```

**Features:**
- Uses `browser-use` package with Claude Sonnet for LLM-driven browser navigation
- Bypasses CAPTCHA/Cloudflare protection by using real browser
- Agent waits for challenges, navigates pages, extracts article data
- Configured via `config.json["browser_use_sources"]`
- Reuses L2 pipeline nodes (filter, metadata, summaries)
- Outputs to `data/{config}/browser_use_news.json/csv`

**Pipeline Flow:**
```
load_browser_use_sources → fetch_with_browser_agent → adapt_browser_use_to_articles →
filter_by_date → filter_business_news → extract_metadata →
generate_summaries → build_output_dataframe → save_browser_use_content
```

**Enabled Sources (business_news config):**
- Economic Times (tech.economictimes.indiatimes.com)
- SCMP (scmp.com/tech)
- CNBC (cnbc.com/technology/)

**Cost:** ~$0.30-0.50 per source per run (uses Claude Sonnet)

**Output:**
- `data/{config}/browser_use_news.json` - Scraped AI business news with metadata
- `data/{config}/browser_use_news.csv` - CSV format output
- `data/{config}/browser_use_discarded.csv` - Filtered-out articles with discard reasons
- `data/{config}/browser_use_failures.json` - Failed sources with error details

### Layer 2: Content Aggregation

```python
import content_orchestrator

# Run full aggregation (default config: business_news)
content_orchestrator.run()

# Run for specific sources only (substring match on source name or URL)
content_orchestrator.run(source_filter=['techcabal', '36kr'])

# Custom article age cutoff (e.g., last 48 hours)
content_orchestrator.run(max_age_hours=48)

# Combine filters
content_orchestrator.run(source_filter=['techcrunch'], max_age_hours=72)

# Run for a different config
content_orchestrator.run(config="academic_papers")
```

**Features:**
- Source filter for testing specific feeds
- Date cutoff filter to drop articles older than `max_age_hours` (default: 24)
- URL deduplication against SQLite database (skips already-processed articles)
- Discarded articles exported with reasons
- Adaptive batch retry on LLM parse errors
- Outputs to `data/{config}/aggregated_news.json/csv`

**Pipeline Flow:**
```
load_available_feeds -> fetch_rss_content -> check_url_duplicates ->
filter_by_date -> filter_business_news -> extract_metadata ->
generate_summaries -> build_output_dataframe -> save_aggregated_content
```

### Layer 3: Deduplication (Cross-Pipeline)

```python
import dedup_orchestrator

# Run deduplication on all Layer 2 outputs (default config: business_news)
dedup_orchestrator.run()

# Custom lookback period (e.g., last 7 days)
dedup_orchestrator.run(lookback_hours=168)

# Select specific input sources
dedup_orchestrator.run(input_sources=["rss", "html"])  # Exclude Twitter
dedup_orchestrator.run(input_sources=["rss"])  # RSS only (backward compatible)

# Run for a different config
dedup_orchestrator.run(config="academic_papers")
```

**Features:**
- **Multi-source merging:** Combines RSS, HTML, and Twitter Layer 2 outputs
- URL deduplication at merge point (priority: RSS > HTML > Twitter)
- Semantic deduplication using OpenAI embeddings
- Three-tier classification: unique (<0.75), ambiguous (0.75-0.90), duplicate (>0.90)
- LLM confirmation only for ambiguous cases (cost-optimized)
- Tracks `source_type` field for each article (rss, html, twitter)
- Cross-source duplicate detection (same news from different pipelines)
- Stores articles with embeddings to SQLite for future comparison
- First run seeds database without deduplication
- Outputs to `data/{config}/merged_news_deduped.json/csv`

**Pipeline Flow:**
```
merge_pipeline_outputs -> generate_embeddings -> load_historical_embeddings ->
compare_similarities -> llm_confirm_duplicates -> store_articles ->
export_dedup_report
```

**Input Files:**
- `data/aggregated_news.json` - RSS Layer 2 output
- `data/html_news.json` - HTML Layer 2 output
- `data/twitter_news.json` - Twitter Layer 2 output

**Output Files:**
- `data/{config}/merged_news_deduped.json` - Deduplicated articles from all sources
- `data/{config}/merged_news_deduped.csv` - CSV format with source_type column
- `data/{config}/dedup_report.json` - Deduplication statistics (includes cross-source stats)
- `data/{config}/articles.db` - SQLite database with embeddings

**Cost Estimate:**
- Embeddings (OpenAI): ~$0.001 per run
- LLM confirmation (Haiku): ~$0.01-0.02 (only for ambiguous cases)
- Total: ~$0.02-0.03 per run

### Twitter Layer 1: Account Discovery

```python
import twitter_layer1_orchestrator

# Single-config: Run for one config
twitter_layer1_orchestrator.run(config="business_news")

# Single-config: Filter specific handles
twitter_layer1_orchestrator.run(config="business_news", handle_filter=['@OpenAI'])

# Multi-config: Consolidated scraping (each handle scraped ONCE)
twitter_layer1_orchestrator.run_multi(configs=["business_news", "ai_tips"])

# Multi-config: Full pipeline (L1 + L2 for each config)
twitter_layer1_orchestrator.run_all(configs=["business_news", "ai_tips"])
```

**CLI Usage:**
```bash
# Single-config
python twitter_layer1_orchestrator.py --config=business_news

# Multi-config (consolidated L1 only)
python twitter_layer1_orchestrator.py --configs business_news ai_tips

# Multi-config with full pipeline (L1 + L2 for each config)
python twitter_layer1_orchestrator.py --configs business_news ai_tips --run-all
```

**Features:**
- Scrapes tweets via Playwright GraphQL API interception
- Analyzes account activity (tweets per day, last tweet date)
- Marks accounts as "active" or "inactive" (no tweets in N days)
- Caches raw tweets for Layer 2 (no re-scraping needed)
- **Multi-config mode:** Deduplicates handles across configs, scrapes each once
- Results merge with existing availability files

**Output Files (single-config):**
- `data/{config}/twitter_availability.json` - Account status and metrics
- `data/{config}/twitter_raw_cache.json` - Raw tweets for Layer 2

**Output Files (multi-config):**
- `data/shared/twitter_raw_cache.json` - Shared cache for all configs

**Pipeline Flow:**
```
load_twitter_accounts → fetch_twitter_content → analyze_account_activity →
save_twitter_availability
```

### Twitter Layer 2: Content Aggregation

```python
import twitter_layer2_orchestrator

# Run full aggregation (default config: business_news)
twitter_layer2_orchestrator.run(config="business_news")

# Run for specific handles only (substring match)
twitter_layer2_orchestrator.run(config="business_news", handle_filter=['@OpenAI'])

# Custom tweet age cutoff (e.g., last 7 days)
twitter_layer2_orchestrator.run(config="business_news", max_age_hours=168)

# Use shared cache (after running multi-config L1)
twitter_layer2_orchestrator.run(config="business_news", use_shared_cache=True)
```

**CLI Usage:**
```bash
# Standard (reads from config-specific cache)
python twitter_layer2_orchestrator.py --config=business_news

# Use shared cache (after multi-config L1)
python twitter_layer2_orchestrator.py --config=business_news --use-shared-cache
```

**Features:**
- Reads from Layer 1 output (only active accounts)
- Uses cached tweets (no re-scraping)
- **Shared cache mode:** Reads from `data/shared/` and filters to config's handles
- Reuses `filter_business_news`, `extract_metadata`, `generate_summaries` from RSS Layer 2
- Same 8-field output schema as RSS pipeline
- Discarded tweets exported with reasons
- Outputs to `data/{config}/twitter_news.json/csv`

**Pipeline Flow:**
```
load_available_accounts → load_cached_tweets → filter_by_date_twitter →
fetch_link_content → adapt_tweets_to_articles → filter_business_news →
extract_metadata → generate_summaries → build_twitter_output → save_twitter_content
```

### Twitter Configuration

Edit `configs/{config}/twitter_accounts.json` to add/remove accounts:

```json
{
  "accounts": [
    {"handle": "@OpenAI", "category": "AI company"},
    {"handle": "@AnthropicAI", "category": "AI company"}
  ],
  "settings": {
    "scrape_delay_min": 55,
    "scrape_delay_max": 65,
    "max_age_hours": 24,
    "inactivity_threshold_days": 14,
    "cache_ttl_hours": 24
  }
}
```

**Settings:**
- `scrape_delay_min`/`scrape_delay_max`: Randomized rate limiting between accounts (default: 55-65s)
- `max_age_hours`: Tweet age cutoff for L2 (default: 24)
- `inactivity_threshold_days`: Days without tweets = inactive (default: 14)
- `cache_ttl_hours`: Cache validity period (default: 24)

### Twitter Authentication (Required)

Twitter restricts non-authenticated users to curated "highlights" instead of chronological timelines. The scraper requires session cookies from a logged-in browser.

**Setup (one-time):**

1. Launch Chrome with remote debugging:
   ```bash
   # Linux
   google-chrome --remote-debugging-port=9222 --user-data-dir="$HOME/chrome-twitter"

   # Windows
   chrome.exe --remote-debugging-port=9222 --user-data-dir="C:\chrome-twitter"
   ```

2. Log in to Twitter manually in that browser

3. Run the cookie extraction script:
   ```bash
   python twitter_cdp_login.py --port 9222 --test
   ```

4. Cookies are saved to `chrome_data/twitter_cookies.json`

The scraper automatically loads these cookies on each run. Re-run `twitter_cdp_login.py` if cookies expire (typically after a few weeks).

### Twitter Rate Limiting & Ban Prevention

**⚠️ CAUTION: Aggressive scraping may result in account suspension.**

Best practices to avoid bans:
- Keep `scrape_delay_min`/`scrape_delay_max` at 55-65+ seconds between accounts
- Limit scraping to a few times per day
- Don't scrape more than 20-30 accounts per session
- Use a secondary/throwaway Twitter account for authentication
- If you get rate-limited, wait 15+ minutes before retrying
- Monitor for 429 (Too Many Requests) errors in logs

**Signs of rate limiting:**
- Empty tweet responses
- 429 HTTP status codes
- Account temporarily locked warnings

**If banned:**
- The authenticated account may be suspended
- Create a new account and re-authenticate
- Consider reducing scraping frequency

### Manual Cleanup Scripts

One-time utilities for DB maintenance (not part of regular pipeline):

```bash
# Remove garbage articles (reactions, hype, link-only)
python cleanup_garbage.py --configs business_news ai_tips --dry-run
python cleanup_garbage.py --configs business_news ai_tips --export

# Fix bad summaries (too long, not Korean)
python regenerate_summaries.py --configs business_news ai_tips --dry-run
python regenerate_summaries.py --configs business_news ai_tips --export
```
