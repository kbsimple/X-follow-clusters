# Phase 2: API Enrichment - Context

**Gathered:** 2026-04-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Enrich 867 followed accounts with rich profile data from the X API. Extract bio, location, professional_category, pinned tweet text, follower/following counts, and verified status. Cache responses immediately. Flag accounts with missing bio/location for the scraping phase (Phase 3).

</domain>

<decisions>
## Implementation Decisions

### Cache Format
- **D-01:** JSON Lines format (one `.jsonl` file per account) — `data/enrichment/{account_id}.json`
- **Rationale:** Easy to inspect individual records, simple implementation, no database overhead

### Error Handling
- **D-02:** Collect failures and continue — robust for large batches
- **D-03:** Track suspended accounts (error 63) and protected accounts (error 179) separately
- **D-04:** Rate limit errors trigger exponential backoff with jitter; continue when limit resets
- **Rationale:** 867 accounts is a large batch; losing all progress on first error is unacceptable

### Missing Data Strategy
- **D-05:** Flag accounts with missing bio or location for Phase 3 scraping
- **Implementation:** Store `needs_scraping: true` in enrichment record if bio/location is empty
- **Rationale:** Ensures no scraping targets slip through unnoticed

### Claude's Discretion
- API batch size (up to 100 per `GET /2/users` call) — use tweepy's default batching
- Rate limit header parsing (`x-rate-limit-remaining`, `x-rate-limit-reset`)
- Exact backoff timing (exponential with jitter — specific values TBD by planner)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 1 Artifacts
- `src/auth/x_auth.py` — XAuth dataclass, get_auth(), verify_credentials(), AuthError
- `src/parse/following_parser.py` — parse_following_js(), FollowingRecord (account_id, user_link)
- `.env.example` — All 5 credential env vars documented
- `docs/auth-alternatives.md` — X API alternatives comparison

### Requirements
- `.planning/REQUIREMENTS.md` — ENRICH-01 through ENRICH-05, AUTH-01 through AUTH-03

</canonical_refs>

<codebase_context>
## Existing Code Insights

### Reusable Assets
- `src/auth/x_auth.py`: XAuth dataclass, get_auth(), verify_credentials() — use as-is for API calls
- `src/parse/following_parser.py`: parse_following_js() returns FollowingRecord list — 867 records ready

### Established Patterns
- tweepy Client already configured for OAuth 1.0a in Phase 1
- AuthError includes HTTP status and response body for debugging
- Credential loading via environment variables (get_auth() reads all 5 vars)

### Integration Points
- Input: `parse_following_js("data/following.js")` → list of FollowingRecord
- Output: `data/enrichment/{account_id}.json` files (JSON Lines, one per account)
- Next phase: Phase 3 reads enrichment data to know which accounts need scraping

</codebase_context>

<specifics>
## Specific Ideas

- 867 accounts to enrich (from `data/following.js`)
- Credentials must be configured before this phase can run (user hasn't obtained them yet)
- Enrichment data feeds into Phase 3 (scraping) and Phase 4 (clustering)

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 02-api-enrichment*
*Context gathered: 2026-04-05*
