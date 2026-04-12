---
phase: 08-3scrape
plan: 02
subsystem: scrape
tags: [link-follower, external-bio, web-scraping]
dependency_graph:
  requires: []
  provides:
    - src/scrape/link_follower.py: LinkFollowResult, follow_account_links
  affects:
    - data/enrichment/{account_id}.json: adds external_bio field
tech_stack:
  added: []
  patterns:
    - curl_cffi Session with browser impersonation for external HTTP
    - BeautifulSoup link extraction with keyword matching
    - Time-budget enforcement per account (30s max, 10s per request)
    - Content truncation at 2000 chars
key_files:
  created:
    - src/scrape/link_follower.py: LinkFollowResult dataclass, follow_account_links(), _find_bio_links(), _fetch_page_text()
  modified: []
decisions:
  - "Skips LinkedIn links explicitly per D-13"
  - "Triggers only when website exists AND bio < 10 chars per D-10"
  - "Fetches homepage first, then parses and follows up to 3 about/bio links per D-11"
metrics:
  duration: null
  completed: 2026-04-11
---

# Phase 08 Plan 02 Summary: Link Follower for External Bio Extraction

## One-liner

Link follower module that fetches homepage and about/bio pages from personal websites, skipping LinkedIn, with 10s per-request and 30s per-account timeouts.

## Completed Tasks

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| 1 | Create src/scrape/link_follower.py | 41909e7 | src/scrape/link_follower.py |

## Acceptance Criteria Status

- src/scrape/link_follower.py exists and contains follow_account_links() - **PASS**
- LinkFollowResult dataclass with username, external_bio, links_followed, pages_fetched fields - **PASS**
- LinkedIn URLs explicitly skipped (grep finds "linkedin.com" check) - **PASS**
- external_bio written to cache JSON file - **PASS**
- 10s per-request timeout enforced - **PASS**
- 30s max per-account timeout enforced - **PASS**
- Homepage and up to 3 about/bio links fetched - **PASS**
- Importable via `from src.scrape.link_follower import follow_account_links, LinkFollowResult` - **PASS**

## Deviations from Plan

None - plan executed exactly as written.

## Threat Flags

None.