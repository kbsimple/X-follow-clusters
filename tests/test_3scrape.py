"""Tests for Phase 8 3scrape modules."""

import pytest


def test_entities_module_import():
    from src.scrape.entities import extract_entities, EntityResult
    assert callable(extract_entities)
    assert EntityResult is not None


def test_link_follower_module_import():
    from src.scrape.link_follower import follow_account_links, LinkFollowResult
    assert callable(follow_account_links)
    assert LinkFollowResult is not None


def test_google_lookup_module_import():
    from src.scrape.google_lookup import google_lookup_account, GoogleLookupResult
    assert callable(google_lookup_account)
    assert GoogleLookupResult is not None


def test_scrape_init_exports_3scrape():
    from src.scrape import (
        extract_entities,
        EntityResult,
        follow_account_links,
        LinkFollowResult,
        google_lookup_account,
        GoogleLookupResult,
    )
    assert callable(extract_entities)
    assert callable(follow_account_links)
    assert callable(google_lookup_account)


def test_entity_result_dataclass():
    from src.scrape.entities import EntityResult
    result = EntityResult(
        username="testuser",
        orgs=["DeepMind"],
        locs=["London"],
        titles=["Research Scientist"],
    )
    assert result.username == "testuser"
    assert result.orgs == ["DeepMind"]
    assert result.locs == ["London"]
    assert result.titles == ["Research Scientist"]


def test_link_follow_result_dataclass():
    from src.scrape.link_follower import LinkFollowResult
    result = LinkFollowResult(
        username="testuser",
        external_bio="Test bio content",
        links_followed=2,
        pages_fetched=3,
    )
    assert result.username == "testuser"
    assert result.external_bio == "Test bio content"
    assert result.links_followed == 2
    assert result.pages_fetched == 3


def test_google_lookup_result_dataclass():
    from src.scrape.google_lookup import GoogleLookupResult
    result = GoogleLookupResult(
        username="testuser",
        result_title="Test Title",
        result_snippet="Test snippet text",
        search_count=5,
    )
    assert result.username == "testuser"
    assert result.result_title == "Test Title"
    assert result.result_snippet == "Test snippet text"
    assert result.search_count == 5


def test_get_text_for_embedding_with_entities():
    from src.cluster.embed import get_text_for_embedding
    account = {
        "description": "AI researcher",
        "location": "London",
        "professional_category": "Engineering",
        "pinned_tweet_text": "Excited about AGI!",
        "entity_orgs": ["DeepMind", "Google"],
        "entity_locs": ["London", "Mountain View"],
        "entity_titles": ["Research Scientist"],
    }
    text = get_text_for_embedding(account)
    assert "AI researcher" in text
    assert "London" in text
    assert "Engineering" in text
    assert "Org: DeepMind, Google" in text
    assert "Loc: London, Mountain View" in text
    assert "Title: Research Scientist" in text
    # Check separator pattern
    assert " | " in text


def test_get_text_for_embedding_without_entities():
    from src.cluster.embed import get_text_for_embedding
    account = {
        "description": "AI researcher",
        "location": "London",
        "professional_category": "Engineering",
        "pinned_tweet_text": "Excited about AGI!",
        # No entity fields
    }
    text = get_text_for_embedding(account)
    assert "AI researcher" in text
    assert "London" in text
    assert "Engineering" in text
    # Should not contain entity markers
    assert "Org:" not in text
    assert "Loc:" not in text
    assert "Title:" not in text


def test_scrape_result_has_3scrape_fields():
    from src.scrape import ScrapeResult
    result = ScrapeResult(
        total=100,
        scraped=50,
        skipped=30,
        failed=10,
        blocked=5,
        link_followed=20,
        entities_extracted=80,
        google_looked_up=10,
    )
    assert result.link_followed == 20
    assert result.entities_extracted == 80
    assert result.google_looked_up == 10


def test_find_bio_links():
    from src.scrape.link_follower import _find_bio_links
    from bs4 import BeautifulSoup
    html = """
    <html><body>
    <a href="/about">About Me</a>
    <a href="https://example.com/bio">My Bio</a>
    <a href="https://linkedin.com/in/test">LinkedIn</a>
    <a href="https://x.com/test">X Profile</a>
    </body></html>
    """
    soup = BeautifulSoup(html, "lxml")
    links = _find_bio_links(soup, "https://example.com")
    # LinkedIn should be skipped
    assert not any("linkedin" in l.lower() for l in links)
    assert not any("x.com" in l for l in links)
    # About/bio links should be included
    assert len(links) >= 2


def test_google_lookup_account_requires_no_bio_no_website(tmp_path):
    from src.scrape.google_lookup import google_lookup_account
    import json

    # Create a test cache file with bio but no website
    cache_file = tmp_path / "testuser.json"
    cache_file.write_text(json.dumps({
        "username": "testuser",
        "description": "I have a bio",  # bio present
        "website": "",  # no website
    }))

    result = google_lookup_account("testuser", cache_dir=tmp_path)
    # Should return None because bio is present (gate condition per D-06)
    assert result is None or result.result_title is None

    # Update to have neither bio nor website
    cache_file.write_text(json.dumps({
        "username": "testuser",
        "description": "",
        "website": "",
    }))

    result = google_lookup_account("testuser", cache_dir=tmp_path)
    # If SERPAPI_KEY not set, should still return a result (with None title)
    assert result is not None


def test_follow_account_links_requires_website_no_bio(tmp_path):
    from src.scrape.link_follower import follow_account_links
    import json

    # Create a test cache file with bio (length >= 10) and website
    cache_file = tmp_path / "testuser.json"
    cache_file.write_text(json.dumps({
        "username": "testuser",
        "description": "I have a substantial bio that is definitely longer than 10 chars",
        "website": "https://example.com",
    }))

    result = follow_account_links("testuser", cache_dir=tmp_path)
    # Should return None because bio is long enough (per D-10 gate)
    assert result is None or result.external_bio is None

    # Update to have no bio and website
    cache_file.write_text(json.dumps({
        "username": "testuser",
        "description": "",
        "website": "https://example.com",
    }))

    result = follow_account_links("testuser", cache_dir=tmp_path)
    # Should attempt link following (but may return None if URL unreachable)
    assert result is not None