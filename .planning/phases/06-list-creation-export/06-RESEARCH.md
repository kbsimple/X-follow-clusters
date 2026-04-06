# Phase 6: List Creation + Export - Research

**Researched:** 2026-04-06
**Domain:** tweepy Client X API list creation + pandas/parquet data export
**Confidence:** HIGH

## Summary

Phase 6 creates native X API lists from Phase 5 approved clusters and exports follower data to Parquet and CSV. The tweepy 4.16.0 `Client` class provides `create_list()` and `add_list_members()` methods that map directly to X's `POST /2/lists` and `POST /2/lists/{id}/members/add_all` endpoints. The critical constraint is the 100-member-per-request limit on `add_all`, requiring chunked batch logic. Parquet export requires `pandas` and `pyarrow` which are not yet in the project's `pyproject.toml` dependencies and must be added. Conflict detection via `GET /2/users/me/lists` must run before creation to avoid HTTP 409. The existing `ApprovalRegistry` from Phase 5 provides all needed state including the `automation_enabled` flag that controls whether Phase 6 runs interactively or fully automated.

**Primary recommendation:** Use tweepy Client for list operations, add `pandas`+`pyarrow` to dependencies, pre-check owned lists before creation, chunk member adds in batches of 100.

## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Dry-run first, then real execution. CLI flag `--dry-run` (default True), pass `--execute` to create lists for real. Dry-run output shows approved cluster names + member counts only (no API calls).
- **D-02:** HTTP 409 (list name conflict) triggers CLI prompt with options: "Rename list", "Skip this list", "Abort entirely". Pre-check via `GET /2/users/me/lists` before attempting creation.
- **D-03:** Export both approved AND deferred clusters to CSV. Parquet exports all enriched accounts (regardless of cluster status) with full enrichment + cluster assignment fields. CSV exports per approved/deferred cluster with list name, member handles, metadata.
- **D-04:** Before any live API work, verify credentials via `verify_credentials()` from Phase 1.
- **D-05:** Deferred clusters from Phase 5 get no X API list. Deferred clusters are exported to CSV per D-03, but no `POST /2/lists` for them.
- **D-06:** Phase 6 reads `registry.automation_enabled` from `data/clusters/approved.json`. If True: skip interactive prompts, create lists for all approved clusters. If False: present each list creation for confirmation before executing. Use `is_automation_enabled(reg)` from `src/review/automation.py`.

### Specifics

- List mode: private by default (per X API default)
- Cluster name to list name directly (no transformation)
- Cluster description to list description (if available in registry entry)
- Bulk add in batches of 100 (X API limit)
- Export paths: `data/export/followers.parquet`, `data/export/clusters.csv`
- If no enrichment data exists yet: exit gracefully with "Run Phase 4 first" message

### Deferred Ideas (OUT OF SCOPE)

None.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| LIST-01 | Create native X API lists for approved clusters (5-50 people per list) | tweepy `client.create_list()` maps to `POST /2/lists`. Cluster name directly as list name. Private by default. |
| LIST-02 | Use `POST /2/lists` for list creation; handle naming conflicts (HTTP 409) gracefully | 409 pre-check via `get_owned_lists()` (`GET /2/users/me/lists`). CLI prompt with 3 options per D-02. |
| LIST-03 | Bulk add members via `POST /2/lists/{id}/members/add_all` (up to 100 per request) | tweepy `client.add_list_members()` wraps `add_all`. Must chunk members into batches of 100. Loop over chunks. |
| LIST-04 | Validate list sizes against X's 5,000 member cap and 1,000 lists/account limit | Pre-check: count owned lists via `get_owned_lists()`, validate each approved cluster size (already constrained to 5-50 by Phase 4). |
| LIST-05 | Verify list creation is possible with a test call before full run | Per D-04: `verify_credentials()` already done. Additionally, check rate limit remaining before bulk operations. |
| EXPORT-01 | Export follower records with enrichment data and cluster assignments to Parquet | `pandas.DataFrame` with schema from `data/enrichment/*.json`. Requires adding `pandas`+`pyarrow` to dependencies. |
| EXPORT-02 | Export final approved clusters to CSV with list name, member handles, and cluster metadata | One CSV row per approved/deferred cluster (per D-03). Uses `pandas.DataFrame.to_csv()`. |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| tweepy | 4.16.0 | X API client for list creation | Already used in Phase 1-2; `create_list()`, `add_list_members()`, `get_owned_lists()` map to X API endpoints |
| pandas | NOT INSTALLED | DataFrame for export | Standard Python data export; `to_parquet()`, `to_csv()` |
| pyarrow | NOT INSTALLED | Parquet format support | Required by `pandas.DataFrame.to_parquet()` |
| questionary | 2.1.1 | Interactive CLI prompts | Already used in Phase 5 review CLI |
| rich | (already used) | Console output | Already used in Phase 5 CLI |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `src/review/registry.py` | (existing) | `ApprovalRegistry`, `load_registry()`, `is_automation_enabled()` | Read approved/deferred clusters and automation flag |
| `src/auth/x_auth.py` | (existing) | `get_auth()`, `verify_credentials()` | Load and validate X API credentials |
| `src/enrich/api_client.py` | (existing) | `XEnrichmentClient` | Reference for tweepy Client patterns with rate limit handling |

