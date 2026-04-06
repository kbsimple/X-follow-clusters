# X Following Organizer

## What This Is

A Python tool that reads the `following.js` file from an X data archive export, enriches each followed account with profile data from the X API and profile page scraping, clusters followers into semi-automated categorized lists, and creates those lists as native X API lists. The user reviews and approves clusters before they become lists, with an option to enable full automation after trust is established.

## Core Value

Transform a flat following list into organized, named X API lists that make it easy to reference and follow groups of similar people.

## Requirements

### Validated

- [x] Parse `following.js` from X data archive export — Phase 01
- [x] X API authentication setup — Phase 01
- [x] X API profile enrichment with caching, rate limiting, and error handling — Phase 02
- [x] Profile page scraping for supplemental fields (curl_cffi + BeautifulSoup) — Phase 03
- [x] Semi-automated clustering: interactive review CLI with approve/reject/rename/merge/split/defer actions — Phase 05
- [x] Enable full automation mode after user approves a few clustering rounds — Phase 05

### Active

- [ ] User-defined starter categories: Geographic (Bay Area, NYC, RI, etc.), Occupation (VC, Engineer, Financier), Political Action (campaigns, evangelism groups), Entertainment (sports, humor)
- [ ] Discover additional categories beyond the starter set
- [x] Create native X API lists for approved clusters (5–50 people per list) — Phase 06

### Out of Scope

- Real-time monitoring or notifications — one-time (or on-demand) run only
- Posting or interacting with lists — read/creation only
- Integrating with other social platforms — X only
- Creating lists directly in the X app — API-only list creation

## Context

- User follows hundreds of people on X
- [ ] API credentials obtained and configured (Phase 01 completed auth module)
- Input file is `data/following.js` from a personal X data archive (JSON wrapped in JS assignment)
- Lists should be 5–50 people each; multiple people can belong to multiple lists
- User wants to review cluster quality before lists are created
- Full automation is a goal after initial review rounds build confidence

## Constraints

- **Tech Stack**: Python
- **Output**: Native X API lists (intermediate files allowed, final output must be X API lists)
- **Data Collection**: Rich profile data via X API + profile page scraping (not just basic API fields)
- **API Credentials**: X API authentication not yet obtained — must be factored into implementation plan

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Semi-automated clustering | User wants review/approval before lists are created | — Validated (Phase 05) |
| Rich profile data (API + scraping) | Maximize information for accurate clustering | — Pending |
| X API lists as final output | User wants native X app lists, not a separate tool | — Validated (Phase 06) |
| Python | User-specified tech stack | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-06 after Phase 06*
