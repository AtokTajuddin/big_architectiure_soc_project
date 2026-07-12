---
name: dticlaw-research
description: "Deep multi-hop web research with source synthesis, confidence scoring, and citation. Use for research, analysis, market intel, atau studi literatur."
metadata: { "openclaw": { "emoji": "🔬" } }
allowed-tools: ["web_search", "web_fetch", "memory_search", "memory_get", "write", "read", "exec"]
user-invocable: true
---

# DTIClaw Deep Research

Multi-hop iterative research engine. Break complex query → search → fetch → synthesize → cross-reference → follow-up.

## Workflow

### Phase 1: Plan
- Break user query into 2-5 sub-queries
- Identify knowledge gaps that need follow-up

### Phase 2: Search (parallel)
- `web_search` each sub-query
- Collect 3-10 sources per sub-query
- Filter by relevance, recency, authority

### Phase 3: Fetch & Extract
- `web_fetch` top sources (max 15 total)
- Extract: key claims, data points, dates, names
- Flag: paywalled, low-quality, outdated

### Phase 4: Synthesize
- Per sub-topic: summarize findings
- Cross-reference between sources
- Identify agreements, contradictions, gaps

### Phase 5: Follow-up (recursive, max 3 rounds)
- If gaps found → new sub-query → search → fetch
- If contradictions → hunt for authoritative source

### Phase 6: Report
- Structured output with:
  - Executive summary (3-5 sentences)
  - Detailed findings per sub-topic
  - Source citations (URL + date accessed)
  - Confidence level per claim (CERTAIN/HIGH/MODERATE/LOW)
  - Unresolved questions

## Confidence Scoring

| Level | Criteria |
|-------|----------|
| CERTAIN | 3+ independent authoritative sources agree |
| HIGH | 2+ credible sources agree, no contradictions |
| MODERATE | 1 source or sources with minor discrepancies |
| LOW | Inference, single weak source, or significant gaps |
| UNKNOWN | No sources found |

## Output Format

```markdown
# Research: [query]
**Date:** [today]
**Sources:** [count] | **Confidence:** [overall]

## Executive Summary
[3-5 sentences]

## Findings
### [Sub-topic 1]
[findings with citations]

### [Sub-topic 2]
...

## Source List
1. [title] — [url] (accessed [date])
...

## Confidence Map
| Claim | Confidence | Sources |
|-------|------------|---------|
| ... | ... | ... |
```

## Safety
- Never fabricate citations — mark UNKNOWN if not found
- Flag outdated sources (>2 years for tech, >5 for general)
- State "I could not find" bukan bikin klaim palsu
- Bahasa Indonesia default, English when appropriate
