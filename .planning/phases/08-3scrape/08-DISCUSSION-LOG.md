# Phase 8: 3scrape - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-11
**Phase:** 08-3scrape
**Areas discussed:** Entity Extraction Scope, Google Search Trigger, Link Following Depth, Embedding Integration

---

## Entity Extraction Scope

| Option | Description | Selected |
|--------|-------------|----------|
| ORG + LOC + JOB_TITLE (Recommended) | Extract organization, location, and job title. These add the most clustering signal — they reveal community, geography, and profession. | ✓ |
| ORG + LOC + JOB_TITLE + PERSON | Additionally extract person names. Adds some signal but less impactful for clustering quality. | |
| Custom set — I'll specify | Let me decide which entity types based on the research findings. | |

**User's choice:** ORG + LOC + JOB_TITLE (Recommended)

---

## Entity Extraction: Text Fields

| Option | Description | Selected |
|--------|-------------|----------|
| Bio + pinned_tweet_text (Recommended) | Run GLiNER on both bio and pinned_tweet_text. Maximum signal but slower (2x the NER calls). | ✓ |
| Bio only | Run GLiNER on bio only. Faster, but pinned tweets can reveal interests/affiliations. | |
| Bio, fallback to pinned_tweet | Run on pinned_tweet_text only (if bio is empty/minimal). Skip if bio has enough text. | |

**User's choice:** Bio + pinned_tweet_text (Recommended)

---

## Entity Extraction: Minimum Text Length

| Option | Description | Selected |
|--------|-------------|----------|
| 10 characters (Recommended) | 10 characters is enough for meaningful entity extraction — filters truly empty bios but allows short ones. | |
| 20 characters | More conservative, ensures richer text before spending NER compute. | |
| No minimum | No minimum — run on all bios regardless of length. Wasteful but exhaustive. | ✓ |

**User's choice:** No minimum

---

## Google Search Trigger

| Option | Description | Selected |
|--------|-------------|----------|
| No bio + no website only (Recommended) | Only when account has no bio AND no website — the coldest accounts. Respects SerpApi free tier limits. | ✓ |
| No bio + no website + short bio (<20) | Also when bio is under 20 characters — slightly more accounts get Google context but uses more API calls. | |
| Never (skip entirely) | Never use Google search — accounts with no bio just don't get external context. Saves API costs. | |

**User's choice:** No bio + no website only (Recommended)

---

## Google Search: Data Extracted

| Option | Description | Selected |
|--------|-------------|----------|
| Title + snippet only (Recommended) | Extract page title and snippet from the first result as external context. Minimum storage, maximum signal. | ✓ |
| Full result data | Store full result URL, title, and snippet. More data for debugging but not needed for clustering. | |

**User's choice:** Title + snippet only (Recommended)

---

## Link Following Depth

| Option | Description | Selected |
|--------|-------------|----------|
| Homepage + timeout only (Recommended) | Follow website URL, parse for about/biography page, extract full bio. 10s timeout per site, max 30s per account. | |
| Homepage + about links | Additionally follow any 'about' or 'bio' links found on the homepage. Deeper but slower. | ✓ |
| Never follow external links | Never follow external links from profile websites — privacy/IP concerns. Skip entirely. | |

**User's choice:** Homepage + about links

---

## LinkedIn Links

| Option | Description | Selected |
|--------|-------------|----------|
| Skip LinkedIn links (Recommended) | LinkedIn scraping violates their ToS and LinkedIn has aggressive anti-bot detection. Skip LinkedIn links. | ✓ |
| Follow LinkedIn too | Follow LinkedIn profile links found on personal websites if no other bio data is available. | |

**User's choice:** Skip LinkedIn links (Recommended)

---

## Embedding Integration: Entity Format

| Option | Description | Selected |
|--------|-------------|----------|
| Append as " \| Org: X \| Loc: Y \| Title: Z" (Recommended) | Keeps format consistent with Phase 4. | ✓ |
| Separate entity fields in cache, separate embedding string | Keep original fields separate, add entity fields with "entities_" prefix. Cleaner separation but different format. | |
| Replace bio with enriched version | Override bio with entity-enriched version: "[Org: X] [Loc: Y] [Title: Z] original bio". | |

**User's choice:** Append as " | Org: X | Loc: Y | Title: Z" (Recommended)

---

## External Bio Entity Extraction

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — extract entities from external_bio too (Recommended) | Also run entity extraction on external_bio from link following. Maximizes entity signal for sparse accounts. | ✓ |
| No — use external_bio text directly | External_bio is used as-is in embeddings without additional entity extraction. | |

**User's choice:** Yes — extract entities from external_bio too (Recommended)

---

## Execution Order

| Option | Description | Selected |
|--------|-------------|----------|
| Link → Entity → Google (Recommended) | 1. Link following → external_bio, 2. Entity extraction (on all text including external_bio), 3. Google search (coldest accounts). | ✓ |
| Entity → Link → Google | 1. Entity extraction (on bio + pinned_tweet), 2. Link following (if bio empty), 3. Google search (if still no bio). | |
| Parallel execution | All three run in parallel for applicable accounts. Fastest but most complex to orchestrate. | |

**User's choice:** Link → Entity → Google (Recommended)

---

## Claude's Discretion

- Exact GLiNER threshold for entity confidence (default 0.5 — planner can tune)
- How to merge entity results when both bio and pinned_tweet produce entities
- Whether to cache GLiNER model in memory across accounts (performance optimization)
- Exact CSS selectors for finding "about" links on arbitrary websites

## Deferred Ideas

None — discussion stayed within phase scope.