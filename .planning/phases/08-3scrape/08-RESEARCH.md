# Phase 8: 3scrape - Research

**Researched:** 2026-04-11
**Domain:** Profile scraping post-processing, external data enrichment, entity extraction
**Confidence:** MEDIUM-HIGH

## Summary

Phase 8 ("3scrape") enhances the existing Phase 3 scraping pipeline with three post-analysis capabilities that improve clustering quality for accounts with sparse or ambiguous bios. The three enhancements are:

1. **Entity extraction** (post-analysis): Extract structured entities (person names, organizations, locations, job titles) from bio text and pinned tweets using a zero-shot NER model (GLiNER). This enriches the text representation used for embeddings without requiring custom training.

2. **Google search fallback** (external lookup): When an account has no bio AND no website, query Google via SerpApi to find the account's public-facing profiles on other platforms (personal site, LinkedIn, Wikipedia) that reveal their identity and interests. This addresses the cold-start problem for high-value accounts with empty bios.

3. **Link extraction and following** (external data): Extract URLs from the `website` field and follow them to scrape additional context (about page, biography page). This supplements sparse bios for accounts that have a website but no textual bio.

**Primary recommendation:** Implement entity extraction first (highest impact, lowest cost). Use GLiNER (`urchade/gliner_base-v2.1`) for zero-shot NER on short bio text. Treat Google search as a gated fallback (only when bio is completely absent). Treat link following as an optional enhancement for accounts with websites but no bios.

**Phase 7 dependency:** Phase 7 (OAuth 2.0 PKCE) has no functional impact on Phase 8. The data pipeline (enrichment cache -> scraping -> clustering) is unchanged. Phase 8 runs as a post-processing step on the same cache files.

---

## User Constraints (from CONTEXT.md)

> No CONTEXT.md exists for Phase 8. The phase is newly added and has no prior locked decisions. Claude's discretion applies to all implementation decisions.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `gliner` | >=1.0.0 | Zero-shot NER for entity extraction from short bios | [ASSUMED] Lightweight (~110M params), CPU-friendly, state-of-the-art zero-shot on short text |
| `serpapi` | >=1.0.0 | Google search API for account lookup | [ASSUMED] Standard for programmatic Google search; 250 free searches/month |
| `lxml` | (already in deps) | HTML parsing for link extraction | Already in project dependencies |

### Supporting (existing)
| Library | Purpose | When to Use |
|---------|---------|-------------|
| `beautifulsoup4` | HTML parsing | Already in deps; used for link extraction |
| `curl_cffi` | HTTP with TLS impersonation | Already in deps; used for external link following |
| `requests` | HTTP client | Already in deps |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `gliner` | spaCy `en_core_web_trf` | spaCy requires ~750MB model, slower; GLiNER is purpose-built for short text zero-shot |
| `gliner` | `dslim/bert-base-NER` (HuggingFace) | Requires pipeline setup; GLiNER has better entity-type prompting for custom labels |
| `serpapi` | DIY Google scraping (requests + BeautifulSoup) | Google actively blocks automated queries with CAPTCHA; SerpApi handles this reliably |
| `serpapi` | DuckDuckGo API | Less comprehensive for X/Twitter account search; no dedicated Twitter results endpoint |

---

## Architecture Patterns

### Recommended Project Structure
```
src/
├── scrape/
│   ├── scraper.py        # Existing XProfileScraper (Phase 3)
│   ├── parser.py         # Existing parse_profile_fields (Phase 3)
│   ├── __init__.py       # Existing exports
│   ├── entities.py       # NEW: Entity extraction from bio/pinned_tweet_text (Phase 8)
│   ├── google_lookup.py # NEW: SerpApi-based Google search for accounts (Phase 8)
│   ├── link_follower.py  # NEW: External URL extraction and following (Phase 8)
│   └── __main__.py       # EXISTING: CLI entry point for scrape module
```

### Pattern 1: Post-Scraping Analysis Pipeline

**What:** After Phase 3 scraping enriches `data/enrichment/{username}.json`, Phase 8 entity extraction reads those files and adds structured entity fields.