### Dependencies to Add

```toml
# pyproject.toml additions
[project.optional-dependencies]
export = [
    "pandas>=2.0.0",
    "pyarrow>=14.0.0",
]
# Or add to main dependencies:
pandas>=2.0.0,
pyarrow>=14.0.0,
```

**Installation:**
```bash
pip install pandas>=2.0.0 pyarrow>=14.0.0
```

## Architecture Patterns

### Recommended Project Structure

```
src/
├── list/
│   ├── __init__.py
│   ├── creator.py      # create_lists_from_clusters(), chunked add_list_members()
│   ├── exporter.py     # export_to_parquet(), export_clusters_to_csv()
│   ├── cli.py          # Phase 6 entry point: python -m src.list.cli
│   └── dry_run.py      # Dry-run output logic
src/review/
├── registry.py         # (existing) ApprovalRegistry, load_registry()
├── automation.py       # (existing) is_automation_enabled()
```

### Pattern 1: tweepy Client List Creation

**What:** Create a list and add members using tweepy Client methods.
**When to use:** For each approved cluster in Phase 6.
**Example:**
```python
# Source: tweepy 4.16.0 client documentation
import tweepy

client = tweepy.Client(
    consumer_key=auth.api_key,
    consumer_secret=auth.api_secret,
    access_token=auth.access_token,
    access_token_secret=auth.access_token_secret,
)

# Create list (private by default)
lst = client.create_list(
    name=cluster_name,
    description=cluster_description,
    mode="private",  # default; explicitly set per D-Specific
)

# Add members in chunks of 100
list_id = lst.data["id"]
usernames = [member["username"] for member in cluster_members]
for i in range(0, len(usernames), 100):
    chunk = usernames[i:i + 100]
    client.add_list_members(list_id=list_id, user_names=chunk)
```

### Pattern 2: Conflict Pre-Check (409 Avoidance)

**What:** Check owned lists before attempting creation to avoid HTTP 409.
**When to use:** Before `create_list()` for each cluster.
**Example:**
```python
# Source: Phase 6 context (D-02, D-04)
owned_lists = client.get_owned_lists()
existing_names = {lst.name for lst in owned_lists.data}

for cluster in approved_clusters:
    if cluster["cluster_name"] in existing_names:
        # Trigger CLI prompt: rename / skip / abort
        handle_conflict(cluster)
    else:
        create_list(cluster)
```

### Pattern 3: Parquet Export Schema

**What:** Flat DataFrame with one row per enriched account.
**When to use:** For EXPORT-01.
**Example:**
```python
# Source: enrichment cache schema from context (canonical_refs)
# data/enrichment/{account_id}.json fields:
# username, description, cluster_id, cluster_name, silhouette_score,
# is_seed_category, central_member_usernames,
# plus all ENRICH and SCRAPE fields from API response

rows = []
for fpath in Path("data/enrichment").glob("*.json"):
    if fpath.stem in ("suspended", "protected", "errors"):
        continue
    with open(fpath) as f:
        data = json.load(f)
    rows.append(data)

df = pd.DataFrame(rows)
df.to_parquet("data/export/followers.parquet", index=False)
```

