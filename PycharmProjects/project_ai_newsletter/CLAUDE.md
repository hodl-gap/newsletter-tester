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
- Generate concise English summaries (1-2 sentences)
- Extract metadata (region, category, AI layer)
- URL deduplication against historical DB (saves LLM costs)

**Layer 3: Deduplication** (runs after Layer 2)
- Semantic deduplication using OpenAI embeddings
- Compares new articles against last 48h of stored articles
- Three-tier classification: unique (<0.75), ambiguous (0.75-0.90), duplicate (>0.90)
- LLM confirmation for ambiguous cases only (cost-optimized)
- Stores articles with embeddings to SQLite for future comparison
- Output: `aggregated_news_deduped.json`, `dedup_report.json`

**Twitter Pipeline** (independent, parallel to Layer 2) - **FIXED (2026-01-06)**
- Scrape tweets from configured Twitter/X accounts
- Uses Playwright to intercept GraphQL API responses
- **Requires authenticated session cookies** (see Twitter Authentication below)
- Same LLM filtering and metadata extraction as Layer 2
- Rate-limited (30s delay between accounts)
- Output: Same 8-field schema as RSS pipeline

---

## Architecture

### Folder Structure

```
project_ai_newsletter/
├── orchestrator.py           # Main orchestrator (placeholder)
├── layer0_orchestrator.py    # Layer 0: Source quality assessment
├── rss_orchestrator.py       # Layer 1: RSS discovery orchestrator
├── content_orchestrator.py   # Layer 2: Content aggregation orchestrator
├── dedup_orchestrator.py     # Layer 3: Deduplication orchestrator
├── twitter_orchestrator.py   # Twitter: Tweet scraping pipeline (legacy)
├── twitter_layer1_orchestrator.py  # Twitter L1: Account discovery
├── twitter_layer2_orchestrator.py  # Twitter L2: Content aggregation
├── twitter_cdp_login.py       # Twitter: CDP cookie extraction script
├── twitter_login.py           # Twitter: Alternative Playwright login (less reliable)
├── src/
│   ├── __init__.py
│   ├── models.py             # All LLM model definitions and helpers
│   ├── utils.py              # Utility functions (prompt loading, etc.)
│   ├── tracking.py           # Time and cost tracking utilities
│   ├── database.py           # SQLite database for article storage
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
│       ├── generate_embeddings.py
│       ├── load_historical_embeddings.py
│       ├── compare_similarities.py
│       ├── llm_confirm_duplicates.py
│       ├── store_articles.py
│       ├── export_dedup_report.py
│       │── # Twitter L1 functions
│       ├── load_twitter_accounts.py
│       ├── fetch_twitter_content.py
│       ├── analyze_account_activity.py
│       ├── save_twitter_availability.py
│       │── # Twitter L2 functions
│       ├── load_available_twitter_accounts.py
│       ├── load_cached_tweets.py
│       ├── filter_by_date_twitter.py
│       ├── build_twitter_output.py
│       └── save_twitter_content.py
├── prompts/                  # All LLM prompts (markdown format)
│   │── # Layer 0 prompts
│   ├── assess_credibility_system_prompt.md
│   │── # Layer 1 prompts
│   ├── discover_rss_agent_system_prompt.md
│   ├── classify_feeds_system_prompt.md
│   │── # Layer 2 prompts
│   ├── filter_business_news_system_prompt.md
│   ├── extract_metadata_system_prompt.md
│   ├── generate_summary_system_prompt.md
│   │── # Layer 3 prompts
│   └── confirm_duplicate_system_prompt.md
├── data/                     # Input/output data files
│   ├── input_urls.json       # URLs to process (Layer 0/1 input)
│   ├── source_quality.json   # Source quality ratings (Layer 0 output)
│   ├── rss_availability.json # RSS discovery results (Layer 1 output)
│   ├── aggregated_news.json  # Aggregated content (Layer 2 output)
│   ├── aggregated_news.csv   # CSV format output (Layer 2 output)
│   ├── discarded_news.csv    # Filtered-out articles with reasons (Layer 2 output)
│   ├── articles.db           # SQLite database (Layer 3)
│   ├── aggregated_news_deduped.json  # Deduplicated content (Layer 3 output)
│   ├── aggregated_news_deduped.csv   # CSV format output (Layer 3 output)
│   ├── dedup_report.json     # Deduplication report (Layer 3 output)
│   ├── twitter_accounts.json      # Twitter accounts config (Twitter input)
│   ├── twitter_availability.json  # Twitter L1 output: Account status
│   ├── twitter_raw_cache.json     # Twitter L1 output: Cached tweets for L2
│   ├── twitter_news.json          # Twitter L2 output: Aggregated content
│   ├── twitter_news.csv           # Twitter L2 output: CSV format
│   └── twitter_discarded.csv      # Twitter L2 output: Filtered-out tweets
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

### 4. Prompts (`prompts/`)

- **All LLM prompts** must be stored in the `prompts/` folder
- Format: Markdown (`.md`)
- Naming convention: `{function_name}_{description}_prompt.md`
  - Example: `summarize_article_system_prompt.md`
  - Example: `generate_newsletter_user_prompt.md`
- Prompts must be loaded from files, never hardcoded in function files
- Use placeholders like `{variable}` for dynamic content

```python
# Example prompt loading
from pathlib import Path

