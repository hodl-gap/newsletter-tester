# Layer 2: Content Aggregation - Requirements & Plan

## User Request (2026-01-04)

### Goal
Build a pipeline that aggregates AI **business/company news** (NOT technical research):
- Funding rounds, M&A, startup launches, revenue reports
- NOT: "new transformer model increases score by 37%"
- YES: "Indian startup XYZ raised $20M with brain-reading AI"

### Output Format
DataFrame/JSON with columns:

| Column | Description |
|--------|-------------|
| date | Publication date (YYYY-MM-DD) |
| source | Publication name |
| region | Region mentioned IN the article (LLM-extracted) |
| category | funding, acquisition, product_launch, partnership, earnings, expansion, executive, ipo, layoff, other |
| layer | 5-tier AI value chain position |
| contents | Article summary |
| url | Article URL |

### AI Layer Classification (5-tier)
1. **chips_infra** - Semiconductors, GPUs, cloud, data centers
2. **foundation_models** - Base LLM companies (OpenAI, Anthropic, etc.)
3. **finetuning_mlops** - MLOps platforms, training infrastructure
4. **b2b_apps** - Enterprise AI applications
5. **consumer_apps** - Consumer-facing AI products

### Content Requirements
- Need evaluation framework to test if RSS description is sufficient
- If not sufficient, use LLM to summarize full article content
- Region should be extracted FROM the article, not the publication's location

---

## Initial Plan

### Pipeline Architecture

```
[load_available_feeds] ──→ Read 27 feeds from rss_availability.json
        │
[fetch_rss_content] ─────→ Fetch & parse RSS XML with feedparser
        │
[filter_business_news] ──→ LLM batch filter (25 articles/call)
        │                  KEEP: funding, M&A, startups, launches
        │                  DISCARD: technical research, tutorials
        │
[evaluate_content_sufficiency] → Sample 10-20% of articles
        │                        Score description vs full content
        │                        Decide: use descriptions or summaries
        │
[extract_metadata] ──────→ LLM batch extraction (15 articles/call)
        │                  Extract: region, category, layer
        │
[generate_summaries] ────→ Conditional: only if descriptions insufficient
        │
[build_output_dataframe] → Assemble final output format
        │
[save_aggregated_content] → Write to data/aggregated_news.json + .csv
```

### Files Created

**Orchestrator:**
- `content_orchestrator.py`

**Node Functions (src/functions/):**
- `load_available_feeds.py`
- `fetch_rss_content.py`
- `filter_business_news.py`
- `evaluate_content_sufficiency.py`
- `extract_metadata.py`
- `generate_summaries.py`
- `build_output_dataframe.py`
- `save_aggregated_content.py`

**Prompts (prompts/):**
- `filter_business_news_system_prompt.md`
- `evaluate_content_sufficiency_system_prompt.md`
- `extract_metadata_system_prompt.md`
- `generate_summary_system_prompt.md`

---

## Test Run Results (2026-01-04)

### Pipeline Progress
- **Feeds loaded:** 27
- **Articles fetched:** 524 (deduplicated)
- **After filtering:** 379 kept, 145 discarded
- **Content sufficiency:** Score 3.8/5 → Using descriptions (no summaries)
- **Metadata extraction:** Interrupted at batch 16/26

### Cost Breakdown (PROBLEM!)

| Node | Calls | Total Cost | Avg/Call | % of Total |
|------|-------|------------|----------|------------|
| filter_business_news | 21 | $0.90 | $0.043 | **61%** |
| extract_metadata | 15 | $0.54 | $0.036 | **37%** |
| evaluate_content_sufficiency | 1 | $0.03 | $0.034 | 2% |
| **TOTAL (partial run)** | 37 | **$1.47** | - | - |

**Projected full run cost: ~$2.50**

### Cost Issue Analysis

**Problem:** Using `claude-sonnet-4` for all LLM tasks

**filter_business_news** is the biggest cost driver (61%):
- Simple binary classification (business news yes/no)
- Does NOT need Sonnet's reasoning capability
- Could use `claude-haiku` at ~1/10th cost

**Recommended Model Assignment:**

| Task | Current Model | Recommended | Est. Savings |
|------|---------------|-------------|--------------|
| filter_business_news | claude-sonnet-4 | claude-haiku | ~90% |
| extract_metadata | claude-sonnet-4 | claude-sonnet-4 | - |
| evaluate_content_sufficiency | claude-sonnet-4 | claude-sonnet-4 | - |
| generate_summaries | claude-sonnet-4 | claude-sonnet-4 | - |

**Projected optimized cost:** ~$0.60-0.80 per full run

---

## Next Steps

### Cost Optimization

1. [ ] **Switch model for filtering** → Use claude-haiku instead of sonnet
   - Projected: $0.90 → $0.09 (90% savings)

2. [ ] **Increase batch sizes** → Fewer LLM calls
   | Node | Current | Optimized | Calls Reduction |
   |------|---------|-----------|-----------------|
   | filter_business_news | 25/call | 50/call | 21 → 11 |
   | extract_metadata | 15/call | 25/call | 26 → 16 |

3. [ ] Re-run full pipeline with optimized costs
4. [ ] Validate output quality (ensure Haiku accuracy is acceptable)
