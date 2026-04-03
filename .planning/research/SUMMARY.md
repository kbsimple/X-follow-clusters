# Research Summary: X Following Organizer

**Project:** X Following Organizer
**Synthesized:** 2026-04-02
**Confidence:** MEDIUM-HIGH (X API specifics high confidence; clustering approaches medium)

---

## Key Findings

### Stack (Recommended Python Libraries)

| Layer | Library | Why |
|-------|---------|-----|
| HTTP Client | `httpx >= 0.28.0` + `curl_cffi >= 0.7.0` | HTTP/2, async, TLS impersonation (critical for X) |
| HTML Scraping | `BeautifulSoup4 >= 4.12.0` + `playwright >= 1.50.0` | Static content vs JS-rendered pages |
| X API | `tweepy >= 4.14.0` | Official client, handles rate limiting correctly |
| Embeddings | `sentence-transformers >= 3.0.0` | Bio text → vectors for clustering |
| Clustering | `scikit-learn >= 1.5.0` + `HDBSCAN >= 0.8.0` | K-Means, DBSCAN on embeddings |
| Data | `pandas >= 2.2.0` | DataFrames for follower records |

**API Cost Warning:** X Basic tier ($100/month) is required for meaningful access. Free tier is nearly unusable (1,500 tweets/month).

### Table Stakes (MVP Must-Haves)

- Parse `follower.js` from X data archive (custom JS parser)
- Fetch full follower list beyond X's 500-cap UI limit
- Basic filtering (follower count, verified, activity)
- List creation + bulk add/remove via X API
- CSV/JSON export

### Differentiators (This Project's Focus)

- **Semi-automated NLP clustering** with review workflow — key differentiator
- Rich profile enrichment (API + profile page scraping)
- LLM-generated cluster names
- Seed categories (Geographic, Occupation, Political Action, Entertainment) to anchor clustering
- Full automation mode after trust is established

### Watch Out For

1. **Rate limits** — Batch API requests (up to 100 user IDs/call), track `x-rate-limit-*` headers, exponential backoff
2. **Scraping blocks** — X uses Cloudflare + TLS fingerprinting. Use `curl_cffi` for TLS impersonation, residential proxies, random delays
3. **Over-clustering** — Enforce min 5 people per cluster, max 50 (matches list limit)
4. **Suspended accounts** — Filter out error code 63; flag protected accounts separately
5. **robots.txt / ToS** — Scraping X profile pages has legal risk; scope it carefully

### X API Hard Limits

| Constraint | Value |
|------------|-------|
| Max members per list | 5,000 |
| Max per create_all request | 100 |
| Max lists per account | 1,000 |
| List ops rate limit | ~300 requests/15 min |

### Recommended Phase Order

1. **Archive Parsing** — Parse `follower.js`, validate structure
2. **API Integration** — Auth, rate-limit-aware enrichment, suspend/protected detection
3. **Scraping** (if needed beyond API) — Profile page enrichment with anti-detection
4. **Clustering** — Bio embeddings → clustering → LLM name generation
5. **Review Flow** — Semi-automated approval UI, batch actions
6. **List Creation** — X API list creation with conflict handling

### What NOT to Build

- Auto-follow on list add
- Scraping without TLS impersonation (will get blocked immediately)
- TF-IDF-only clustering (poor quality on short bios — use transformer embeddings)
- NLP/semantic clustering as v1 (keyword-based + review is tractable MVP)

---

## Files

| File | Status |
|------|--------|
| STACK.md | Agent ran inline — see agent output |
| FEATURES.md | Written |
| ARCHITECTURE.md | Agent ran inline — see agent output |
| PITFALLS.md | Written |
| SUMMARY.md | This file |

---

## Sources

- [X API Rate Limits (Official)](https://x-preview.mintlify.app/x-api/fundamentals/rate-limits)
- [X API Error Troubleshooting (Official)](https://developer.x.com/en/support/x-api/error-troubleshooting)
- [How to Scrape Twitter/X in 2026 (DEV Community)](https://dev.to/agenthustler/how-to-scrape-twitterx-in-2026-public-data-rate-limits-and-what-still-works-5bdg)
- [Web Scraping Anti-Detection 2026 (Apify)](https://use-apify.com/blog/web-scraping-anti-detection-2026)
- [Sentence Transformers Clustering](https://sbert.net/examples/sentence_transformer/applications/clustering/README.html)
- [twitter-archive-parser (GitHub)](https://github.com/timhutton/twitter-archive-parser)
