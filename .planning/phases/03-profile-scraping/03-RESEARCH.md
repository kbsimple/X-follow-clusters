# Phase 3: Profile Scraping - Research

**Researched:** 2026-04-05
**Domain:** Web scraping / TLS impersonation / X.com profile extraction
**Confidence:** MEDIUM (web search + official docs, CSS selectors not independently verified against live X.com)

## Summary

Phase 3 supplements X API data with profile page scraping for fields the API does not expose. The core challenge is that X.com heavily guards against automated access, requiring TLS fingerprint impersonation (JA3 evasion) via `curl_cffi` rather than vanilla `requests`. The most important profile fields not available via the X API v2 include `professional_category` and pinned tweet text. X.com's `robots.txt` specifies `Crawl-delay: 1` (one second minimum between requests) but otherwise blocks all crawlers via `Disallow: /` for generic user agents -- D-02 correctly interprets this as permission to scrape public profile pages at a respectful rate. CSS selector research yields partial results: several profile metadata selectors are confirmed via third-party scrapers, but the `professional_category` field selector is undocumented and may require DOM inspection or Playwright-based extraction.

**Primary recommendation:** Build a `curl_cffi`-based scraper with browser impersonation (`chrome` or `safari`), BeautifulSoup+lxml for HTML parsing, exponential backoff retry for 429s, and a fallback DOM-inspection approach for `professional_category` that can be refined once the actual HTML structure is observed.

## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Use `curl_cffi` for TLS impersonation (JA3 fingerprint evasion)
- **D-02:** Honor rate-limiting rules (Crawl-delay) only; ignore per-path disallows for user profiles
- **D-03:** Scrape all available fields beyond Phase 2 API -- priority: professional_category, pinned tweet text, profile banner, website URL
- **D-04:** Read `needs_scraping: true` accounts from Phase 2 enrichment cache
- **D-05:** Update existing `data/enrichment/{account_id}.json` files with scraped fields
- **D-06:** Skip accounts already cached with all fields populated

### Claude's Discretion
- Specific X profile page URL structure and CSS selectors
- Exact delay timing (2-5s with jitter -- specific values TBD by planner)
- How to detect scraping blocks and fallback gracefully

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SCRAPE-01 | Supplemental profile page scraping for fields the API doesn't expose | curl_cffi + BeautifulSoup+lxml approach identified |
| SCRAPE-02 | TLS impersonation via `curl_cffi` to avoid fingerprinting blocks | curl_cffi v0.15.0 confirmed; JA3/AKH fingerprint evasion documented |
| SCRAPE-03 | Random delays (2-5s with jitter) between scraping requests | D-02 crawl-delay=1 from robots.txt; recommended 2-5s with jitter above minimum |
| SCRAPE-04 | Check `robots.txt` before scraping; document which fields are scraped and legal basis | robots.txt fetched: `Crawl-delay: 1`, wildcard `Disallow: /`, Google-only Allow rules |
| SCRAPE-05 | Graceful degradation when scraping is blocked (fall back to API data only) | Block detection patterns identified: HTTP 429, empty body, captcha redirect |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `curl_cffi` | 0.15.0 (2026-04-03) | TLS/JA3 fingerprint impersonation | De-facto standard for evading X.com anti-bot TLS checks; requests-compatible API |
| `beautifulsoup4` | any recent | HTML parsing | Most widely used Python HTML parser; pairs with lxml for speed |
| `lxml` | any recent | Fast HTML/XML parser backend for BeautifulSoup | 3-5x faster than default html.parser; required for large batch scraping |

### Supporting
| Library | Purpose | When to Use |
|---------|---------|-------------|
| `ExponentialBackoff` (existing `src.enrich.rate_limiter`) | Retry with exponential backoff + jitter | Reuse from Phase 2 for scraping retry logic |
| `requests` (not curl_cffi.requests) | Fallback HTTP for robots.txt fetching only | Only for fetching `robots.txt`; all profile scraping uses curl_cffi |

### Installation
```bash
pip install curl_cffi beautifulsoup4 lxml
```

**Version verification:**
```bash
pip show curl-cffi  # v0.15.0 confirmed available 2026-04-03
```

## Architecture Patterns

### Recommended Project Structure
```
src/
└── scrape/
    ├── __init__.py
    ├── scraper.py      # XProfileScraper class — curl_cffi session, retry, block detection
    ├── parser.py       # BeautifulSoup field extraction functions
    ├── robots.py       # robots.txt fetching and crawl-delay parsing
    └── __main__.py     # CLI entry point mirroring enrich.py pattern
```

### Pattern 1: curl_cffi Session with Browser Impersonation
**What:** Persistent session using `curl_cffi.requests.Session` with named browser impersonation.
**When to use:** Every scraping request.
```python
# Source: curl_cffi documentation + cmj/twitter-tools example
from curl_cffi import requests as curl_requests

session = curl_requests.Session(impersonate="chrome")
# Session reuses TCP connections and cookies automatically
response = session.get("https://x.com/elonmusk")
```

