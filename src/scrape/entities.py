"""Entity extraction using GLiNER for ORG, LOC, JOB_TITLE from bio text.

Provides:
- EntityResult: dataclass with orgs, locs, titles lists
- extract_entities(): runs GLiNER on bio + pinned_tweet_text + external_bio

Usage:
    from src.scrape.entities import extract_entities, EntityResult

    result = extract_entities("someaccount", cache_dir="data/enrichment")
    if result:
        print(result.orgs, result.locs, result.titles)
"""

from __future__ import annotations

import json
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Module-level model singleton (cache across accounts)
_model = None

# GLiNER max sequence length is ~384 tokens ≈ 1500 chars
MAX_CHUNK_CHARS = 1200


def _get_model() -> Any:
    """Get or create the GLiNER model singleton."""
    global _model
    if _model is None:
        from gliner import GLiNER

        # Suppress all GLiNER/transformers tokenizer warnings
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=FutureWarning, module="huggingface_hub")
            warnings.filterwarnings("ignore", category=UserWarning, message=".*sentencepiece.*byte fallback.*")
            warnings.filterwarnings("ignore", category=UserWarning, message=".*truncate.*max_length.*")
            _model = GLiNER.from_pretrained("urchade/gliner_medium-v2.1")
    return _model


def _chunk_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """Split text into chunks that fit within GLiNER's max sequence length.

    Tries to split on sentence boundaries (period + space) when possible.

    Args:
        text: Text to chunk.
        max_chars: Maximum characters per chunk (default 1200).

    Returns:
        List of text chunks.
    """
    if len(text) <= max_chars:
        return [text]

    chunks = []
    remaining = text

    while remaining:
        if len(remaining) <= max_chars:
            chunks.append(remaining)
            break

        # Find a good split point (period + space) within the limit
        split_point = remaining.rfind(". ", 0, max_chars)
        if split_point > max_chars // 2:
            # Good split point found
            chunks.append(remaining[:split_point + 1])
            remaining = remaining[split_point + 2:]
        else:
            # No good split point, just cut at max_chars
            chunks.append(remaining[:max_chars])
            remaining = remaining[max_chars:]

    return [c.strip() for c in chunks if c.strip()]


@dataclass
class EntityResult:
    """Entity extraction result for a single account.

    Attributes:
        username: Account username.
        orgs: Organization names extracted from bio text.
        locs: Location names extracted from bio text.
        titles: Job titles extracted from bio text.
    """

    username: str
    orgs: list[str]
    locs: list[str]
    titles: list[str]


def extract_entities(
    username: str,
    cache_dir: Path | str = Path("data/enrichment"),
    threshold: float = 0.5,
) -> EntityResult | None:
    """Extract ORG, LOC, JOB_TITLE entities from an account's text sources.

    Processes each text source separately to avoid GLiNER truncation, then
    merges and dedupes results. This ensures entity extraction works correctly
    even when recent_tweets_text is very long (50 tweets can be 5000+ chars).

    Per D-01: entity types are ORG, LOC, JOB_TITLE.
    Per D-02: run on both bio AND pinned_tweet_text.
    Per D-04: also run on external_bio when available.
    Per D-03: run on all bios regardless of length (no minimum threshold).

    Args:
        username: Account username (cache file stem).
        cache_dir: Directory containing {username}.json cache files.
        threshold: GLiNER confidence threshold (default 0.5).

    Returns:
        EntityResult if text was found, None if all texts were empty.
    """
    cache_dir = Path(cache_dir)
    cache_path = cache_dir / f"{username}.json"

    if not cache_path.exists():
        return None

    with open(cache_path, encoding="utf-8") as f:
        account = json.load(f)

    # Collect text sources as (source_name, text) pairs
    sources: list[tuple[str, str]] = []

    bio = account.get("bio") or account.get("description", "")
    if bio:
        sources.append(("bio", bio))

    pinned = account.get("pinned_tweet_text", "")
    if pinned:
        sources.append(("pinned", pinned))

    external_bio = account.get("external_bio", "")
    if external_bio:
        sources.append(("external", external_bio))

    # Chunk recent tweets to avoid truncation
    recent_tweets_text = account.get("recent_tweets_text", "")
    if recent_tweets_text:
        chunks = _chunk_text(recent_tweets_text)
        for i, chunk in enumerate(chunks):
            sources.append((f"tweets_{i}", chunk))

    if not sources:
        return None

    # Get model and labels
    model = _get_model()
    labels = ["organization", "location", "job_title"]

    # Extract entities from each source separately
    all_orgs: set[str] = set()
    all_locs: set[str] = set()
    all_titles: set[str] = set()

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=UserWarning, message=".*truncate.*max_length.*")

        for source_name, text in sources:
            if not text.strip():
                continue

            raw_entities = model.predict_entities(text, labels, threshold=threshold)

            for entity in raw_entities:
                label = entity["label"]
                text_val = entity["text"]

                if label == "organization":
                    all_orgs.add(text_val)
                elif label == "location":
                    all_locs.add(text_val)
                elif label == "job_title":
                    all_titles.add(text_val)

    # Convert sets to sorted lists for consistent output
    orgs = sorted(all_orgs)
    locs = sorted(all_locs)
    titles = sorted(all_titles)

    result = EntityResult(
        username=username,
        orgs=orgs,
        locs=locs,
        titles=titles,
    )

    # Cache entity results back to the account JSON (per D-18)
    account["entity_orgs"] = orgs
    account["entity_locs"] = locs
    account["entity_titles"] = titles

    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(account, f, indent=2)

    return result


__all__ = ["extract_entities", "EntityResult"]