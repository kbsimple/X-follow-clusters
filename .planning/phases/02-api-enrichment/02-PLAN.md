---
phase: 02-api-enrichment
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/enrich/rate_limiter.py
  - src/enrich/api_client.py
  - src/enrich/enrich.py
  - src/enrich/__init__.py
autonomous: true
requirements:
  - ENRICH-01
  - ENRICH-02
  - ENRICH-03
  - ENRICH-04
  - ENRICH-05

must_haves:
  truths:
    - "867 accounts are enriched via batch API calls (up to 100 per call)"
    - "Rate limit headers are tracked; exponential backoff with jitter prevents 429 failures"
    - "Suspended (63) and protected (179) accounts are detected and flagged"
    - "All API responses are cached to disk immediately (one file per account)"
    - "Accounts missing bio/location are flagged with needs_scraping: true for Phase 3"
  artifacts:
    - path: "src/enrich/rate_limiter.py"
      provides: "Exponential backoff with jitter for rate limit handling"
      exports: ["ExponentialBackoff", "RateLimitError"]
    - path: "src/enrich/api_client.py"
      provides: "Tweepy client wrapper with rate limit tracking and immediate caching"
      exports: ["XEnrichmentClient", "CacheWriteError"]
    - path: "src/enrich/enrich.py"
      provides: "Main orchestration: batch enrichment, error tracking, needs_scraping flags"
      exports: ["enrich_all", "EnrichmentResult"]
    - path: "data/enrichment/"
      provides: "Directory for cached enrichment JSON files (one per account)"
    - path: "data/enrichment/suspended.json"
      provides: "List of suspended account IDs"
    - path: "data/enrichment/protected.json"
      provides: "List of protected account IDs"
  key_links:
    - from: "src/enrich/enrich.py"
      to: "src/auth/x_auth.py"
      via: "get_auth() returns XAuth, verify_credentials() called before batch"
      pattern: "from src.auth import get_auth, verify_credentials"
    - from: "src/enrich/enrich.py"
      to: "src/parse/following_parser.py"
      via: "parse_following_js() returns list of FollowingRecord"
      pattern: "parse_following_js"
    - from: "src/enrich/api_client.py"
      to: "data/enrichment/{account_id}.json"
      via: "write each response immediately after receiving it"
      pattern: "Path\\(cache_dir\\).*write_text"
---

<objective>
Build the complete X API profile enrichment system for 867 followed accounts.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/REQUIREMENTS.md (ENRICH-01 through ENRICH-05)
@.planning/phases/02-api-enrichment/02-CONTEXT.md
@.planning/phases/02-api-enrichment/02-RESEARCH.md
@src/auth/x_auth.py (XAuth, get_auth, verify_credentials, AuthError)
@src/parse/following_parser.py (parse_following_js, FollowingRecord)

# Key interfaces from existing code

From src/auth/x_auth.py:
```python
@dataclass
class XAuth:
    api_key: str
    api_secret: str
    access_token: str
    access_token_secret: str
    bearer_token: str | None = None

def get_auth() -> XAuth: ...
def verify_credentials(auth: XAuth) -> dict[str, Any]: ...
class AuthError(Exception): ...
```

From src/parse/following_parser.py:
```python
@dataclass
class FollowingRecord:
    account_id: str
    user_link: str
    raw_entry: dict

def parse_following_js(path: Union[str, Path]) -> list[FollowingRecord]: ...
```
</context>

<tasks>

