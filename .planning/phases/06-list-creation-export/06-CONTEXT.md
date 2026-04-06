# Phase 6: List Creation + Export - Context

**Gathered:** 2026-04-06
**Status:** Ready for planning

<domain>
## Phase Boundary

Approved clusters from Phase 5 review flow are created as native X API lists. Also export follower records with cluster assignments to Parquet, and approved+deferred clusters to CSV. Reads from `data/clusters/approved.json` (approval registry) and `data/enrichment/*.json` (per-account cache). This is the final phase — once lists are created, the tool's core job is done.

</domain>

<decisions>
## Implementation Decisions

### Dry-Run Execution
- **D-01:** Dry-run first, then real execution
- **Dry-run output:** Show approved cluster names + member counts only (no API calls)
- **Rationale:** User wants to see what WOULD be created before touching live API. Simple names+counts is fast and informative without the complexity of mock API simulation.
- **Implementation:** CLI flag `--dry-run` (default True). Pass `--execute` to create lists for real.

### Conflict Handling
- **D-02:** HTTP 409 (list name conflict) → prompt user via CLI
- **Options presented:** "Rename list", "Skip this list", "Abort entirely"
- **Rationale:** X API list names must be unique per account. User should choose rather than the tool deciding silently.
- **Conflict detection:** Check if a list with the proposed name already exists via `GET /2/lists` before attempting creation.

### Data Export Scope
- **D-03:** Export both approved AND deferred clusters to CSV
- **Rationale:** Deferred clusters represent a decision the user made — worth preserving even if they won't get X API lists yet.
- **Parquet export:** All enriched accounts (regardless of cluster status) with full enrichment + cluster assignment fields
- **CSV export:** Per approved/deferred cluster — list name, member handles, cluster metadata

### API Credential Check
- **D-04:** Before any live API work, verify credentials are present and valid (re-use Phase 1 `verify_credentials()`)
- **Rationale:** No point attempting list creation without valid auth. Fail fast with clear message.

### Deferred Clusters
- **D-05:** Deferred clusters from Phase 5 get no X API list (by design — deferred means "not yet approved")
- **Deferred clusters are exported to CSV** per D-03, but no `POST /2/lists` for them

### Automation Mode
- **D-06:** Phase 6 reads `registry.automation_enabled` from `data/clusters/approved.json`
- **If automation_enabled=True:** Skip interactive prompts, create lists for all approved clusters without asking
- **If automation_enabled=False:** Present each list creation for confirmation before executing
- **Source:** `src/review/automation.is_automation_enabled()` — already implemented in Phase 5

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 5 Artifacts
- `src/review/registry.py` — `ApprovalRegistry` dataclass with `clusters["approved"]`, `clusters["deferred"]`, `automation_enabled`
- `src/review/automation.py` — `is_automation_enabled(reg)` — returns bool for Phase 6 to read
- `data/clusters/approved.json` — persistent approval registry schema
- `.planning/phases/05-review-flow/05-CONTEXT.md` — Phase 5 decisions (merge/split, batch approve, automation threshold)

### X API List Endpoints (tweepy Client)
- `client.create_list()` → `POST /2/lists` — list_name, description, mode (public/private)
- `client.add_list_members()` → `POST /2/lists/{id}/members/add_all` — up to 100 per request
- `client.get_owned_lists()` → `GET /2/users/me/lists` — for 409 conflict pre-check
- tweepy docs: https://docs.tweepy.org/en/stable/client.html

### Enrichment Cache Schema
- `data/enrichment/{account_id}.json` — Fields: username, description, cluster_id, cluster_name, silhouette_score, is_seed_category, central_member_usernames, plus all ENRICH and SCRAPE fields

### Requirements
- `.planning/REQUIREMENTS.md` — LIST-01 through LIST-05, EXPORT-01, EXPORT-02

### Phase 6 ROADMAP Success Criteria
- Native X API lists created for all approved clusters (5-50 members)
- HTTP 409 naming conflicts handled gracefully via user prompt
- Members bulk-added via `POST /2/lists/{id}/members/add_all` (up to 100/request)
- X limits validated: 5,000 members/list, 1,000 lists/account; test call before full execution
- Follower records exported to Parquet with enrichment + cluster data
- Approved clusters exported to CSV with list name, handles, metadata

</canonical_refs>

<codebase_context>
## Existing Code Insights

### Reusable Assets
- `get_auth()` from `src/auth/x_auth.py` — loads credentials from env vars
- `verify_credentials(auth)` from `src/auth/x_auth.py` — calls `GET /2/users/me` to validate; raises `AuthError` with HTTP status
- `ApprovalRegistry` from `src/review/registry.py` — already knows approved/deferred cluster structure
- `is_automation_enabled()` from `src/review/automation.py` — Phase 6 just calls this
- `load_registry()` from `src/review/registry.py` — returns `ApprovalRegistry` with `clusters["approved"]` and `clusters["deferred"]`

### Established Patterns
- tweepy Client for all X API calls (already used in Phase 1-2)
- AuthError with HTTP status + response body for API error debugging
- Immediate disk caching after each operation
- argparse CLI with `--dry-run` flag pattern

### Integration Points
- Input: `data/clusters/approved.json` (Phase 5 output), `data/enrichment/*.json` (Phase 4 output)
- Output: X API lists (live), `data/export/clusters.csv`, `data/export/followers.parquet`
- Automation: reads `registry.automation_enabled` flag set in Phase 5

</codebase_context>

<specifics>
## Specific Ideas

- List mode: private by default (per X API default)
- Cluster name → list name directly (no transformation)
- Cluster description → list description (if available in registry entry)
- Bulk add in batches of 100 (X API limit)
- Export paths: `data/export/followers.parquet`, `data/export/clusters.csv`
- If no enrichment data exists yet: exit gracefully with "Run Phase 4 first" message

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 06-list-creation-export*
*Context gathered: 2026-04-06*