**When to use:** Accounts with sparse bios (one-liners, single words) benefit most from entity extraction as it surfaces implicit identity signals (organization names, locations, job titles mentioned implicitly).

**Data flow:**
```
Phase 3 cache (bio, location, website, pinned_tweet_text)
    -> Phase 8 entity extraction (extracts orgs, locations, persons, job_titles)
    -> Enhanced cache fields (bio_entities, pinned_entities)
    -> Phase 4 embed_accounts() adds entity text to embedding string
    -> Clustering quality improves for sparse accounts
```

**Example enhanced embedding text:**
```
# Before (sparse):
"AI researcher" | ""

# After (entity-enriched):
"AI researcher | Org: DeepMind | Loc: London | Title: Research Scientist"
```

### Pattern 2: Gated Google Search Fallback

**What:** Only query Google when an account has neither bio nor website — the coldest accounts.

**When to use:** Accounts where clustering is weakest (no text signal at all from X profile).

**Trigger condition:**
```python
if not bio and not website:
    # Trigger Google search to find external profile context
    google_result = search_x_account(username)
```

**Example (SerpApi):**
```python
import serpapi

client = serpapi.Client(api_key=os.environ["SERPAPI_KEY"])
results = client.search({
    "engine": "google",
    "q": f'"{username}" site:x.com OR site:twitter.com',
})
# Extract snippet, profile link, etc.
```

### Pattern 3: Link Extraction and Following

**What:** For accounts with a `website` URL but no bio, fetch the website and scrape the about/biography page.

**When to use:** Accounts with `website` field set but `bio` empty or minimal. High-value accounts with personal websites often have full bios there.

**Process:**
1. Extract `website` from cached profile JSON
2. Fetch website homepage with curl_cffi (reuse existing TLS impersonation)
3. Parse for common biography patterns (about page, LinkedIn link, "about me" section)
4. Add `external_bio` field to cache

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Named entity recognition on short bio text | Train a custom NER model | `gliner` zero-shot | GLiNER Base v2.1 achieves SOTA on short text NER without training; training requires labeled data |
| Google search for X account context | DIY requests + BeautifulSoup Google scraping | `serpapi` | Google actively blocks automated queries; SerpApi handles CAPTCHAs, IP rotation, structured results |
| HTML link extraction from external websites | ad-hoc regex link matching | `beautifulsoup4` + `lxml` | Already in project deps; robust link extraction with `soup.find_all('a', href=True)` |
| Zero-shot entity typing for custom entity types | Fine-tune a base model | GLiNER entity prompt labels | GLiNER accepts label prompts at inference; no fine-tuning needed for ORG, PERSON, LOC, JOB_TITLE |

**Key insight:** Bio text is extremely short (typically 10-160 characters). Generic NER models trained on long-form news text perform poorly on tweets/bios. GLiNER is specifically designed for this length regime and accepts custom entity labels via prompting, making it ideal for the "organization", "person", "location", and "job title" entities needed to improve clustering.

---

## Common Pitfalls

### Pitfall 1: Entity extraction on empty bio
**What goes wrong:** Running NER on accounts with empty bios produces no entities, wasting compute.
**How to avoid:** Gate entity extraction to accounts with `len(bio) >= 10` characters. For shorter bios, skip entity extraction and use Google search fallback instead.
**Warning signs:** 100% of entities list is empty across all accounts — indicates running on accounts without enough text.

### Pitfall 2: SerpApi rate limits hit during bulk enrichment
**What goes wrong:** SerpApi free tier is 250 searches/month. A 500-account batch exhausts this in one run.
**How to avoid:** Check for `SERPAPI_KEY` env var; if absent, skip Google search with a warning log. If present, track search count and warn at 200/250. Never block on a paid API being unavailable.
**Warning signs:** `serpapi.SearchError` with "Monthly limit reached" — implement exponential backoff and graceful skip.