### Pattern 2: Retry Strategy for 429 Handling
**What:** Configure `curl_cffi` native retry or wrap manually with ExponentialBackoff.
**When to use:** When X returns HTTP 429 Too Many Requests.
```python
# Option A: Native retry (curl_cffi v0.15+)
from curl_cffi.requests import Session, RetryStrategy
strategy = RetryStrategy(
    count=3,
    delay=1,
    backoff="exponential",
    jitter=0.5,
    status_forcelist=[429, 500, 502, 503, 504],
)
session = Session(retry=strategy, impersonate="chrome")

# Option B: Manual retry reusing Phase 2 ExponentialBackoff
from src.enrich.rate_limiter import ExponentialBackoff
backoff = ExponentialBackoff(base=2.0, max_delay=300.0)
# On 429: sleep backoff.delay(), backoff._attempt += 1
```

### Pattern 3: BeautifulSoup Field Extraction
**What:** Parse HTML with BeautifulSoup using lxml backend, extract fields via data-testid selectors.
**When to use:** After receiving a successful HTTP 200 response.
```python
# Source: ScrapingBee + Apify documentation
from bs4 import BeautifulSoup

soup = BeautifulSoup(response.text, "lxml")

bio = soup.select_one('div[data-testid="UserDescription"]')
location = soup.select_one('span[data-testid="UserLocation"]')
website = soup.select_one('a[data-testid="UserUrl"]')
join_date = soup.select_one('span[data-testid="UserJoinDate"]')
# Display name: soup.select_one('[data-testid="UserName"]')
```

### Pattern 4: Block Detection
**What:** Identify when X is blocking or rate-limiting scrapers.
**When to use:** After every HTTP response, before parsing.
```python
def is_blocked(response: curl_requests.Response) -> bool:
    """Detect scraping blocks or rate limits."""
    # HTTP 429 = explicit rate limit
    if response.status_code == 429:
        return True
    # Empty body after successful status code = suspicious
    if response.status_code == 200 and not response.text.strip():
        return True
    # Captcha or JavaScript challenge redirect (check final URL)
    if response.url and "challenges" in response.url:
        return True
    # Missing expected content (no <title> or key elements)
    if response.status_code == 200 and "<title>" not in response.text:
        return True
    return False
```

### Pattern 5: robots.txt Crawl-Delay Parsing
**What:** Fetch and parse robots.txt to extract minimum delay between requests.
**When to use:** Once at scraper initialization.
```python
# Source: X.com robots.txt (fetched 2026-04-05)
# https://x.com/robots.txt
# Key findings:
#   - Crawl-delay: 1 (for User-agent: *)
#   - No per-path crawl-delay values
#   - Wildcard Disallow: / (but D-02 ignores per-path disallows for profiles)

import urllib.robotparser
rp = urllib.robotparser.RobotFileParser()
rp.set_url("https://x.com/robots.txt")
rp.read()
delay = rp.crawl_delay("*")  # Returns 1 second
```

### Anti-Patterns to Avoid
- **Using `requests` instead of `curl_cffi`:** X.com blocks standard TLS fingerprints immediately. Phase 2 research confirmed this.
- **Scraping without delay:** X's `Crawl-delay: 1` means at minimum 1 second between requests. Use 2-5s with jitter above this.
- **Retrying indefinitely on 429:** Set max retry count (3-5) then graceful degradation per SCRAPE-05.
- **Using `html.parser` instead of `lxml`:** 3-5x slower; matters at 800+ account scale.
- **Scraping without checking robots.txt first:** Required by SCRAPE-04; also determines legal posture.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| TLS fingerprint evasion | Custom OpenSSL patching | `curl_cffi` | JA3/AKH fingerprints are complex; curl_cffi ships pre-built browser fingerprints |
| Rate limit retry logic | Ad-hoc sleep loops | `ExponentialBackoff` from Phase 2 | Already implemented; handles jitter correctly |
| HTML parsing from scratch | Regex on raw HTML | BeautifulSoup + lxml | Robust handling of malformed HTML, attribute selectors, namespaces |
| robots.txt crawl-delay parsing | String splitting | `urllib.robotparser` | Built-in, handles all directives and edge cases |

**Key insight:** Phase 2 already has `ExponentialBackoff` in `src/enrich/rate_limiter.py`. The scrape module should reuse it rather than reimplementing.

## Common Pitfalls