### Pattern 4: CSV Cluster Export

**What:** One row per approved/deferred cluster with nested member list.
**When to use:** For EXPORT-02.
**Example:**
```python
# Source: Phase 6 context (D-03)
rows = []
for cluster in approved + deferred:
    rows.append({
        "cluster_id": cluster["cluster_id"],
        "cluster_name": cluster["cluster_name"],
        "status": "approved" if in_approved else "deferred",
        "size": cluster["size"],
        "silhouette": cluster.get("silhouette", ""),
        "member_handles": ",".join(cluster["member_usernames"]),
    })
df = pd.DataFrame(rows)
df.to_csv("data/export/clusters.csv", index=False)
```

### Pattern 5: Dry-Run CLI Pattern

**What:** `--dry-run` (default True) prints planned actions without API calls. `--execute` runs for real.
**When to use:** Phase 6 CLI entry point.
**Example:**
```python
# Source: Phase 6 context (D-01), matching Phase 1-5 argparse pattern
parser = argparse.ArgumentParser(description="Create X API lists from approved clusters")
parser.add_argument("--dry-run", action="store_true", default=True,
                    help="Show what would be created without making API calls")
parser.add_argument("--execute", action="store_true",
                    help="Execute list creation (default is dry-run)")
```

### Pattern 6: Automation-Mode Skip

**What:** Read `registry.automation_enabled` to skip interactive confirmation.
**When to use:** At start of Phase 6 execution.
**Example:**
```python
# Source: Phase 6 context (D-06), existing is_automation_enabled()
from src.review.registry import load_registry
from src.review.automation import is_automation_enabled

reg = load_registry()
if is_automation_enabled(reg):
    # Skip confirmation, create all approved lists
    create_all_lists(approved_clusters)
else:
    # Confirm each list creation interactively
    for cluster in approved_clusters:
        if confirm(f"Create list '{cluster['name']}'?"):
            create_list(cluster)
```

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| X API list creation | Custom HTTP requests | tweepy Client `create_list()` | Handles auth, serialization, error parsing |
| Bulk member adds | Loop with individual `add_list_member()` | `client.add_list_members()` with `user_names` param (add_all) | 100/request batch is the API limit; single call is more efficient |
| Parquet serialization | Manual byte writing | `pandas.DataFrame.to_parquet()` with pyarrow | Handles schema, compression, column types |
| Rate limit backoff | Simple sleep | Reuse `ExponentialBackoff` from Phase 2 | Already implemented with jitter and cap |
| Conflict detection | Catch 409 after the fact | Pre-check via `get_owned_lists()` before creating | Cleaner UX, avoids wasted API call |

## Common Pitfalls

### Pitfall 1: `add_list_members()` Parameter Format

**What goes wrong:** Passing user IDs instead of usernames (or wrong format) silently fails or returns no members added.
**Why it happens:** The X API `add_all` endpoint accepts `user_names` (usernames, not numeric IDs). tweepy's `add_list_members()` wraps `user_names` parameter. Passing `user_id` or numeric IDs will fail.
**How to avoid:** Use `user_names=list_of_username_strings`. For the enrichment cache, `username` field is already available from the cached JSON files.
**Warning signs:** List created with 0 members, no error raised.

### Pitfall 2: Rate Limit on List Operations

**What goes wrong:** List operations have their own rate limits (distinct from user lookup limits). Running list creation for many clusters without backoff hits 429.
**Why it happens:** X API rate limits vary by endpoint. `POST /2/lists` and `add_all` have separate limits from `GET /2/users`.
**How to avoid:** Add small delay between list creations (e.g., `time.sleep(0.5)`) and check `x-rate-limit-remaining` headers if available. Use `ExponentialBackoff` for retries.
**Warning signs:** HTTP 429 on list creation that succeeds on retry.

### Pitfall 3: Orphaned Partial State on Conflict