def load_prompt(filename: str) -> str:
    return Path(f"prompts/{filename}").read_text()

prompt = load_prompt("summarize_article_system_prompt.md")
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

| File | Description |
|------|-------------|
| `data/source_quality.json` | Layer 0 output: Source credibility ratings ("quality" or "crude") |
| `data/rss_availability.json` | Layer 1 output: RSS feed discovery results |
| `data/aggregated_news.json` | Layer 2 output: AI business news with metadata |
| `data/aggregated_news.csv` | Layer 2 output: Same as JSON in tabular format |
| `data/discarded_news.csv` | Layer 2 output: Filtered-out articles with discard reasons |
| `data/articles.db` | Layer 3: SQLite database with articles and embeddings |
| `data/aggregated_news_deduped.json` | Layer 3 output: Deduplicated AI business news |
| `data/aggregated_news_deduped.csv` | Layer 3 output: Same as JSON in tabular format |
| `data/dedup_report.json` | Layer 3 output: Deduplication statistics and details |
| `data/twitter_availability.json` | Twitter L1 output: Account status and activity metrics |
| `data/twitter_raw_cache.json` | Twitter L1 output: Cached tweets for L2 consumption |
| `data/twitter_news.json` | Twitter L2 output: AI business news from tweets |
| `data/twitter_news.csv` | Twitter L2 output: Same as JSON in tabular format |
| `data/twitter_discarded.csv` | Twitter L2 output: Filtered-out tweets with discard reasons |

---

## Running the Pipelines

### Layer 0: Source Quality Assessment (Optional)

```python
import layer0_orchestrator

# Run full quality assessment
layer0_orchestrator.run()

# Run for specific URLs only (substring match)
layer0_orchestrator.run(url_filter=['techcrunch', 'inc42'])
```

**Features:**
- Fetches homepage and about page for each source
- LLM assesses credibility based on domain reputation and content
- Outputs `source_quality: "quality"` or `"crude"` per source
- Results saved to `data/source_quality.json`

### Layer 1: RSS Discovery

```python
import rss_orchestrator

# Run full discovery (re-checks ALL sources)
rss_orchestrator.run()

# Run for specific URLs only (substring match)
rss_orchestrator.run(url_filter=['.co.kr', 'techcrunch'])
```

