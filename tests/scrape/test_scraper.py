"""Tests for src/scrape/scraper.py and src/scrape/parser.py."""
import pytest
from pathlib import Path
import tempfile
import json


def test_scraper_init_with_temp_cache():
    """XProfileScraper initializes with a temp cache dir."""
    from src.scrape.scraper import XProfileScraper
    with tempfile.TemporaryDirectory() as tmpdir:
        scraper = XProfileScraper(cache_dir=Path(tmpdir))
        assert scraper.cache_dir == Path(tmpdir)


def test_parser_extracts_bio():
    """parse_profile_fields extracts bio from HTML."""
    from bs4 import BeautifulSoup
    from src.scrape.parser import parse_profile_fields
    html = '<html><body><div data-testid="UserDescription">Test bio</div></body></html>'
    soup = BeautifulSoup(html, "lxml")
    fields = parse_profile_fields(soup)
    assert fields["bio"] == "Test bio"


def test_parser_returns_none_for_missing_fields():
    """parse_profile_fields returns None for fields not in HTML."""
    from bs4 import BeautifulSoup
    from src.scrape.parser import parse_profile_fields
    html = "<html><body></body></html>"
    soup = BeautifulSoup(html, "lxml")
    fields = parse_profile_fields(soup)
    assert fields["bio"] is None
    assert fields["location"] is None


def test_is_blocked_detects_empty_200():
    """is_blocked returns True for empty 200 response."""
    from src.scrape.scraper import XProfileScraper
    from unittest.mock import Mock
    with tempfile.TemporaryDirectory() as tmpdir:
        scraper = XProfileScraper(cache_dir=Path(tmpdir))
        response = Mock(status_code=200, text="", url="https://x.com/user")
        assert scraper.is_blocked(response) is True


def test_is_blocked_allows_normal_200():
    """is_blocked returns False for normal 200 response."""
    from src.scrape.scraper import XProfileScraper
    from unittest.mock import Mock
    with tempfile.TemporaryDirectory() as tmpdir:
        scraper = XProfileScraper(cache_dir=Path(tmpdir))
        response = Mock(status_code=200, text="<html><title>Profile</title></html>", url="https://x.com/user")
        assert scraper.is_blocked(response) is False