<task type="auto">
  <name>Task 1: Build rate_limiter.py with exponential backoff and jitter</name>
  <files>src/enrich/rate_limiter.py</files>
  <action>
    Create src/enrich/rate_limiter.py implementing custom rate limit handling.

    Requirements from ENRICH-02 and D-04:
    - Track x-rate-limit-remaining and x-rate-limit-reset headers from API responses
    - Implement exponential backoff with jitter (not tweepy's simple sleep-until-reset)
    - Base delay: 1 second, max delay: 300 seconds
    - Jitter: random.uniform(0, 1) added to each backoff calculation
    - Formula: delay = min(base * (2 ** attempt) + random.uniform(0, 1), max_delay)
    - raise RateLimitError when rate limit is hit, containing reset timestamp and retry-after

    Implementation:
    ```python
    class RateLimitError(Exception):
        reset_timestamp: int  # Unix timestamp when limit resets
        retry_after: float    # seconds to wait
        remaining: int       # calls remaining at time of error
    ```

    Export: ExponentialBackoff class, RateLimitError exception
    Do NOT import tweepy here - this is pure timing logic, no API calls.
  </action>
  <verify>
    <automated>python -c "from src.enrich.rate_limiter import ExponentialBackoff, RateLimitError; b = ExponentialBackoff(); print('ok')"</automated>
  </verify>
  <done>Exponential backoff with jitter implemented, tested with sample delays</done>
</task>

<task type="auto">
  <name>Task 2: Build api_client.py - tweepy wrapper with rate tracking and immediate caching</name>
  <files>src/enrich/api_client.py</files>
  <action>
    Create src/enrich/api_client.py wrapping tweepy.Client with:

    1. Initialization:
       - Use return_type=requests.Response to access rate limit headers (per research finding)
       - Set wait_on_rate_limit=False (custom backoff instead)
       - Use user_auth=True for OAuth 1.0a (900 req/15min, not 300)
       - Pass all XAuth fields to tweepy.Client constructor

    2. User fields to request (ENRICH-04):
       - description (bio)
       - location
       - public_metrics (followers_count, following_count, tweet_count, listed_count)
       - verified
       - protected
       - pinned_tweet_id
       - Note: professional_category NOT available via API - omit, will come from Phase 3 scraping

    3. Cache immediately after each API call:
       - Write to data/enrichment/{account_id}.json
       - Format: pretty-printed JSON (indent=2)
       - Write each user's data immediately upon receiving it, before next user
       - On cache write failure, log warning but do NOT retry - continue with enrichment
       - Custom CacheWriteError exception class

    4. Rate limit tracking:
       - Parse x-rate-limit-remaining and x-rate-limit-reset from response headers
       - Before each batch, check if remaining calls < batch size; wait if needed
       - On 429, raise RateLimitError with reset timestamp for orchestrator to handle

    5. Error handling for suspended (63) and protected (179):
       - When return_type=dict: response has {"data": [...], "errors": [...]}
       - Iterate errors array; for each error with code 63 or 179, return in separate tracking dict
       - Do NOT raise exception for these - track and continue (per D-02 and D-03)

    Export: XEnrichmentClient class
    Dependencies: src/enrich/rate_limiter.py (ExponentialBackoff, RateLimitError)
  </action>
  <verify>
    <automated>python -c "from src.enrich.api_client import XEnrichmentClient; print('ok')"</automated>
  </verify>
  <done>Tweepy wrapper handles rate limits, caches immediately, parses error codes 63/179</done>
</task>

<task type="auto">
  <name>Task 3: Build enrich.py - main orchestration with batch processing</name>
  <files>src/enrich/enrich.py, src/enrich/__init__.py</files>
  <action>
    Create src/enrich/enrich.py as the main orchestration script.

    Flow:
    1. Load credentials via get_auth() from src.auth
    2. Verify credentials with verify_credentials() before batch operations (per AUTH-02)
    3. Parse following.js via parse_following_js from src.parse
    4. Create XEnrichmentClient with ExponentialBackoff rate limiter
    5. Process all accounts in batches of up to 100 (per ENRICH-01)
    6. For each enriched user: write to data/enrichment/{account_id}.json immediately
    7. Track suspended (code 63) and protected (code 179) in separate lists
    8. On rate limit (429): use ExponentialBackoff, retry the same batch after wait
    9. On other errors: log and continue (per D-02), collect in errors list

    needs_scraping flag (D-05):
    - After receiving user data, check if bio (description) or location is empty/missing
    - If either is missing, set needs_scraping: true in the cached JSON
    - This flags the account for Phase 3 scraping

    Output files:
    - data/enrichment/{account_id}.json (one per enriched account)
    - data/enrichment/suspended.json (list of suspended account IDs)
    - data/enrichment/protected.json (list of protected account IDs)
    - data/enrichment/errors.json (list of failed account IDs with error info)

    EnrichmentResult dataclass returned:
    - total: int
    - enriched: int
    - suspended: int
    - protected: int
    - errors: int
    - cache_dir: Path

    Create src/enrich/__init__.py exporting:
    - from .enrich import enrich_all, EnrichmentResult
    - from .api_client import XEnrichmentClient
    - from .rate_limiter import ExponentialBackoff, RateLimitError

    CLI: python -m src.enrich.enrich --input data/following.js --output data/enrichment
  </action>
  <verify>
    <automated>python -c "from src.enrich import enrich_all, EnrichmentResult; print('ok')"</automated>
  </verify>
  <done>867 accounts processed with all error handling, caching, and needs_scraping flags working</done>
</task>

</tasks>

<verification>
- [ ] Rate limiter correctly implements exponential backoff with jitter
- [ ] API client parses rate limit headers and raises RateLimitError on 429
- [ ] Each API response cached immediately to data/enrichment/{account_id}.json
- [ ] Error code 63 (suspended) and 179 (protected) detected and tracked
- [ ] accounts missing bio/location flagged with needs_scraping: true
- [ ] CLI runs without errors: python -m src.enrich.enrich
</verification>

<success_criteria>
All 5 ENRICH requirements satisfied:
- ENRICH-01: Batch API calls (up to 100 per call) implemented
- ENRICH-02: Rate limit headers tracked, exponential backoff with jitter implemented
- ENRICH-03: Suspended (63) and protected (179) accounts flagged
- ENRICH-04: bio, location, public_metrics, verified, protected, pinned_tweet_id extracted; professional_category omitted (not API-available, will come from Phase 3); pinned_tweet text deferred to scraping phase
- ENRICH-05: All responses cached immediately to data/enrichment/{account_id}.json
</success_criteria>

<output>
After completion, create .planning/phases/02-api-enrichment/02-01-SUMMARY.md
</output>