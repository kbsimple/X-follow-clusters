# ROADMAP: X Following Organizer

**Project:** X Following Organizer
**Granularity:** Coarse (3-5 phases, 1-3 plans each)
**YOLO Mode:** Enabled

---

## Milestones

- ✅ **v1.0 MVP** — Phases 1-6 (shipped 2026-04-06) — [v1.0-ROADMAP.md](./milestones/v1.0-ROADMAP.md)
- 🚧 **v1.1** — Next milestone — Phase 7 (planning complete, execution pending)

---

## Phases

### Phase 7: Upgrade OAuth 1.0a to OAuth 2.0 PKCE

**Goal:** Upgrade X API authentication from OAuth 1.0a to OAuth 2.0 PKCE for refresh token support, higher rate limits, and improved security.
**Requirements:** OAuth 2.0 PKCE flow completes, all API calls work, tests pass
**Depends on:** None
**Plans:** 6 plans

Plans:
- [ ] 07-01-PLAN.md — XAuth dataclass and env var update
- [ ] 07-02-PLAN.md — First-run OAuth 2.0 PKCE flow (OAuth2UserHandler, callback server, token persistence)
- [ ] 07-03-PLAN.md — Update verify_credentials() for OAuth 2.0 Bearer token
- [ ] 07-04-PLAN.md — Update api_client.py XEnrichmentClient for OAuth 2.0
- [ ] 07-05-PLAN.md — Update tests for OAuth 2.0
- [ ] 07-06-PLAN.md — Update README.md and documentation

### Phase 8: 3scrape

**Goal:** Scrape Enhancement — post-analysis, Google search, and link extraction. Add three post-processing capabilities on top of Phase 3 scraping: (1) Entity extraction via GLiNER, (2) Google search fallback via SerpApi, (3) Link extraction and following for accounts with websites but no bios.
**Requirements**: TBD
**Depends on:** Phase 7
**Plans:** 6 plans

Plans:
- [ ] 08-01-PLAN.md — Install GLiNER dependency, create entity extraction module (src/scrape/entities.py)
- [ ] 08-02-PLAN.md — Create link follower module (src/scrape/link_follower.py)
- [ ] 08-03-PLAN.md — Create Google search lookup module (src/scrape/google_lookup.py)
- [ ] 08-04-PLAN.md — Update scrape_all() orchestrator with Link → Entity → Google pipeline
- [ ] 08-05-PLAN.md — Update get_text_for_embedding() to include entity fields
- [ ] 08-06-PLAN.md — Create tests (tests/test_3scrape.py), update CLI

---

*Last updated: 2026-04-11 — Phase 8 plans created (6 plans in 3 waves)*