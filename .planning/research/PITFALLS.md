# Domain Pitfalls: X Follower Organization Tool

**Domain:** X API + scraping + follower clustering
**Researched:** 2026-04-02
**Confidence:** MEDIUM (web search primary source; some X API specifics need validation)

---

## Critical Pitfalls

### 1. Rate Limit Exhaustion Without Recovery Strategy

**What goes wrong:** Tool hits HTTP 429 and either retries immediately (making it worse) or fails silently (producing incomplete output).

**Why it happens:** X API v2 enforces per-endpoint limits (e.g., `GET /2/users/:id` is 300/15min per user, 900/15min per app). The `follower.js` can contain hundreds or thousands of accounts. Naive enrichment makes one API call per follower and exhausts limits in minutes.

**Consequences:**
- Partial enrichment (many profiles missing data)
- 429s cascading through the session
- User cannot tell which accounts were enriched vs. skipped

**Prevention:**
- Batch requests: `GET /2/users` accepts up to 100 user IDs per call
- Track `x-rate-limit-remaining` and `x-rate-limit-reset` headers in every response
- Implement exponential backoff with jitter (cap at 60s, add random 0-1s jitter)
- Build a request queue that spaces calls across time windows (e.g., for 900/15min limit, max 1 req/sec)
- Cache all API responses to disk immediately -- never re-request within the session

**Detection:**
- Log `x-rate-limit-remaining` at 80% threshold
- Alert when 429 is encountered
- Verify output count matches expected count after enrichment

**Phase:** Phase 2 (API integration). Rate limit handling must be built before enrichment begins.

---

### 2. Authentication Failure Due to Token Misconfiguration

**What goes wrong:** HTTP 401 on every request despite credentials being "correct."

**Why it happens:**
- **Clock skew**: OAuth 1.0a signatures are timestamp-sensitive; system clock drift >5 minutes causes 401
- **Access token regeneration**: After changing app permissions (e.g., adding Read/Write), existing tokens are invalidated -- must regenerate
- **OAuth scope mismatch**: App has wrong scopes for the endpoints being called (e.g., Basic tier cannot access some endpoints)
- **Bearer token in wrong format**: Should be `Authorization: Bearer <token>`, not query param

**Consequences:**
- Complete inability to make API calls
- User blames "broken API integration" rather than config issue

**Prevention:**
- Sync system clock via NTP before first run
- Verify credentials with a lightweight endpoint (e.g., `GET /2/users/me`) before batching
- Document that changing app permissions in the X developer portal requires re-authenticating
- Use OAuth 2.0 Authorization Code with PKCE (current standard for X API v2)

**Detection:**
- Log full error response body on 401/403
- Check `x-rate-limit-reset` header even on auth failures (sometimes misleading)

**Phase:** Phase 2 (API integration). Auth verification should be the first test before any enrichment.

---

### 3. Getting IP-Blocked During Profile Scraping

**What goes wrong:** X's anti-bot system detects headless browser or requests library, blocks IP, returns 403 or CAPTCHA pages.

**Why it happens:**
- X uses Cloudflare Turnstile + behavioral fingerprinting
- Python `requests` has a distinct TLS (JA3) fingerprint recognized and blocked
- Datacenter IPs (AWS, DigitalOcean, etc.) are blocked within minutes of high-frequency requests
- Headless browsers without stealth plugins expose automation signals (missing navigator.plugins, automation flags)

**Consequences:**
- Profile page scraping fails entirely
- IP may be temporarily soft-blocked on the API too (shared IP detection)
- CAPTCHA interstitial appears instead of profile data

**Prevention:**
- Use residential or mobile proxies for scraping (Bright Data, Oxylabs, Apify proxy)
- Use `curl_cffi` or Playwright with stealth plugins to match browser TLS fingerprints
- Add random delays between requests (2-5s with jitter)
- Warm up sessions: browse a few unrelated pages first, maintain cookies
- Rotate User-Agent strings but stay within plausible Chrome/Firefox versions
- Consider managed scraping APIs (Apify, Bright Data) for X specifically -- they maintain browser fingerprints at scale

**Detection:**
- 403 responses on scraping but not on API calls
- CAPTCHA page title in response HTML
- `curl` works but programmatic requests fail (clear fingerprinting signal)

**Phase:** Phase 3 (Scraping). Anti-detection should be researched and tested before production scraping runs.

---

## Moderate Pitfalls

### 4. Suspended and Protected Accounts Breaking Clustering

**What goes wrong:** Cluster contains accounts that are suspended, deleted, or protected -- enriching them fails or returns garbage, clustering is degraded.

**Why it happens:**
- X API returns error code 63 ("User has been suspended") or 179 ("Protected tweets") for these accounts
- Scraping protected accounts returns redirect-to-login or empty profile
- Clustering includes placeholder/null data for these, corrupting similarity calculations

**Consequences:**
- Clusters include dead weight accounts
- Similarity scores are wrong (missing half the profile data)
- User creates X lists that contain suspended/empty profiles -- embarrassing and useless

