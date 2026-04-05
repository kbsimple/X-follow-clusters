# X API Alternatives

This document compares approaches for obtaining X (Twitter) data when you don't have or don't want to pay for official X API access.

---

## Official X API (Basic Tier)

**Cost:** $100/month (as of 2024)

**What you get:**
- Access to Twitter API v2 endpoints
- GET /2/users/me for credential verification
- Followers/following lookup endpoints
- Tweet reading and posting
- Rate limits vary by endpoint (Basic tier: ~500k tweets/month, 50k reads/month for followers)

**How to get it:**
1. Apply at https://developer.x.com/en/docs/twitter-api/twitter-api-labs
2. Create a project and app
3. Generate OAuth 1.0a credentials (API Key + Secret, Access Token + Secret)
4. Optionally generate Bearer Token for app-only auth

**Pros:**
- Official, supported, stable API
- No risk of IP blocks or legal issues
- Consistent rate limits

**Cons:**
- $100/month is a significant commitment
- Basic tier may still have restrictive rate limits for bulk operations
- Application review process can be slow

---

## Apify Twitter Followers Scraper

**Cost:** Free tier (5K actor credits), then ~$49/month for 100K credits

**What it scrapes:**
- Twitter user profiles (username, bio, followers/following count, etc.)
- Follower/following lists
- Tweets
- Uses residential proxies to avoid blocks

**How it works:**
1. Create account at https://apify.com
2. Use the `twitter-followers-scraper` or `twitter-user-scraper` actor
3. Pass in target Twitter handles
4. Actor returns structured JSON with profile data

**Pros:**
- No Twitter API approval process needed
- Can scrape data that API doesn't expose (full profile HTML, specific tweet data)
- Residential proxies included (handles anti-bot detection)

**Cons:**
- Not an official API - ToS compliance is murky
- Data freshness depends on scrape timing
- Cost can escalate for large followings

**Integration:**
```python
from apify_client import ApifyClient

client = ApifyClient("YOUR_API_TOKEN")
actor_call = client.actor("YOUR_ACTOR_ID").call()
# Returns structured follower data
```

---

## Bright Data X (Twitter) Scraper

**Cost:** Starts at ~$500/month for scraping suite (includes X)

**What it scrapes:**
- Full Twitter profile data
- Historical tweets
- Followers/following data
- Uses residential proxy network

**How it works:**
1. Set up Bright Data account
2. Access X data via their SERP API or scraping browser
3. Residential proxies rotate automatically

**Pros:**
- Very robust, handles anti-bot measures automatically
- Legal compliance layer (Bright Data handles some legal exposure)
- High data quality

**Cons:**
- Expensive - overkill for single-user projects
- Requires technical setup (proxy integration)
- Minimum commitment can be high

---

## Comparison Table

| Approach | Monthly Cost | Ease of Setup | Data Completeness | Rate Limits | Legal Risk |
|----------|-------------|---------------|-------------------|-------------|------------|
| X API Basic | $100 | Medium (needs approval) | High (official) | ~500K tweets/mo | None (official) |
| Apify Scraper | ~$49+ | Easy | High (full profiles) | No formal limits | Moderate |
| Bright Data | ~$500+ | Hard | Very High | Virtually unlimited | Low-Moderate |
| Manual Export | Free | Easy | Limited (archive only) | N/A | None |

---

## Recommendation

**For this project (X Following Organizer):**

1. **Start with X API Basic ($100/mo)** if you plan to run this tool regularly or at scale. The official API is the most reliable and legally safe option.

2. **Consider Apify** if you want to try without committing $100/month. The free tier is enough to test with a small following list, and the cost is predictable.

3. **Use the X data archive (free)** as a fallback. The `follower.js` file from an X data export gives you your current following list without needing any API access.

4. **Bright Data is overkill** for this use case unless you're building a commercial product.

---

## For This Project

The auth module in `src/auth/x_auth.py` is designed to work with official X API credentials. If you choose Apify or another scraping service instead, you would:

1. Update `src/enrich/` to call the scraping service API instead of `verify_credentials()`
2. Use environment variables like `APIFY_API_TOKEN` (see `.env.example`)
3. Handle rate limits and errors according to the service's documentation

The core workflow (parse archive -> enrich profiles -> cluster -> create lists) remains the same regardless of data source.
