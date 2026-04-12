---
phase: quick
plan: 01
type: execute
tags: [gliner, entity-extraction, truncation, fix]
completed_at: "2026-04-12T20:22:00Z"
---

# Quick Task 260412-iji: Fix GLiNER Truncation

**One-liner:** Fixed entity extraction truncation by processing text sources separately instead of concatenating.

## Problem

GLiNER was truncating combined text (bio + pinned + external + 50 tweets) from 2874+ tokens to 384 tokens, losing entity information from recent tweets.

## Solution

- Added `_chunk_text()` helper to split long text into ~1200 char chunks
- Process each source (bio, pinned, external_bio, tweets) separately
- Merge and dedupe entities from all sources
- Eliminates truncation warnings

## Files Modified

| File | Changes |
|------|---------|
| `src/scrape/entities.py` | Rewrote extract_entities() to process sources separately |

## Commit

1ec324e