**Prevention:**
- Filter out suspended accounts (error code 63) immediately after enrichment
- Flag protected accounts as "protected" in data model, exclude from bio-based clustering
- Store `suspended: true` / `protected: true` / `deleted: true` as explicit flags, not implicit nulls
- In clustering algorithm, handle missing fields gracefully (don't treat null bio as empty string -- these are semantically different)
- Allow user to exclude suspended accounts from list creation

**Detection:**
- Count of error 63 responses during enrichment
- Number of profiles where `public_metrics.followers_count` is 0 and bio is empty (likely suspended)

**Phase:** Phase 2 (API integration) and Phase 4 (Clustering). Data quality filtering must be in the enrichment pipeline.

---

### 5. Over-Clustering: 50 Micro-Categories Nobody Understands

**What goes wrong:** Clustering algorithm produces 40 clusters of 3-5 people each. User is overwhelmed trying to review and name them.

**Why it happens:**
- Algorithm optimizes for statistical separation, not human usability
- No minimum cluster size constraint
- Distance threshold too fine-grained
- Bio text clustering with TF-IDF on small vocabularies produces spurious similarity

**Consequences:**
- User abandons review process
- "Analysis paralysis" -- everything looks similar at small scale
- Tool feels less useful than a flat list

**Prevention:**
- Set minimum cluster size (e.g., 5 people minimum for a useful list)
- Merge clusters with same/similar names automatically
- Use hierarchical clustering that can be cut at different depths -- let user choose granularity
- Pre-define category seeds (from the PROJECT.md: Geographic, Occupation, Political Action, Entertainment) to anchor the clustering
- Present cluster size distribution before user review; warn if it's heavily skewed to small clusters

**Detection:**
- Report cluster size histogram during clustering
- Flag if >50% of clusters have fewer than 5 members

**Phase:** Phase 4 (Clustering). Cluster size constraints should be configurable parameters.

---

### 6. Under-Clustering: One Giant Cluster

**What goes wrong:** All 400 followed accounts end up in one cluster because the similarity threshold is too loose.

**Why it happens:**
- Default distance threshold too permissive
- Most followed accounts have generic bios ("tweets about tech"), making them seem similar
- Algorithm treats sparse data as high similarity (few distinguishing features = mathematically similar)

**Consequences:**
- Tool provides no organizational value
- User loses trust in clustering quality

**Prevention:**
- Use silhouette score or elbow method to find optimal cluster count
- Set a maximum cluster size (e.g., 50 -- matches list size limit from PROJECT.md)
- Treat bio keyword overlap carefully: a "VC" cluster and "engineer" cluster might both contain "tech" -- use more discriminative features
- Consider graph-based clustering (follower overlap) in addition to bio text similarity

**Detection:**
- If single cluster contains >80% of accounts, clustering failed
- Silhouette score below 0.3

**Phase:** Phase 4 (Clustering).

---

### 7. Bad Category Names: "Cluster 12" or Gibberish

**What goes wrong:** Algorithm names clusters based on dominant keywords that are weird ("seems", "just", "things") or generic ("people I follow").

**Why it happens:**
- Keyword extraction from short bios picks up stopwords and filler
- No constraint that names should be meaningful labels
- Auto-generated names aren't validated against whether a human would use them

**Consequences:**
- User doesn't trust the names
- Review flow slows down because user has to rename everything
- Some clusters look like spam

**Prevention:**
- Use LLM to generate cluster names from member profiles (e.g., "Bay Area fintech founders" not "sf finance bay")
- Filter extracted keywords through a semantic quality filter (discard single words, discard common stopwords, require noun phrases)
- Present 3-5 name options per cluster for user to pick/edit
- Allow manual rename as first-class operation during review
- Use category seeds from PROJECT.md to guide name generation ("This cluster is mostly NYC-based journalists covering tech")

**Detection:**
- Name plausibility check: if a name would appear in a normal conversation, it's good
- Flag clusters where top keyword appears in >50% of bios (likely a filler word)

**Phase:** Phase 4 (Clustering) and Phase 5 (Review flow).

---

### 8. robots.txt Violation During Scraping

**What goes wrong:** Scraping violates X's `robots.txt`, exposing the project to legal/technical risk.

**Why it happens:**
- X's `robots.txt` disallows most automated access to profile pages
- Scraping without checking or respecting `robots.txt` is both legally risky and triggers blocks
- Even with API access, profile page scraping for additional data may violate ToS

**Consequences:**
- Legal exposure (X has aggressively sued scrapers)
- IP blocked
- App suspended from X API

**Prevention:**
- Check X's `robots.txt` before scraping (`https://x.com/robots.txt`)
- Use X API for profile data instead of scraping wherever possible
- If scraping additional fields the API doesn't provide, consult legal review
- Document which data comes from API vs. scraping, and the legal basis for each

**Note:** This tool already plans to use API + scraping. The scraping portion needs careful scoping to avoid crossing legal lines.

**Phase:** Phase 1 (Scraping decision) and Phase 3 (Scraping implementation). Legal review of scraping scope should happen early.

---

## Minor Pitfalls

### 9. Data Archive Parsing Failures on Edge Cases

**What goes wrong:** `follower.js` parses correctly for most users but fails on edge cases: escaped characters, Unicode in names, accounts that were renamed or deleted since archive was created.

**Prevention:**
- Test with multiple real `follower.js` files from different accounts
- Wrap parsing in try/except per-entry; log failures, continue with valid entries
- Validate JSON structure before assuming fixed format

**Phase:** Phase 1 (Archive parsing).

---

### 10. List Creation Fails at X API Level

**What goes wrong:** All clustering is correct but `POST /2/lists` fails because user has hit list creation limits or the account doesn't have list creation enabled.

**Prevention:**
- Verify list creation is possible with a test call before the full run
- X has a limit on total lists per account (initially 1,000); warn if approaching
- Lists must have unique names; handle `409 Conflict` errors gracefully

**Phase:** Phase 5 (List creation).

---

### 11. Review Flow Overwhelms User with Unstructured Approvals

**What goes wrong:** Review screen shows 40 clusters with no grouping, sorting, or context. User approves/rejects randomly or abandons.

**Prevention:**
- Group clusters by suggested category type (Geography, Occupation, etc.)
- Sort by cluster size (largest first, easiest decisions first)
- Show member preview without expanding (e.g., "12 people: 3 VCs, 5 engineers, 4 journalists")
- Provide batch actions: "Approve all clusters with >5 members and confident names"
- Show confidence scores for cluster membership (member X is 90% confident in this cluster vs. 55%)
- Allow deferring a cluster ("not sure yet") without blocking others

**Phase:** Phase 5 (Review flow).

---

## Phase-Specific Warnings

| Phase | Most Likely Pitfall | Mitigation |
|-------|--------------------|------------|
| Phase 1: Archive Parsing | Edge case parsing failures | Test with real files; per-entry error handling |
| Phase 2: API Integration | Rate limit exhaustion + Auth failures | Batch requests; NTP sync; credential verification |
| Phase 3: Scraping | IP blocking | Residential proxies; stealth browser; consider managed service |
| Phase 4: Clustering | Over-clustering / under-clustering | Configurable min/max size; silhouette scoring; seed categories |
| Phase 5: Review Flow | Unstructured approval chaos | Grouped display; batch actions; confidence scores |
| Phase 6: List Creation | List limits / naming conflicts | Pre-check limits; handle 409 gracefully |

---

## Sources

- [Common Developer Mistakes with Twitter API Rate Limits (MoldStud, Feb 2025)](https://moldstud.com/articles/p-twitter-api-rate-limits-common-developer-mistakes) -- MEDIUM confidence
- [Twitter API Rate Limit Errors: Fix 401, 403, 429 & 503 Fast (Error Medic)](https://errormedic.com/api/twitter-api/twitter-api-rate-limit-errors-fix-401-403-429-503-fast) -- MEDIUM confidence
- [How to Scrape Twitter/X in 2026 (DEV Community, Mar 2026)](https://dev.to/agenthustler/how-to-scrape-twitterx-in-2026-public-data-rate-limits-and-what-still-works-5bdg) -- MEDIUM confidence
- [X API Rate Limits Documentation (Official)](https://x-preview.mintlify.app/x-api/fundamentals/rate-limits) -- HIGH confidence
- [How Anti-Bot Systems Detect Scrapers in 2026 (DEV Community)](https://dev.to/agenthustler/how-anti-bot-systems-detect-scrapers-in-2026-and-how-to-get-past-them-5fpp) -- MEDIUM confidence
- [Web Scraping Anti-Detection Techniques: The Definitive 2026 Reference (Apify)](https://use-apify.com/blog/web-scraping-anti-detection-2026) -- MEDIUM confidence
- [Downloading tweet data from a suspended account (X Dev community)](https://devcommunity.x.com/t/downloading-tweet-data-from-a-suspended-account/166817) -- HIGH confidence
- [Get protected tweets using API v2 (X Dev community)](https://devcommunity.x.com/t/get-protected-tweets-using-api-v2/226274) -- HIGH confidence
- [X API Response codes and errors (Official)](https://developer.x.com/en/support/x-api/error-troubleshooting) -- HIGH confidence
- [X API endpoint map (Official)](https://developer.x.com/en/docs/x-api/migrate/x-api-endpoint-map) -- HIGH confidence
- [X API v2 authentication mapping (Official)](https://docs.x.com/fundamentals/authentication/guides/v2-authentication-mapping) -- HIGH confidence
- [Semantic Clustering in Site Taxonomy Design (Everestranking)](https://everestranking.com/maximizing-user-experience-with-semantic-clustering-in-site-taxonomy-design/) -- LOW confidence (generic UX, not X-specific)
- [What is SimClusters on X (Watsspace)](https://watsspace.com/blog/what-is-simclusters-on-x-twitter/) -- MEDIUM confidence
