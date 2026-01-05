# CLAUDE.md - Project Guidelines

## Project Overview

AI Newsletter Aggregator - a system to collect and aggregate content from various newsletter sources using LangGraph/LangChain for orchestration.

---

## Project Purpose

### Two Orchestrative Layers

**Layer 1: Source Discovery** (prerequisite)
- Find ways to access newsletter content (RSS, API, scraping)
- Test availability (public, paywalled, non-existent)
- Output: List of sources with access methods

**Layer 2: Content Aggregation** (depends on Layer 1)
- Fetch actual content from discovered sources
- Filter for AI business news
- Generate concise English summaries (1-2 sentences)
- Extract metadata (region, category, AI layer)

---

## Architecture

### Folder Structure

```
project_ai_newsletter/
├── orchestrator.py           # Main orchestrator (placeholder)
├── rss_orchestrator.py       # Layer 1: RSS discovery orchestrator
├── content_orchestrator.py   # Layer 2: Content aggregation orchestrator
├── src/
│   ├── __init__.py
│   ├── models.py             # All LLM model definitions and helpers
│   ├── utils.py              # Utility functions (prompt loading, etc.)
│   ├── tracking.py           # Time and cost tracking utilities
│   └── functions/            # Node functions (one file per function)
│       ├── __init__.py
│       │── # Layer 1 functions
│       ├── test_rss_preset.py
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
│       └── save_aggregated_content.py
├── prompts/                  # All LLM prompts (markdown format)
│   │── # Layer 1 prompts
│   ├── discover_rss_agent_system_prompt.md
│   ├── classify_feeds_system_prompt.md
│   │── # Layer 2 prompts
│   ├── filter_business_news_system_prompt.md
│   ├── extract_metadata_system_prompt.md
│   └── generate_summary_system_prompt.md
├── data/                     # Input/output data files
│   ├── input_urls.json       # URLs to process (Layer 1 input)
│   ├── rss_availability.json # RSS discovery results (Layer 1 output)
│   ├── aggregated_news.json  # Aggregated content (Layer 2 output)
│   ├── aggregated_news.csv   # CSV format output (Layer 2 output)
│   └── discarded_news.csv    # Filtered-out articles with reasons (Layer 2 output)
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
| RSS Orchestrator | `rss_orchestrator.py` | - |
| Content Orchestrator | `content_orchestrator.py` | - |
| Node functions | `src/functions/` | `{name}.py` |
| LLM models | `src/models.py` | - |
| Tracking | `src/tracking.py` | - |
| Prompts | `prompts/` | `{func}_{desc}_prompt.md` |
| Data files | `data/` | `{name}.json` or `{name}.csv` |
| Tests | `tests/` | `test_{name}.py` |

## Output Files

| File | Description |
|------|-------------|
| `data/rss_availability.json` | Layer 1 output: RSS feed discovery results |
| `data/aggregated_news.json` | Layer 2 output: AI business news with metadata |
| `data/aggregated_news.csv` | Layer 2 output: Same as JSON in tabular format |
| `data/discarded_news.csv` | Layer 2 output: Filtered-out articles with discard reasons |
