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

from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Module-level model singleton (cache across accounts)
_model = None


def _get_model() -> Any:
    """Get or create the GLiNER model singleton."""
    global _model
    if _model is None:
        from gliner import GLiNER
        _model = GLiNER.from_pretrained("urchade/gliner_base-v2.1")
    return _model


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
    """Extract ORG, LOC, JOB_TITLE entities from an account's bio text.

    Runs on: bio + pinned_tweet_text + external_bio (if available).
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
    import json

    cache_dir = Path(cache_dir)
    cache_path = cache_dir / f"{username}.json"

    if not cache_path.exists():
        return None

    with open(cache_path, encoding="utf-8") as f:
        account = json.load(f)

    # Collect text sources (per D-02 and D-04)
    texts = []
    bio = account.get("bio") or account.get("description", "")
    if bio:
        texts.append(bio)

    pinned = account.get("pinned_tweet_text", "")
    if pinned:
        texts.append(pinned)

    external_bio = account.get("external_bio", "")
    if external_bio:
        texts.append(external_bio)

    if not texts:
        return None

    combined_text = " ".join(texts)

    # Run GLiNER prediction
    model = _get_model()
    labels = ["organization", "location", "job_title"]
    raw_entities = model.predict_entities(combined_text, labels, threshold=threshold)

    # Filter and dedupe by type
    orgs = list({e["text"] for e in raw_entities if e["label"] == "organization"})
    locs = list({e["text"] for e in raw_entities if e["label"] == "location"})
    titles = list({e["text"] for e in raw_entities if e["label"] == "job_title"})

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