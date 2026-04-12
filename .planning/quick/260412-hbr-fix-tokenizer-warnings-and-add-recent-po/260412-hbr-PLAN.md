---
phase: 260412-hbr
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/scrape/entities.py
  - src/enrich/api_client.py
  - src/enrich/test_enrich.py
autonomous: true
requirements: []
user_setup: []

must_haves:
  truths:
    - "GLiNER loads without tokenizer warnings"
    - "Recent tweets are fetched and cached for enriched accounts"
    - "Recent tweets are displayed in test_enrich.py output"
  artifacts:
    - path: "src/scrape/entities.py"
      provides: "Warning-free entity extraction"
    - path: "src/enrich/api_client.py"
      provides: "get_recent_tweets() method for fetching user timeline"
    - path: "src/enrich/test_enrich.py"
      provides: "Recent tweets display in pipeline output"
  key_links:
    - from: "src/enrich/test_enrich.py"
      to: "XEnrichmentClient.get_recent_tweets()"
      via: "API call after enrichment"
      pattern: "get_recent_tweets"
---

<objective>
Fix GLiNER tokenizer warnings and add recent tweets functionality to the enrichment pipeline.

Purpose: Clean up noisy warnings that clutter output, and enhance enrichment with recent tweet data for better entity extraction and context.

Output: Warning-free entity extraction, recent tweets cached and displayed in test_enrich.py.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/PROJECT.md

## Current State

- v1.1 milestone shipped (OAuth 2.0 PKCE + 3scrape pipeline)
- GLiNER entity extraction works but emits noisy warnings from transformers/sentencepiece
- Enrichment fetches user profiles but not recent tweets
- 3scrape pipeline includes entity extraction on bio + pinned_tweet_text + external_bio
</context>

<tasks>

<task type="auto">
  <name>Task 1: Suppress GLiNER tokenizer warnings in entities.py</name>
  <files>src/scrape/entities.py</files>
  <action>
Expand the warnings filter in `_get_model()` to catch all GLiNER-related tokenizer warnings:

1. The current filter only catches `FutureWarning` from `huggingface_hub`
2. Add filters for:
   - `UserWarning` from `transformers` about sentencepiece byte fallback
   - `UserWarning` from `transformers` about truncation without max_length

Wrap the entire `GLiNER.from_pretrained()` call and also wrap the `model.predict_entities()` call in `extract_entities()` since the truncation warning appears at inference time.

Pattern:
```python
import warnings

# Suppress all GLiNER/transformers tokenizer warnings
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", category=FutureWarning, module="huggingface_hub")
    warnings.filterwarnings("ignore", category=UserWarning, message=".*sentencepiece.*byte fallback.*")
    warnings.filterwarnings("ignore", category=UserWarning, message=".*truncate.*max_length.*")
    # GLiNER operations here
```
  </action>
  <verify>
    <automated>.venv/bin/python -c "from src.scrape.entities import extract_entities; extract_entities('test', cache_dir='data/enrichment')" 2>&1 | grep -c "sentencepiece\|truncate" || echo "No warnings found"</automated>
  </verify>
  <done>No sentencepiece or truncation warnings appear during GLiNER model loading or entity extraction.</done>
</task>

<task type="auto">
  <name>Task 2: Add recent tweets fetching and display in test_enrich.py</name>
  <files>src/enrich/api_client.py, src/enrich/test_enrich.py</files>
  <action>
Add functionality to fetch recent tweets via X API and display them in test_enrich.py:

**Part A: Add get_recent_tweets() to XEnrichmentClient (api_client.py)**

Add a new method to fetch recent tweets for a user:
```python
def get_recent_tweets(
    self,
    user_id: str,
    max_tweets: int = 5,
) -> list[dict[str, Any]]:
    """Fetch recent tweets for a user.

    Args:
        user_id: X user ID.
        max_tweets: Maximum tweets to fetch (default 5).

    Returns:
        List of tweet dicts with 'text' and 'created_at' fields.
    """
    try:
        response = self._client.get_users_tweets(
            id=user_id,
            max_results=min(max_tweets, 10),  # API allows 5-100
            tweet_fields=["created_at", "public_metrics"],
            exclude=["retweets", "replies"],  # Just original tweets
        )
        body = response.json()
        return body.get("data") or []
    except Exception as e:
        logger.warning("Failed to fetch tweets for %s: %s", user_id, e)
        return []
```

**Part B: Update test_enrich.py to fetch and display recent tweets**

After the 3scrape pipeline step, add a new step to fetch recent tweets for each enriched account:
1. Call `client.get_recent_tweets(account_id)` for each enriched account
2. Cache the tweets to the account JSON file under a `recent_tweets` key
3. Display tweet previews (first 100 chars of each) in the output
4. Show tweet count in the summary

Add after Step 8 (3scrape pipeline):
```python
# Step 9: Fetch recent tweets
print("\n[Step 9] Fetching recent tweets...")
tweets_fetched_count = 0

for account_id in sample_ids:
    username = id_to_username.get(account_id, account_id)
    try:
        tweets = client.get_recent_tweets(account_id)
        if tweets:
            print(f"  @{username}: {len(tweets)} recent tweets")
            for i, tweet in enumerate(tweets[:3]):  # Show first 3
                text_preview = tweet.get("text", "")[:80]
                if len(tweet.get("text", "")) > 80:
                    text_preview += "..."
                print(f"    [{i+1}] {text_preview}")
            tweets_fetched_count += 1

            # Cache tweets
            cache_path = cache_dir / f"{account_id}.json"
            if cache_path.exists():
                with open(cache_path, encoding="utf-8") as f:
                    account = json.load(f)
                account["recent_tweets"] = tweets
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(account, f, indent=2)
        else:
            print(f"  @{username}: no recent tweets")
    except Exception as e:
        print(f"  @{username}: error fetching tweets - {e}")
```

Update the summary section to include tweets fetched count.
  </action>
  <verify>
    <automated>.venv/bin/python -m src.enrich.test_enrich 2>&1 | grep -E "recent tweets|tweets fetched" || echo "Check output for tweets section"</automated>
  </verify>
  <done>
- get_recent_tweets() method exists on XEnrichmentClient
- test_enrich.py fetches and caches recent tweets for enriched accounts
- Recent tweets are displayed in output with preview text
- Summary includes tweets fetched count
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| X API → Client | Tweets come from external X API, already trusted in existing auth flow |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-260412-01 | I | get_recent_tweets | accept | Tweet text from X API, already sanitized by platform |
</threat_model>

<verification>
1. Run test_enrich.py and verify no tokenizer warnings appear
2. Verify recent tweets section appears in output
3. Verify tweets are cached in account JSON files
</verification>

<success_criteria>
- No sentencepiece or truncation warnings during GLiNER operations
- Recent tweets fetched, cached, and displayed for enriched accounts
- test_enrich.py output shows tweet previews
</success_criteria>

<output>
After completion, create `.planning/quick/260412-hbr-fix-tokenizer-warnings-and-add-recent-po/260412-hbr-SUMMARY.md`
</output>