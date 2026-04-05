# Phase 2: API Enrichment - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-05
**Phase:** 02-api-enrichment
**Areas discussed:** Cache format, Error handling, Missing data strategy

---

## Cache Format

| Option | Description | Selected |
|--------|-------------|----------|
| One file per account (JSON Lines) | One JSON per account — easy to inspect, simple implementation | ✓ |
| SQLite database | Single DB — queryable, no file system overhead | |
| Single JSON file | Single large JSON — simplest but slower for large batches | |

**User's choice:** One file per account (JSON Lines)
**Notes:** JSON Lines format at `data/enrichment/{account_id}.json`

---

## Error Handling

| Option | Description | Selected |
|--------|-------------|----------|
| Collect and continue (Recommended) | Continue with partial results, report all failures at end. More robust for large batches. | ✓ |
| Fail fast | Stop immediately on first error — easier debugging, but loses all progress on failure | |

**User's choice:** Collect and continue (Recommended)
**Notes:** Also: track suspended accounts (error 63) and protected accounts (error 179) separately; rate limit errors trigger exponential backoff with jitter

---

## Missing Data Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Leave blank (Recommended) | Leave empty fields as empty string — scraping phase will fill in later if possible | |
| Flag for scraping | Raise error if bio or location is missing — ensures no scraping targets slip through | ✓ |

**User's choice:** Flag for scraping
**Notes:** Store `needs_scraping: true` in enrichment record if bio/location is empty

---

## Claude's Discretion

- API batch size (up to 100 per `GET /2/users` call) — use tweepy's default batching
- Rate limit header parsing (`x-rate-limit-remaining`, `x-rate-limit-reset`)
- Exact backoff timing (exponential with jitter — specific values TBD by planner)

## Deferred Ideas

None — discussion stayed within phase scope.