**What goes wrong:** If a cluster creates 3 lists successfully, then the 4th hits a 409 conflict, partial state exists and the user must decide what to do about the already-created lists.
**Why it happens:** HTTP 409 is non-transactional across multiple API calls.
**How to avoid:** Pre-check ALL cluster names against owned lists before ANY creation. Report all conflicts upfront before making any API calls. Offer "Abort entirely" option per D-02.
**Warning signs:** User reports lists with duplicate names appearing in their X account.

### Pitfall 4: Missing Pandas/Pyarrow at Runtime

**What goes wrong:** Phase 6 plan includes export functionality but `pandas` and `pyarrow` are not in `pyproject.toml` or the .venv.
**Why it happens:** Export was not part of earlier phases, so these packages were never added.
**How to avoid:** Add `pandas>=2.0.0` and `pyarrow>=14.0.0` to `pyproject.toml` dependencies before Phase 6 implementation. Include install step in plan.
**Warning signs:** `ModuleNotFoundError: No module named 'pandas'` when running Phase 6.

### Pitfall 5: Empty Enrichment Cache

**What goes wrong:** Phase 6 tries to export but `data/enrichment/*.json` is empty (Phase 4 was never run).
**Why it happens:** Phase 6 reads from enrichment cache that may not exist yet.
**How to avoid:** Check at start: if no enrichment files exist, exit with message "Run Phase 4 clustering first."
**Warning signs:** Empty DataFrame exported, no CSV rows written.

## Code Examples

Verified patterns from existing codebase:

### Existing tweepy Client Pattern (from src/enrich/api_client.py)

```python
# tweepy Client initialization (used throughout project)
self._client = tweepy.Client(
    consumer_key=auth.api_key,
    consumer_secret=auth.api_secret,
    access_token=auth.access_token,
    access_token_secret=auth.access_token_secret,
    bearer_token=auth.bearer_token,
    wait_on_rate_limit=False,  # we handle 429 ourselves
    return_type=requests.Response,  # for header access
)
```

### AuthError Pattern (from src/auth/x_auth.py)

```python
class AuthError(Exception):
    def __init__(self, message: str, status_code: int | None = None, response_body: str | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.response_body = response_body
```

### ApprovalRegistry Usage (from Phase 6 context)

```python
# Read existing registry (existing pattern from Phase 5)
from src.review.registry import load_registry, save_registry, ApprovalRegistry
from src.review.automation import is_automation_enabled

reg = load_registry()
approved = reg.clusters["approved"]    # list of {cluster_id, cluster_name, size, members, ...}
deferred = reg.clusters["deferred"]   # list of {cluster_id, cluster_name, size, members}
automation_enabled = is_automation_enabled(reg)
```

### Loading Enrichment Cache (from src/review/cli.py)