**Features:**
- Reads from `input_urls.json` (L0 integration disabled)
- URL filter for testing specific sources
- Results merge with existing `rss_availability.json` (doesn't overwrite)
- Freshness check: AI feeds older than 7 days fall back to main feed
- **RSS Directory Scanning:** Scans `/about/rss`, `/feeds` pages for topic-specific feeds
- For non-AI-focused sites, prefers tech feed > AI feed > main feed

**Re-Run Behavior:**
- Layer 1 is NOT incremental - re-checks ALL sources every run
- Results are **merged** with existing entries (update existing, add new, preserve old)
- Old entries may lack newer fields (e.g., `ai_feed_latest_date`, `fallback_reason`)
- To update specific sources: `rss_orchestrator.run(url_filter=['techcabal'])`

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

### Layer 2: Content Aggregation

```python
import content_orchestrator

# Run full aggregation (default: 24-hour article cutoff)
content_orchestrator.run()

# Run for specific sources only (substring match on source name or URL)
content_orchestrator.run(source_filter=['techcabal', '36kr'])

# Custom article age cutoff (e.g., last 48 hours)
content_orchestrator.run(max_age_hours=48)

# Combine filters
content_orchestrator.run(source_filter=['techcrunch'], max_age_hours=72)
```

**Features:**
- Source filter for testing specific feeds
- Date cutoff filter to drop articles older than `max_age_hours` (default: 24)
- URL deduplication against SQLite database (skips already-processed articles)
- Discarded articles exported with reasons
- Adaptive batch retry on LLM parse errors

**Pipeline Flow:**
```
load_available_feeds -> fetch_rss_content -> check_url_duplicates ->
filter_by_date -> filter_business_news -> extract_metadata ->
generate_summaries -> build_output_dataframe -> save_aggregated_content
```

### Layer 3: Deduplication

```python
import dedup_orchestrator

# Run deduplication on Layer 2 output (default: 48h lookback)
dedup_orchestrator.run()

# Custom lookback period (e.g., last 7 days)
dedup_orchestrator.run(lookback_hours=168)
```

**Features:**
- Reads from `aggregated_news.json` (Layer 2 output)
- URL deduplication (exact match against historical DB)
- Semantic deduplication using OpenAI embeddings
- Three-tier classification: unique (<0.75), ambiguous (0.75-0.90), duplicate (>0.90)
- LLM confirmation only for ambiguous cases (cost-optimized)
- Stores articles with embeddings to SQLite for future comparison
- First run seeds database without deduplication

**Pipeline Flow:**
```
load_new_articles -> generate_embeddings -> load_historical_embeddings ->
compare_similarities -> llm_confirm_duplicates -> store_articles ->
export_dedup_report
```

**Output Files:**
- `data/aggregated_news_deduped.json` - Deduplicated articles
- `data/aggregated_news_deduped.csv` - CSV format
- `data/dedup_report.json` - Deduplication statistics
- `data/articles.db` - SQLite database with embeddings

**Cost Estimate:**
- Embeddings (OpenAI): ~$0.001 per run
- LLM confirmation (Haiku): ~$0.01-0.02 (only for ambiguous cases)
- Total: ~$0.02-0.03 per run

### Twitter Layer 1: Account Discovery

```python
import twitter_layer1_orchestrator

# Run full discovery (all accounts)
twitter_layer1_orchestrator.run()

# Run for specific handles only (substring match)
twitter_layer1_orchestrator.run(handle_filter=['@OpenAI'])
```

**Features:**
- Scrapes tweets via Playwright GraphQL API interception
- Analyzes account activity (tweets per day, last tweet date)
- Marks accounts as "active" or "inactive" (no tweets in N days)
- Caches raw tweets for Layer 2 (no re-scraping needed)
- Results merge with existing `twitter_availability.json`

**Output Files:**
- `data/twitter_availability.json` - Account status and metrics
- `data/twitter_raw_cache.json` - Raw tweets for Layer 2

**Pipeline Flow:**
```
load_twitter_accounts → fetch_twitter_content → analyze_account_activity →
save_twitter_availability
```

### Twitter Layer 2: Content Aggregation

```python
import twitter_layer2_orchestrator

# Run full aggregation (default: 24-hour tweet cutoff)
twitter_layer2_orchestrator.run()

# Run for specific handles only (substring match)
twitter_layer2_orchestrator.run(handle_filter=['@OpenAI'])

# Custom tweet age cutoff (e.g., last 7 days)
twitter_layer2_orchestrator.run(max_age_hours=168)

# Combine filters
twitter_layer2_orchestrator.run(handle_filter=['@OpenAI'], max_age_hours=72)
```

**Features:**
- Reads from Layer 1 output (only active accounts)
- Uses cached tweets (no re-scraping)
- Reuses `filter_business_news`, `extract_metadata`, `generate_summaries` from RSS Layer 2
- Same 8-field output schema as RSS pipeline
- Discarded tweets exported with reasons

**Pipeline Flow:**
```
load_available_accounts → load_cached_tweets → filter_by_date_twitter →
adapt_tweets_to_articles → filter_business_news → extract_metadata →
generate_summaries → build_twitter_output → save_twitter_content
```

### Twitter Configuration

Edit `data/twitter_accounts.json` to add/remove accounts:

```json
{
  "accounts": [
    {"handle": "@OpenAI", "category": "AI company"},
    {"handle": "@AnthropicAI", "category": "AI company"}
  ],
  "settings": {
    "scrape_delay_seconds": 30,
    "max_age_hours": 24,
    "inactivity_threshold_days": 14,
    "cache_ttl_hours": 24
  }
}
```

**Settings:**
- `scrape_delay_seconds`: Rate limiting between accounts (default: 30)
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
- Keep `scrape_delay_seconds` at 30+ seconds between accounts
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