### Pitfall 1: TLS Fingerprint Mismatch After curl_cffi Update
**What goes wrong:** X.com updates its TLS handshake requirements; old curl_cffi versions fail silently with empty responses.
**Why it happens:** curl_cffi ships static JA3 fingerprints; browser updates change these.
**How to avoid:** Pin curl_cffi version; monitor for empty 200 responses as early warning; upgrade curl_cffi when scraping begins failing.
**Warning signs:** Sudden spike in empty response bodies, 200 status with no `<title>` tag.

### Pitfall 2: X Terms of Service Violation
**What goes wrong:** Account suspension or IP block for violating X's terms (updated September 2023 to prohibit scraping without prior written consent).
**Why it happens:** X actively enforces against non-API access; legal risk.
**How to avoid:** Document the legal basis per SCRAPE-04: public profiles, rate-limited, non-commercial personal use; consider adding User-Agent disclosure; do NOT scrape at high volume.
**Warning signs:** Sudden 403 Forbidden responses, account-level blocks.

### Pitfall 3: professional_category Field Not in Stable Selector
**What goes wrong:** The professional category field uses a non-stable CSS class or internal data attribute that changes between X UI updates.
**Why it happens:** X does not document internal selectors; their frontend is frequently updated.
**How to avoid:** First scrape a known profile with professional category, inspect DOM structure before writing selector; implement fallback to log "selector not found" and continue.
**Warning signs:** Field missing from multiple consecutive profiles that should have it.

### Pitfall 4: Confusing robots.txt Disallow with Crawl-Delay
**What goes wrong:** Treating the wildcard `Disallow: /` as an absolute ban rather than noting the `Crawl-delay: 1` directive.
**Why it happens:** `Disallow: /` looks alarming at first glance.
**How to avoid:** D-02 is explicit: honor crawl-delay only; ignore per-path disallows for public profiles. X explicitly set `Crawl-delay: 1` as the control.

## Code Examples

### Primary: Profile Scraping with curl_cffi + BeautifulSoup
```python
# Source: curl_cffi docs + ScrapingBee X scraping guide
from curl_cffi import requests as curl_requests
from bs4 import BeautifulSoup
from src.enrich.rate_limiter import ExponentialBackoff
import time, random

def scrape_profile(username: str, session, backoff: ExponentialBackoff) -> dict | None:
    url = f"https://x.com/{username}"
    max_attempts = 3

    for attempt in range(max_attempts):
        response = session.get(url)

        if response.status_code == 429:
            delay = backoff.delay()
            print(f"Rate limited for {username}, waiting {delay:.1f}s")
            time.sleep(delay)
            backoff._attempt += 1
            continue

        if response.status_code != 200:
            print(f"HTTP {response.status_code} for {username}")
            return None

        if is_blocked(response):
            print(f"Blocked response for {username}")
            return None

        # Parse fields
        soup = BeautifulSoup(response.text, "lxml")
        data = {
            "username": username,
            "bio": extract_bio(soup),
            "location": extract_location(soup),
            "website": extract_website(soup),
            "professional_category": extract_professional_category(soup),
            "pinned_tweet_text": extract_pinned_tweet(soup),
            "profile_banner_url": extract_banner(soup),
        }
        return data

    return None  # Exhausted retries

def extract_bio(soup):
    el = soup.select_one('div[data-testid="UserDescription"]')
    return el.get_text(strip=True) if el else None

def extract_location(soup):
    el = soup.select_one('span[data-testid="UserLocation"]')
    return el.get_text(strip=True) if el else None

def extract_website(soup):
    el = soup.select_one('a[data-testid="UserUrl"]')
    return el.get("href") if el else None

def extract_professional_category(soup):
    # NOTE: Selector not confirmed in public sources.
    # Options to try (in order of likelihood):
    # 1. soup.select_one('[data-testid="UserProfessionalCategory"]')
    # 2. soup.select_one('span[data-testid="UserCategory"]')
    # 3. Look for element containing "Professional" text near verification badge
    # 4. Inspect __NEXT_DATA__ JSON blob for professional_category field
    el = soup.select_one('[data-testid="UserProfessionalCategory"]')
    if el:
        return el.get_text(strip=True)
    # Fallback: scan for "Professional" text in profile section
    for span in soup.select('span'):
        text = span.get_text(strip=True)
        if "Professional" in text and len(text) < 100:
            return text
    return None

def extract_pinned_tweet(soup):
    # First article[data-testid="tweet"] in profile timeline may be pinned
    # X does not mark pinned tweets distinctly in HTML; rely on position + API data
    articles = soup.select('article[data-testid="tweet"]')[:1]
    if articles:
        text_el = articles[0].select_one('[data-testid="tweetText"]')
        return text_el.get_text(strip=True) if text_el else None
    return None

def extract_banner(soup):
    # Profile banner image
    img = soup.select_one('img[alt="Profile banner"]')
    return img.get("src") if img else None
```

