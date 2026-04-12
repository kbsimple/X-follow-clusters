"""External link follower for extracting biography content from personal websites.

Provides:
- LinkFollowResult: dataclass with external_bio, links_followed, pages_fetched
- follow_account_links(): fetches homepage + about/bio pages, extracts bio text

Usage:
    from src.scrape.link_follower import follow_account_links, LinkFollowResult

    result = follow_account_links("someaccount", cache_dir="data/enrichment")
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from curl_cffi import requests as curl_requests
except ImportError:
    curl_requests = None  # type: ignore


@dataclass
class LinkFollowResult:
    """Result of following external links for an account.

    Attributes:
        username: Account username.
        external_bio: Combined text from homepage and about/bio pages.
        links_followed: Number of about/bio links followed.
        pages_fetched: Total pages successfully fetched.
    """

    username: str
    external_bio: str | None
    links_followed: int
    pages_fetched: int


def _find_bio_links(soup: Any, base_url: str) -> list[str]:
    """Find about/bio/biography links on a homepage.

    Looks for anchor tags where link text or href contains about/bio/me/profile.
    Returns up to 3 links, resolved to absolute URLs.
    Skips LinkedIn per D-13.
    """
    from urllib.parse import urljoin

    candidates: list[tuple[str, str]] = []  # (url, text)

    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        text = a.get_text(strip=True).lower()
        # Skip LinkedIn links (per D-13)
        if "linkedin.com" in href.lower():
            continue
        # Skip x.com links
        if "x.com" in href or "twitter.com" in href:
            continue
        # Resolve relative URLs
        full_url = urljoin(base_url, href)
        # Only external http/https links
        if not full_url.startswith("http"):
            continue
        # Check if link text or href suggests about/bio page
        if any(kw in text or kw in href.lower() for kw in ["about", "bio", "me", "profile", "/"]):
            candidates.append((full_url, text))

    # Dedupe by URL, return up to 3
    seen = set()
    result = []
    for url, text in candidates:
        if url not in seen:
            seen.add(url)
            result.append(url)
            if len(result) >= 3:
                break
    return result


def _fetch_page_text(session: Any, url: str, timeout: float = 10.0) -> str | None:
    """Fetch a page and extract visible text content."""
    from bs4 import BeautifulSoup

    try:
        response = session.get(url, timeout=timeout)
        if response.status_code != 200:
            return None
        soup = BeautifulSoup(response.text, "lxml")
        # Remove script/style tags
        for tag in soup(["script", "style", "nav", "header", "footer"]):
            tag.decompose()
        # Get main content or body
        main = soup.find("main") or soup.find("body")
        if main:
            text = main.get_text(separator=" ", strip=True)
        else:
            text = soup.get_text(separator=" ", strip=True)
        # Collapse whitespace
        text = " ".join(text.split())
        return text if len(text) > 50 else None
    except Exception:
        return None


def follow_account_links(
    username: str,
    cache_dir: Path | str = Path("data/enrichment"),
    max_account_time: float = 30.0,
    per_request_timeout: float = 10.0,
) -> LinkFollowResult | None:
    """Fetch homepage and follow about/bio links for an account.

    Per D-10: trigger only for accounts with website set but bio empty (len < 10 chars).
    Per D-11: fetch homepage AND follow any about/bio links found.
    Per D-12: 10s timeout per request, 30s max total per account.
    Per D-13: skip LinkedIn links.
    Per D-14: store external_bio in cache.

    Args:
        username: Account username.
        cache_dir: Directory containing {username}.json cache files.
        max_account_time: Maximum seconds to spend on link following per account (default 30.0).
        per_request_timeout: Timeout per HTTP request (default 10.0).

    Returns:
        LinkFollowResult if website was found, None otherwise.
    """
    cache_dir = Path(cache_dir)
    cache_path = cache_dir / f"{username}.json"

    if not cache_path.exists():
        return None

    with open(cache_path, encoding="utf-8") as f:
        account = json.load(f)

    website = account.get("website", "")
    bio = account.get("bio") or account.get("description", "")

    # Per D-10: only follow links if website exists AND bio is empty or very short
    if not website or len(bio) >= 10:
        return None

    account_start = time.monotonic()

    # Create curl_cffi session with browser impersonation
    if curl_requests is None:
        return None
    session = curl_requests.Session(impersonate="chrome")

    pages_texts: list[str] = []
    bio_links: list[str] = []

    # 1. Fetch homepage (per D-11)
    homepage_text = _fetch_page_text(session, website, timeout=per_request_timeout)
    if homepage_text:
        pages_texts.append(homepage_text)

    elapsed = time.monotonic() - account_start
    if elapsed >= max_account_time:
        # Time exceeded — stop here
        pass
    else:
        # 2. Parse homepage for about/bio links
        try:
            response = session.get(website, timeout=per_request_timeout)
            if response.status_code == 200:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(response.text, "lxml")
                bio_links = _find_bio_links(soup, website)

                for link in bio_links:
                    if time.monotonic() - account_start >= max_account_time:
                        break
                    link_text = _fetch_page_text(session, link, timeout=per_request_timeout)
                    if link_text:
                        pages_texts.append(link_text)
        except Exception:
            pass

    if not pages_texts:
        return LinkFollowResult(
            username=username,
            external_bio=None,
            links_followed=len(bio_links),
            pages_fetched=0,
        )

    # Combine all text with separator
    combined = " || ".join(pages_texts)

    # Truncate to avoid huge text (cap at 2000 chars)
    if len(combined) > 2000:
        combined = combined[:2000]

    # Write external_bio to cache (per D-14)
    account["external_bio"] = combined
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(account, f, indent=2)

    return LinkFollowResult(
        username=username,
        external_bio=combined,
        links_followed=len(bio_links),
        pages_fetched=len(pages_texts),
    )


__all__ = ["follow_account_links", "LinkFollowResult", "_find_bio_links", "_fetch_page_text"]