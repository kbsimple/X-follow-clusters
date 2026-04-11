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

---

*Last updated: 2026-04-11 — Phase 7 plans created (6 plans in 3 waves)*