```python
def json_load(path: Path) -> dict:
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return __import__("json").load(open(path, encoding=enc))
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Could not decode {path}")

# Pattern used in review/cli.py for iterating enrichment files:
for fpath in sorted(cache_dir.glob("*.json")):
    if fpath.stem in ("suspended", "protected", "errors"):
        continue
    d = json_load(fpath)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| tweepy `API` class (v3.x) | tweepy `Client` class (v4.x) | Phase 1 | Client is async-capable and has cleaner list method naming |
| Individual `add_list_member()` in a loop | `add_list_members()` with `user_names` batch | Phase 6 | Up to 100x fewer API calls per list |

**Deprecated/outdated:**
- tweepy `API.create_list()` (v3.x): Replaced by `Client.create_list()` with different parameter names
- `Client.add_member()` (single): Replaced by batch `add_list_members()` for efficiency

## Open Questions

1. **Parquet dependency without explicit install step**
   - What we know: `pandas` and `pyarrow` are not in `pyproject.toml`. Phase 6 plan must include an install step.
   - What's unclear: Whether the project prefers a single `pip install -e ".[export]"` optional dependency or direct inclusion in main dependencies.
   - Recommendation: Add to main dependencies since export is a core Phase 6 deliverable. Use `pandas>=2.0.0` and `pyarrow>=14.0.0`.

2. **X API rate limits for list operations**
   - What we know: X does not publicly document exact rate limits for list creation endpoints. `add_all` has a documented 100/user/request limit.
   - What's unclear: Exact `POST /2/lists` rate limit (calls per 15min window).
   - Recommendation: Implement `time.sleep(0.5)` between list creations and ExponentialBackoff retry on 429. Don't attempt a pre-check test call beyond LIST-05 credential verification.

## Environment Availability

> Step 2.6: SKIPPED - No external dependencies beyond the project's own Python codebase.
> All requirements (tweepy, questionary, rich) are already installed in the .venv.
> pandas and pyarrow need to be added as documented in Common Pitfalls #4.

## Validation Architecture

> Validation Architecture is included since `workflow.nyquist_validation` key is absent (treat as enabled).

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (already in `pyproject.toml` dev dependencies) |
| Config file | `pytest.ini` or `pyproject.toml [tool.pytest]` (none yet - Wave 0) |
| Quick run command | `pytest tests/test_list_creator.py -x` |
| Full suite command | `pytest tests/ -x` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| LIST-01 | Create list from approved cluster via `create_list()` | unit | `pytest tests/test_list_creator.py::test_create_list_from_cluster -x` | No |
| LIST-02 | 409 conflict detected via `get_owned_lists()` pre-check | unit | `pytest tests/test_list_creator.py::test_conflict_detection -x` | No |
| LIST-03 | Members chunked into batches of 100 and added via `add_list_members()` | unit | `pytest tests/test_list_creator.py::test_chunked_member_add -x` | No |
| LIST-04 | Cluster sizes 5-50 validated; account list count checked | unit | `pytest tests/test_list_creator.py::test_list_size_validation -x` | No |
| LIST-05 | `verify_credentials()` called before any list creation | unit | `pytest tests/test_list_creator.py::test_credential_verification -x` | No |
| EXPORT-01 | Parquet export produces valid file with correct schema from enrichment cache | unit | `pytest tests/test_exporter.py::test_parquet_export_schema -x` | No |
| EXPORT-02 | CSV export produces one row per approved/deferred cluster | unit | `pytest tests/test_exporter.py::test_csv_export -x` | No |

### Sampling Rate

- **Per task commit:** `pytest tests/test_list_creator.py -x`
- **Per wave merge:** `pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_list_creator.py` — covers LIST-01 through LIST-05
- [ ] `tests/test_exporter.py` — covers EXPORT-01 and EXPORT-02
- [ ] `tests/conftest.py` — shared fixtures (auth mock, registry mock, temp enrichment cache)
- [ ] `pytest.ini` or `[tool.pytest]` config if needed
- [ ] Framework install: `pip install pytest pytest-asyncio` (already in pyproject.toml dev deps)
- [ ] Add to plan: Install pandas+pyarrow before implementation

## Sources

### Primary (HIGH confidence)

- tweepy 4.16.0 Client documentation — verified via installed package
- `src/auth/x_auth.py` — existing `AuthError`, `XAuth`, `get_auth()`, `verify_credentials()` patterns
- `src/review/registry.py` — existing `ApprovalRegistry`, `load_registry()` patterns
- `src/review/automation.py` — existing `is_automation_enabled()` for Phase 6 to call
- `src/enrich/api_client.py` — existing tweepy Client initialization pattern
- `src/review/cli.py` — enrichment cache file iteration pattern with `glob("*.json")`

### Secondary (MEDIUM confidence)

- X API `POST /2/lists` and `add_all` endpoint behavior — inferred from tweepy client method signatures and Phase 6 context (D-02, D-03, canonical refs)
- Parquet/pandas export schema — inferred from `data/enrichment/{account_id}.json` schema documented in Phase 6 context canonical refs

### Tertiary (LOW confidence)

- X API rate limit numbers for list creation endpoints — not verified with current official docs; implement retry with backoff as defensive measure

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — tweepy 4.16.0 confirmed installed; pandas+pyarrow need to be added but versions are well-established
- Architecture: HIGH — all patterns verified from existing codebase (registry, auth, enrichment cache iteration)
- Pitfalls: HIGH — all pitfalls identified from Phase 6 context decisions and existing codebase patterns

**Research date:** 2026-04-06
**Valid until:** 2026-05-06 (30 days — tweepy API is stable; pandas/pyarrow versions are well-established)
