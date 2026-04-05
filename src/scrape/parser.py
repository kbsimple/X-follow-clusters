"""BeautifulSoup field extraction for X profile pages.

Extracts supplemental profile fields not available via the X API:
- bio, location, website, join_date
- professional_category (via __NEXT_DATA__ JSON fallback)
- pinned_tweet_text (first tweet in timeline)
- profile_banner_url

Usage:
    from src.scrape.parser import parse_profile_fields

    soup = BeautifulSoup(response.text, "lxml")
    fields = parse_profile_fields(soup)
"""

from __future__ import annotations

import json
import logging
from typing import Any

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def parse_profile_fields(soup: BeautifulSoup) -> dict[str, Any]:
    """Extract all supplemental profile fields from a parsed X profile page.

    Args:
        soup: BeautifulSoup object parsed with lxml from profile HTML.

    Returns:
        Dict with keys: bio, location, website, join_date,
        professional_category, pinned_tweet_text, profile_banner_url.
        Values are None if field is not found.
    """
    return {
        "bio": extract_bio(soup),
        "location": extract_location(soup),
        "website": extract_website(soup),
        "join_date": extract_join_date(soup),
        "professional_category": extract_professional_category(soup),
        "pinned_tweet_text": extract_pinned_tweet(soup),
        "profile_banner_url": extract_banner(soup),
    }


def extract_bio(soup: BeautifulSoup) -> str | None:
    """Extract bio/description text from profile page."""
    el = soup.select_one('div[data-testid="UserDescription"]')
    if el:
        text = el.get_text(strip=True)
        return text if text else None
    return None


def extract_location(soup: BeautifulSoup) -> str | None:
    """Extract location text from profile page."""
    el = soup.select_one('span[data-testid="UserLocation"]')
    if el:
        text = el.get_text(strip=True)
        return text if text else None
    return None


def extract_website(soup: BeautifulSoup) -> str | None:
    """Extract website URL from profile page."""
    el = soup.select_one('a[data-testid="UserUrl"]')
    if el:
        return el.get("href")
    return None


def extract_join_date(soup: BeautifulSoup) -> str | None:
    """Extract join date text from profile page."""
    el = soup.select_one('span[data-testid="UserJoinDate"]')
    if el:
        text = el.get_text(strip=True)
        return text if text else None
    return None


def extract_professional_category(soup: BeautifulSoup) -> str | None:
    """Extract professional category from profile page.

    Tries three strategies in order:
    1. data-testid="UserProfessionalCategory" span
    2. __NEXT_DATA__ JSON -> extendedProfile.category.description.label
    3. Scan spans for text containing "Professional" under 100 chars
    """
    # Strategy 1: Direct selector
    el = soup.select_one('[data-testid="UserProfessionalCategory"]')
    if el:
        text = el.get_text(strip=True)
        if text:
            return text

    # Strategy 2: __NEXT_DATA__ JSON fallback
    script = soup.select_one('script[id="__NEXT_DATA__"]')
    if script:
        try:
            data = json.loads(script.string)
            # Navigate to extendedProfile.category.description.label
            result = (
                data.get("props", {})
                .get("pageProps", {})
                .get("user", {})
                .get("result", {})
            )
            category = (
                result.get("legacy", {})
                .get("extensibleProfile", {})
                .get("category", {})
                .get("description", {})
                .get("label")
            )
            if category:
                return category
        except (json.JSONDecodeError, AttributeError, KeyError, TypeError) as e:
            logger.debug("Could not parse __NEXT_DATA__ for professional_category: %s", e)

    # Strategy 3: Scan spans for "Professional" text
    for span in soup.select("span"):
        text = span.get_text(strip=True)
        if "Professional" in text and len(text) < 100:
            return text

    return None


def extract_pinned_tweet(soup: BeautifulSoup) -> str | None:
    """Extract the first tweet's text as a proxy for pinned tweet.

    X does not mark pinned tweets distinctly in HTML. We take the first
    tweet in the timeline as a reasonable proxy. If the account has a
    pinned tweet, it typically appears first in the timeline.
    """
    articles = soup.select('article[data-testid="tweet"]')
    if articles:
        text_el = articles[0].select_one('[data-testid="tweetText"]')
        if text_el:
            text = text_el.get_text(strip=True)
            return text if text else None
    return None


def extract_banner(soup: BeautifulSoup) -> str | None:
    """Extract profile banner image URL."""
    img = soup.select_one('img[alt="Profile banner"]')
    if img:
        return img.get("src")
    return None