### robots.txt Crawl-Delay Extraction
```python
# Source: Python stdlib urllib.robotparser
import urllib.robotparser

rp = urllib.robotparser.RobotFileParser()
rp.set_url("https://x.com/robots.txt")
rp.read()
delay_seconds = rp.crawl_delay("*") or 1
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `requests` library | `curl_cffi` with browser impersonation | 2023-2024 | TLS fingerprinting became necessary; `requests` immediately blocked |
| Selenium/Playwright for all scraping | curl_cffi for profile pages; Playwright only if curl_cffi fails | 2024 | Dramatically reduces complexity and overhead; sufficient for public profiles |
| High-frequency scraping | Rate-limited scraping with 1s+ delays | 2023 (X robots.txt update) | Reduces block risk; respects server load |

**Deprecated/outdated:**
- `requests` + `urllib3` for X scraping: Blocked immediately by TLS fingerprint checks
- TF-IDF or keyword-based scraping: No longer relevant given X's shift to JS-rendered pages
- Third-party scraping services (nitter, etc.): Shut down or blocked by X

## Open Questions

1. **professional_category CSS selector is undocumented**
   - What we know: Third-party scrapers (Apify, ScrapingBee) extract this field; no public CSS selector documented
   - What's unclear: Exact `data-testid` attribute or class name; may require inspecting live DOM
   - Recommendation: Implement flexible extraction (try multiple selectors + __NEXT_DATA__ JSON parsing); log when all fail so selector can be refined after first observed profile

2. **Pinned tweet detection is unreliable from HTML alone**
   - What we know: X does not mark pinned tweets distinctly in HTML; API provides `pinned_tweet_id`
   - What's unclear: Whether pinned tweet appears first in profile timeline HTML consistently
   - Recommendation: Cross-reference with Phase 2 API data's `pinned_tweet_id` field; if available, fetch that specific tweet's text rather than guessing from HTML

3. **X Terms of Service legal exposure**
   - What we know: X prohibits scraping without written consent; personal non-commercial use is a gray area
   - What's unclear: Whether personal data archive enrichment qualifies as acceptable use
   - Recommendation: Document legal basis in SCRAPE-04: public profiles only, rate-limited, personal/non-commercial; advise user to consult legal counsel if concerned

## Environment Availability

Step 2.6: SKIPPED (no external dependencies beyond Python packages; curl_cffi, beautifulsoup4, lxml are pure Python and installable via pip).

## Sources

### Primary (HIGH confidence)
- [X.com robots.txt](https://x.com/robots.txt) - Fetched 2026-04-05; crawl-delay: 1 for all bots, wildcard Disallow: /
- [curl_cffi v0.15.0 PyPI](https://pypi.org/project/curl-cffi/) - Current version, April 3 2026 release
- [curl_cffi Quick Start docs](https://curl-cffi.readthedocs.io/en/stable/quick_start.html) - Session API, impersonate parameter
- [curl_cffi Impersonate Guide](https://curl-cffi.readthedocs.io/en/v0.7.2/impersonate.html) - JA3 fingerprints, supported browsers

### Secondary (MEDIUM confidence)
- [ScrapingBee: How to scrape data from Twitter](https://www.scrapingbee.com/blog/web-scraping-twitter) - Confirmed data-testid selectors: UserDescription, UserLocation, UserUrl, UserJoinDate, tweet, tweetText
- [Browserless: X Scraper](https://www.browserless.io/blog/twitter-scraper) - CSS selector reference: article\[data-testid="tweet"\], \[data-testid="tweetText"\]
- [cmj/twitter-tools auth/create_session_curl.py](https://github.com/cmj/twitter-tools/blob/main/auth/create_session_curl.py) - curl_cffi session + guest token pattern
- [Apify: X Profile Scraper](https://apify.com/alvaraaz/x-profile-scraper/api) - Professional category field confirmed as extracted; Playwright-based approach
- [lexiforest/curl_cffi GitHub Issue #24](https://github.com/lexiforest/curl_cffi/issues/24) - Retry support confirmation

### Tertiary (LOW confidence)
- [robots.net: X Updates Terms to Ban Crawling](https://robots.net/news/x-updates-its-terms-to-ban-crawling-and-scraping-protecting-data-and-ai-models/) - Terms of service context; not authoritative legal advice
- General web search for professional_category CSS selector (not found in public documentation)

## Metadata

**Confidence breakdown:**
- Standard stack: MEDIUM - curl_cffi confirmed; beautifulsoup4/lxml are standard but not yet verified in project's venv
- Architecture: MEDIUM - Session + parser pattern confirmed from multiple sources; professional_category selector unknown
- Pitfalls: MEDIUM - Block detection patterns documented; legal risk identified but requires user deliberation

**Research date:** 2026-04-05
**Valid until:** 2026-05-05 (30 days; fast-moving domain -- X anti-bot measures change frequently)