### Pitfall 3: Following external links to slow/blocking servers
**What goes wrong:** Fetching a website linked in a profile bio can hang indefinitely if the server is slow or down.
**How to avoid:** Set `timeout=10` on all external link requests. Cap total link-following time per account at 30 seconds. Use `curl_cffi` (same session as profile scraper) for TLS impersonation.
**Warning signs:** `requests.Timeout` on multiple consecutive external links — stop following links for that account.

### Pitfall 4: Entity extraction changes embedding space between runs
**What goes wrong:** If entity extraction is non-deterministic (e.g., different model versions produce different entities), the embedding space changes, making cluster stability tracking impossible.
**How to avoid:** Pin `gliner` version in pyproject.toml. Cache entity extraction results in the same cache JSON file. Make entity extraction idempotent (re-extracting from same bio always yields same result).
**Warning signs:** Different cluster assignments for same input between runs — check entity extraction consistency.

---

## Code Examples

### Entity extraction with GLiNER (verified via research)
```python
# Source: https://github.com/urchade/gliner
from gliner import GLiNER

model = GLiNER.from_pretrained("urchade/gliner_base-v2.1")

text = "AI researcher at DeepMind. London-based. Previously Google Brain."
labels = ["person", "organization", "location", "job_title"]

entities = model.predict_entities(text, labels, threshold=0.5)
# Output: [{"text": "DeepMind", "label": "organization"}, {"text": "London", "label": "location"}, {"text": "AI researcher", "label": "job_title"}]
```

### SerpApi Google search (verified via research)
```python
# Source: https://serpapi.com/twitter-results
import os
import serpapi

client = serpapi.Client(api_key=os.getenv("SERPAPI_KEY"))
results = client.search({
    "engine": "google",
    "q": f'"{username}" site:x.com OR site:twitter.com',
})
# results["organic_results"] contains title, link, snippet
```

