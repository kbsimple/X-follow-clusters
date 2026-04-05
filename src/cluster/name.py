"""LLM-generated cluster naming using central member bios.

Pipeline:
1. Load central_member_usernames per cluster from cache files
2. Load bios for those central members from data/enrichment/{username}.json
3. Call LLM (OpenAI GPT-4o-mini or Anthropic Claude Haiku) with bios
4. Fall back to rule-based naming if no API credentials
5. Write cluster_name back to all member cache files
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections import Counter
from pathlib import Path
from typing import Literal

import yaml

logger = logging.getLogger(__name__)

LLM_NAME_PROMPT = """The following accounts share a common characteristic. Based on their bios, give this group a short, descriptive name (3-5 words).

Accounts:
{bios_text}

Group name:"""

# Module-level flag set on import
_LLM_PROVIDER: Literal["openai", "anthropic", "rule_based"] = "rule_based"

# Check credentials and set provider on import
if os.environ.get("OPENAI_API_KEY"):
    _LLM_PROVIDER = "openai"
    logger.info("Using OpenAI GPT-4o-mini for cluster naming")
elif os.environ.get("ANTHROPIC_API_KEY"):
    _LLM_PROVIDER = "anthropic"
    logger.info("Using Anthropic Claude for cluster naming")
else:
    _LLM_PROVIDER = "rule_based"
    logger.warning("No LLM credentials found; using rule-based naming")


# ---------------------------------------------------------------------------
# Bio loading
# ---------------------------------------------------------------------------

def _get_bios_text(central_usernames: list[str], cache_dir: Path) -> str:
    """Load bios for the given central usernames from cache files.

    Parameters
    ----------
    central_usernames : list[str]
        List of usernames to load bios for.
    cache_dir : Path
        Path to data/enrichment directory.

    Returns
    -------
    str
        Bios formatted as "- {bio}" lines, one per account.
        Returns "" if no bios found or cache_dir does not exist.
    """
    if not cache_dir or not cache_dir.exists():
        logger.warning("Cache directory %s does not exist; cannot load bios", cache_dir)
        return ""

    bios_lines: list[str] = []
    for uname in central_usernames:
        acct_file = cache_dir / f"{uname}.json"
        if not acct_file.exists():
            # Search by username
            found = False
            for f in cache_dir.glob("*.json"):
                if f.stem in ("suspended", "protected", "errors"):
                    continue
                try:
                    d = json.load(open(f))
                    if d.get("username") == uname:
                        acct_file = f
                        found = True
                        break
                except Exception:
                    continue
            if not found:
                logger.warning("Account %s not found in enrichment cache", uname)
                continue

        try:
            d = json.load(open(acct_file))
        except Exception as e:
            logger.warning("Could not load %s: %s", acct_file, e)
            continue

        bio = d.get("description", "").strip()
        if bio:
            bios_lines.append(f"- {bio}")
        else:
            logger.warning("Account %s has no description field", uname)

    return "\n".join(bios_lines)


# ---------------------------------------------------------------------------
# LLM naming
# ---------------------------------------------------------------------------

def name_cluster(bios: list[str], model: str = "gpt-4o-mini") -> str:
    """Generate a descriptive cluster name from a list of account bios.

    Parameters
    ----------
    bios : list[str]
        List of bio strings (one per account).
    model : str
        Model to use. "gpt-4o-mini" (OpenAI) or "claude-3-5-haiku" (Anthropic).
        Ignored if OPENAI_API_KEY / ANTHROPIC_API_KEY not set.

    Returns
    -------
    str
        3-5 word descriptive cluster name, or "Unnamed Cluster" if bios is empty.
    """
    if not bios:
        return "Unnamed Cluster"

    if _LLM_PROVIDER == "rule_based":
        logger.debug("Using rule-based naming (no API credentials)")
        return rule_based_name(bios)

    if _LLM_PROVIDER == "openai":
        return _name_cluster_openai(bios, model)
    elif _LLM_PROVIDER == "anthropic":
        return _name_cluster_anthropic(bios, model)

    return rule_based_name(bios)


def _name_cluster_openai(bios: list[str], model: str) -> str:
    """Call OpenAI GPT-4o-mini for cluster naming."""
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    bios_text = "\n".join(f"- {bio}" for bio in bios)
    prompt = LLM_NAME_PROMPT.format(bios_text=bios_text)

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=32,
    )

    name = response.choices[0].message.content or ""
    name = name.strip().strip('"').strip("'")
    if not name:
        logger.warning("Empty response from OpenAI; falling back to rule-based")
        return rule_based_name(bios)

    logger.info("OpenAI named cluster: %s", name)
    return name


def _name_cluster_anthropic(bios: list[str], model: str) -> str:
    """Call Anthropic Claude Haiku for cluster naming."""
    from anthropic import Anthropic

    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    bios_text = "\n".join(f"- {bio}" for bio in bios)
    prompt = LLM_NAME_PROMPT.format(bios_text=bios_text)

    response = client.messages.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=32,
    )

    name = response.content[0].text or ""
    name = name.strip().strip('"').strip("'")
    if not name:
        logger.warning("Empty response from Anthropic; falling back to rule-based")
        return rule_based_name(bios)

    logger.info("Anthropic named cluster: %s", name)
    return name


# ---------------------------------------------------------------------------
# Rule-based fallback
# ---------------------------------------------------------------------------

def rule_based_name(bios: list[str]) -> str:
    """Simple keyword-based fallback naming when no LLM is available.

    Scans bios for common patterns and returns a generic interest-group name
    if no clear pattern emerges.

    Parameters
    ----------
    bios : list[str]
        List of bio strings.

    Returns
    -------
    str
        A 3-5 word descriptive name based on detected keywords.
    """
    # Common keyword patterns (normalized to lowercase for matching)
    keyword_groups: list[tuple[str, list[str]]] = [
        ("Tech & AI", ["ai ", "artificial intelligence", "machine learning", "software", "engineer", "developer", "programming", "tech ", "data science", "startup", "founder", "cto", "ceo", "product"]),
        ("Venture & Finance", ["vc ", "venture", "investor", "finance", "fintech", "crypto", "banking", "financial", "fund ", "hedge fund", "trading", "quant", "wealth"]),
        ("Science & Research", ["research", "scientist", "phd", "professor", "academic", "university", "biology", "physics", "chemistry", "neuroscience", "genomics"]),
        ("Politics & Policy", ["politics", "political", "policy", "campaign", "democrat", "republican", "congress", "senator", "activist", "advocacy", "governance"]),
        ("Media & Journalism", ["journalist", "reporter", "editor", "media", "news", "writer", "author", "podcast", "broadcasting", "correspondent"]),
        ("Arts & Entertainment", ["artist", "music", "actor", "actress", "filmmaker", "designer", "creative", "entertainment", "comedy", "writer", "theater"]),
        ("Sports & Fitness", ["sports", "athlete", "fitness", "coach", "training", "marathon", "olympics", "basketball", "football", "soccer"]),
        ("Health & Medicine", ["doctor", "medicine", "health", "medical", "nurse", "biotech", "pharma", "wellness", "clinical", "surgery"]),
    ]

    text = " ".join(bio.lower() for bio in bios)

    best_group = None
    best_score = 0
    for group_name, keywords in keyword_groups:
        score = sum(1 for kw in keywords if kw in text)
        if score > best_score:
            best_score = score
            best_group = group_name

    if best_score >= 2:
        return best_group

    # Location detection
    location_patterns = [
        ("Bay Area", ["bay area", "san francisco", "silicon valley", "oakland", "berkeley", "palo alto", "sf ", "sf.", "san jose"]),
        ("New York", ["new york", "nyc ", "brooklyn", "manhattan", "queens", "bronx"]),
        ("London", ["london", "uk ", "british", "england"]),
        ("Los Angeles", ["los angeles", "la ", "hollywood", "beverly hills", "santa monica"]),
        ("Washington DC", ["washington", "dc ", "d.c.", "capitol", "potomac"]),
    ]

    best_location = None
    best_loc_score = 0
    for loc_name, patterns in location_patterns:
        score = sum(1 for p in patterns if p in text)
        if score > best_loc_score:
            best_loc_score = score
            best_location = loc_name

    if best_loc_score >= 2:
        return f"{best_location} Interest Group"

    return "Interest Group"


# ---------------------------------------------------------------------------
# Batch naming
# ---------------------------------------------------------------------------

def name_all_clusters(
    cache_dir: str | Path = Path("data/enrichment"),
    dry_run: bool = False,
) -> dict[int, str]:
    """Name all clusters by calling LLM (or rule-based) for each cluster.

    Parameters
    ----------
    cache_dir : str | Path
        Path to data/enrichment directory containing {username}.json files.
    dry_run : bool
        If True, load cache files and compute names but do NOT write back.
        If False, write cluster_name field to all member cache files.

    Returns
    -------
    dict[int, str]
        Mapping from cluster_id to the assigned cluster_name.
    """
    cache_dir = Path(cache_dir)

    # Collect all cluster IDs and their central members
    if not cache_dir.exists():
        logger.warning("Cache directory %s does not exist", cache_dir)
        if dry_run:
            return {}
        raise FileNotFoundError(f"Cache directory {cache_dir} does not exist")

    cluster_members: dict[int, list[dict]] = {}  # cluster_id -> list of account dicts
    for fpath in sorted(cache_dir.glob("*.json")):
        if fpath.stem in ("suspended", "protected", "errors"):
            continue
        try:
            d = json.load(open(fpath))
        except Exception as e:
            logger.warning("Could not load %s: %s", fpath, e)
            continue

        cid = d.get("cluster_id")
        if cid is None:
            continue

        if cid not in cluster_members:
            cluster_members[cid] = []
        cluster_members[cid].append(d)

    if not cluster_members:
        logger.warning("No cluster_id fields found in cache files")
        return {}

    logger.info("Found %d clusters across %d accounts", len(cluster_members), sum(len(v) for v in cluster_members.values()))

    # Name each cluster
    cluster_names: dict[int, str] = {}

    for cid, accounts in sorted(cluster_members.items()):
        # Get central members (up to 5 from cluster's central_member_usernames)
        central_usernames: list[str] = []
        for acct in accounts:
            central = acct.get("central_member_usernames", [])
            if central:
                central_usernames = list(central)[:5]
                break

        # Load bios
        bios_text = _get_bios_text(central_usernames, cache_dir)
        bios_list = [line[2:].strip() for line in bios_text.split("\n") if line.startswith("- ")]

        if not bios_list:
            logger.warning("Cluster %d has no bios for central members; using rule-based fallback", cid)
            name = rule_based_name([])
        else:
            name = name_cluster(bios_list)

        cluster_names[cid] = name
        logger.info("Cluster %d -> '%s'", cid, name)

    # Write back to cache files (unless dry_run)
    if not dry_run:
        for cid, name in cluster_names.items():
            for acct in cluster_members[cid]:
                acct["cluster_name"] = name
                uname = acct.get("username")
                if uname:
                    out_path = cache_dir / f"{uname}.json"
                    json.dump(acct, open(out_path, "w"), indent=2)
        logger.info("Updated %d cache files with cluster_name", sum(len(v) for v in cluster_members.values()))
    else:
        logger.info("dry_run=True — cache files not modified")

    return cluster_names
