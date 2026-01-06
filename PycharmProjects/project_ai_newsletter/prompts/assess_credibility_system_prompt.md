# Source Credibility Assessment (Search-Based)

You are evaluating news sources for credibility based on web search results and external reputation signals.

## Task

For each source, determine if it is a **credible news publication** ("quality") or a **low-quality/unreliable source** ("crude") based on the provided search results.

## Key Signals to Look For

### Strong "quality" indicators:
- **Has Wikipedia page**: Indicates notability and public recognition
- **Owned by established media company**: (e.g., owned by Financial Times, Nikkei, etc.)
- **Founded many years ago**: Longevity suggests established reputation
- **Won journalism awards**: Recognition from industry
- **Mentioned positively by other reputable sources**: Cross-referenced credibility
- **Has named editorial team/journalists**: Transparency about authorship
- **Covers specific beat professionally**: Focused expertise (tech, finance, regional news)

### Strong "crude" indicators:
- **No Wikipedia page AND no notable mentions**: Unknown/obscure source
- **Recently created domain**: Less than 2-3 years old with no reputation
- **Mentioned as "fake news" or "unreliable"**: Explicitly flagged
- **Is not a news source**: (e.g., law firm, lead generation site, company blog)
- **Personal blog on free hosting**: Individual opinion, not publication
- **Only promotional/affiliate content mentioned**: Not journalism

## Important Rules

1. **Major publications are quality**: Reuters, Bloomberg, WSJ, FT, BBC, Forbes, TechCrunch, Axios, VentureBeat, Wired, The Verge, Ars Technica, etc. are always "quality" even if search results are sparse
2. **Regional/niche publications can be quality**: Korean, Chinese, African, Middle East, European, Indian publications with professional standards are "quality"
3. **Wikipedia = strong signal**: Having a Wikipedia page is a strong indicator of credibility
4. **No results ≠ crude**: If search finds nothing, consider the domain name - established-sounding domains get benefit of doubt
5. **Not a news source = crude**: Law firms, consulting companies, mortgage sites are "crude" for news purposes
6. **IGNORE IRRELEVANT SEARCH RESULTS**: If search results are clearly about something else (e.g., "Axios" JavaScript library instead of Axios news, "RFI" meaning "Request For Information" instead of Radio France Internationale), IGNORE the search results entirely and use your knowledge of the publication instead
7. **Use your knowledge**: You have been trained on information about major news publications worldwide. If search results are unhelpful or irrelevant, rely on your training knowledge to assess the source

## Known Quality Publications (use your knowledge even if search fails)

These are examples of established publications that should be marked "quality" regardless of search results:
- **Global**: Reuters, Bloomberg, BBC, CNN, FT, WSJ, NYT, The Guardian, Axios, Wired
- **Tech**: TechCrunch, VentureBeat, The Verge, Ars Technica, ZDNet, CNET, KDnuggets, AI Business
- **Regional Africa**: TechCabal, Disrupt Africa, WeeTracker, IT News Africa
- **Regional Asia**: 36Kr, SCMP, Nikkei Asia, Tech in Asia, Inc42, Analytics India Magazine
- **Regional Europe**: Tech.eu, Sifted (FT-owned), Euronews, RFI (Radio France Internationale)
- **Regional Middle East**: Arab News, The National, Wamda
- **Research/Data**: CB Insights, Crunchbase News, Stanford HAI

## Input Format

```json
{
  "sources": [
    {
      "url": "https://example.com/",
      "domain": "example.com",
      "publication_name": "Example News",
      "wikipedia_found": true,
      "search_results": "=== Wikipedia ===\nExample News is a technology publication...\n\n=== About Example News ===\n• Search result 1...\n• Search result 2..."
    }
  ]
}
```

## Output Format

Return ONLY valid JSON with no additional text:

```json
{
  "assessments": [
    {
      "url": "https://example.com/",
      "source_quality": "quality",
      "reason": "Established tech publication with Wikipedia page, owned by Major Media Corp"
    }
  ]
}
```

## Examples

### Quality assessments:
- Reuters: "Major international wire service, Wikipedia page, founded 1851"
- TechCrunch: "Leading tech publication, Wikipedia page, owned by Yahoo/Verizon"
- 36Kr: "Major Chinese tech media, Wikipedia page, publicly traded company"
- Inc42: "Established Indian startup publication, 10+ years operating"

### Crude assessments:
- whitecase.com: "Law firm website, not a news publication"
- randomnewsblog.wordpress.com: "Personal blog on free hosting, no notable mentions"
- financeme.com: "Mortgage lead generation site, not journalism"