### Link extraction with BeautifulSoup (existing pattern)
```python
# Source: https://softhints.com/how-to-extract-all-the-external-links-or-url-from-a-webpage-using-python/
from bs4 import BeautifulSoup
import requests

response = requests.get(website_url, timeout=10)
soup = BeautifulSoup(response.text, "lxml")
links = [a.get("href") for a in soup.find_all("a", href=True)]
external = [l for l in links if l.startswith("http") and "x.com" not in l]
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| TF-IDF on raw bio text | Transformer embeddings (all-MiniLM-L6-v2) | Phase 4 (v1.0) | Massive improvement on short text |
| Bio-only embedding | Bio + location + category + pinned_tweet | Phase 3-4 (v1.0) | More signal; location helps geographic clustering |
| Raw bio text embedding | Entity-enriched bio text (with GLiNER) | Phase 8 (proposed) | Extracts implicit ORG/LOC/TITLE from sparse bios |
| No external context | Google search via SerpApi for cold-start accounts | Phase 8 (proposed) | Resolves cold-start for zero-bio accounts |
| Website field unused | Link extraction and following for bio-free accounts | Phase 8 (proposed) | Supplements sparse bios from personal websites |

**Deprecated/outdated:**
- DIY Google scraping with requests+BeautifulSoup: No longer viable as Google actively blocks automated queries with CAPTCHA. Use SerpApi instead.
- spaCy `en_core_web_sm` for bio NER: Small models underperform on short text. Use `en_core_web_trf` or GLiNER instead.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `gliner>=1.0.0` works on CPU without GPU | Standard Stack | GLiNER Base v2.1 runs on CPU but may be slow on large batches; no fallback if it requires GPU |
| A2 | `serpapi>=1.0.0` API format is stable | Architecture Patterns | SerpApi may change their result format; should validate with a test call |
| A3 | Entity extraction improves clustering for sparse bios | Code Examples | No guarantees; GLiNER entities may add noise rather than signal for some accounts |
| A4 | Google search with `site:x.com OR site:twitter.com` returns the correct account | Architecture Patterns | Common usernames may have false positive matches; needs disambiguation logic |
| A5 | External link following is legal under robots.txt | Common Pitfalls | Even if legal, following external links from X profile bios may violate those websites' terms |

---

## Open Questions

1. **Which entity types matter most for clustering?**
   - What we know: GLiNER can extract person, organization, location, job_title, event, misc
   - What's unclear: Which entity types actually improve cluster quality? (e.g., job_title may matter more than person names)
   - Recommendation: Start with org + location + job_title; evaluate silhouette score delta before adding person names

2. **Should entity extraction run on pinned_tweet_text or only bio?**
   - What we know: Pinned tweets can reveal interests, affiliations, locations
   - What's unclear: Pinned tweets may be noisy (jokes, quotes, old tweets) vs. bio which is self-declared identity
   - Recommendation: Extract entities from both bio and pinned_tweet_text, but weight bio entities higher in the embedding string

3. **Should Google search be gated on account importance (e.g., only for accounts in top N clusters by silhouette)?**
   - What we know: Cold-start accounts (no bio, no website) are hardest to cluster correctly
   - What's unclear: Whether the effort to resolve cold-start accounts is worth the SerpApi API cost
   - Recommendation: Only run Google search for accounts with NO bio AND NO website — this is already the coldest subset

4. **Should external link following respect a per-domain rate limit (e.g., 1 request per domain per account batch)?**
   - What we know: Websites may block repeated requests from the same IP
   - What's unclear: Optimal rate limit for external link following
   - Recommendation: Reuse the same `min_delay=2.0, max_delay=5.0` pattern from `XProfileScraper`; track domains visited

---

## Environment Availability

> Step 2.6: SKIPPED (no external dependencies beyond Python packages — all execution is local file processing and optional API calls)

**Note:** Phase 8 runs entirely on local data (enrichment cache JSON files) with optional external API calls:
- `gliner`: Python package (install via pip) — no external service dependency
- `serpapi`: Optional API key via env var — if absent, phase skips Google search gracefully
- `curl_cffi` + `beautifulsoup4`: Already in project deps

No CLI tools, databases, or services beyond Python packages need to be available.

---

## Security Domain

> Skipping Security Domain section — Phase 8 does not introduce new attack surfaces. All operations are:
> - Local file read/write (enrichment cache JSON files)
> - Optional outbound HTTP to external websites (link following)
> - Optional SerpApi API calls (if SERPAPI_KEY is set)

No new ASVS categories apply. The existing authentication (OAuth 2.0 PKCE) is not modified by Phase 8.

---

## Sources

### Primary (HIGH confidence)
- [urchade/GLiNER GitHub](https://github.com/urchade/gliner) - GLiNER model architecture, usage, entity labels
- [SerpApi Twitter Results API](https://serpapi.com/twitter-results) - SerpApi Google search for X accounts
- [How to scrape Google Twitter Results with Python - SerpApi Blog](https://serpapi.com/blog/scrape-google-twitter-results-with-python/) - Python integration pattern

### Secondary (MEDIUM confidence)
- [GLiNER zero-shot NER - Towards Data Science](https://towardsdatascience.com/extract-any-entity-from-text-with-gliner-32b413cea787/) - Entity extraction patterns for short text
- [Extract external links from webpage - CodeSpeedy](https://codespeedy.com/extract-all-the-external-links-or-url-from-a-webpage-using-python/) - BeautifulSoup link extraction pattern

### Tertiary (LOW confidence)
- [spaCy + Transformers NER Pipeline - agentbus.sh](https://agentbus.sh/posts/how-to-build-a-named-entity-recognition-pipeline/) - spaCy NER comparison; training not needed for this use case
- [GLiNER-BioMed April 2025 - arXiv:2504.00676](https://arxiv.org/pdf/2504.00676) - Biomedical entity extraction; different domain but same model family

---

## Metadata

**Confidence breakdown:**
- Standard stack: MEDIUM - GLiNER and SerpApi confirmed via WebSearch; exact package versions need verification against PyPI
- Architecture: MEDIUM - Pipeline integration points (entity extraction -> cache -> embed) confirmed by reading existing code
- Pitfalls: MEDIUM - All identified from general knowledge of these technologies; no project-specific validation

**Research date:** 2026-04-11
**Valid until:** 2026-05-11 (30 days; GLiNER and SerpApi are stable technologies)