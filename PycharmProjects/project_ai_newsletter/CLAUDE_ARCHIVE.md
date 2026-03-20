# CLAUDE_ARCHIVE.md - Development Rules (Archived)

These coding conventions were used during the building phase. Kept for reference.

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
