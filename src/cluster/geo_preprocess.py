"""Geographic location preprocessing.

Normalizes location strings before embedding by:
- Expanding airport codes (PVD → Providence Rhode Island)
- Expanding state abbreviations (RI → Rhode Island)
- Extracting city/state from complex strings
- Adding geographic context for known patterns
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

# Cache for loaded airport codes
_airport_codes_cache: dict[str, str] | None = None


def load_airport_codes(config_path: Path | None = None) -> dict[str, str]:
    """Load airport codes from YAML config.

    Parameters
    ----------
    config_path : Path | None
        Path to airport_codes.yaml. Defaults to config/airport_codes.yaml.

    Returns
    -------
    dict[str, str]
        Mapping from IATA code to location string.
    """
    global _airport_codes_cache

    if _airport_codes_cache is not None:
        return _airport_codes_cache

    if config_path is None:
        config_path = Path("config/airport_codes.yaml")

    if not config_path.exists():
        logger.warning("Airport codes config not found: %s", config_path)
        return {}

    with open(config_path) as f:
        data = yaml.safe_load(f) or {}

    _airport_codes_cache = data
    logger.debug("Loaded %d airport codes from %s", len(data), config_path)
    return data


# Backwards compatibility - property-like access for module-level usage
def _get_airport_codes() -> dict[str, str]:
    return load_airport_codes()


# State abbreviations to full names
STATE_ABBREVS = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "Washington DC",
}

# City aliases and common misspellings
CITY_ALIASES = {
    "NYC": "New York City",
    "NY": "New York",
    "SF": "San Francisco",
    "LA": "Los Angeles",
    "SD": "San Diego",
    "DC": "Washington DC",
    "PVD": "Providence Rhode Island",
    "BOS": "Boston",
    "SEA": "Seattle",
    "ATX": "Austin Texas",
    "PDX": "Portland Oregon",
}

# Common prefixes/suffixes to strip when extracting location
NOISE_PATTERNS = [
    r"\bthe\s+",  # "The juice truck" -> "juice truck"
    r"\btruck\b",
    r"\bmobile\b",
    r"\bworldwide\b",
    r"\bglobal\b",
    r"\beverywhere\b",
    r"\binternet\b",
    r"\bcyberspace\b",
]


def extract_airport_codes(text: str) -> list[str]:
    """Find and extract 3-letter airport codes from text.

    Only matches codes that appear to be intentional airport codes,
    not city name fragments. Heuristics:
    - All caps in original text (e.g., "flying from PVD to LAX")
    - Or codes that don't conflict with common words
    """
    airport_codes = _get_airport_codes()

    # Find potential 3-letter codes (all caps, word boundaries)
    # Use negative lookahead to avoid matching words followed by lowercase
    # (e.g., "SAN Francisco" -> "SAN" followed by " Francisco" should NOT match)
    pattern = r'\b([A-Z]{3})(?!\s*[a-z])'
    matches = re.findall(pattern, text)

    expansions = []
    for code in matches:
        if code in airport_codes:
            expansions.append(airport_codes[code])

    return expansions


def expand_state_abbrev(text: str) -> str:
    """Expand state abbreviations to full names."""
    result = text

    # Match state abbreviations as standalone or after comma
    for abbrev, full_name in STATE_ABBREVS.items():
        # Match ", RI" or " RI" but not inside words
        pattern = rf',?\s+{abbrev}\b'
        if re.search(pattern, text, re.IGNORECASE):
            result = re.sub(pattern, f", {full_name}", result, flags=re.IGNORECASE)

    return result


def expand_city_aliases(text: str) -> str:
    """Expand common city abbreviations."""
    result = text

    for alias, full_name in CITY_ALIASES.items():
        # Match standalone alias with word boundaries
        # Use negative lookbehind/lookahead to avoid partial matches
        pattern = rf'(?<![A-Za-z]){re.escape(alias)}(?![A-Za-z])'
        if re.search(pattern, text, re.IGNORECASE):
            result = re.sub(pattern, full_name, result, flags=re.IGNORECASE)

    return result


def extract_location_signal(text: str) -> str:
    """Extract the geographic signal from a location string.

    This is the main entry point. It:
    1. Expands airport codes
    2. Expands state abbreviations
    3. Expands city aliases
    4. Strips noise words
    5. Returns a normalized location string
    """
    if not text:
        return ""

    original = text

    # Step 1: Check for airport codes first (high confidence)
    airport_expansions = extract_airport_codes(text)

    # Step 2: Expand state abbreviations
    expanded = expand_state_abbrev(text)

    # Step 3: Expand city aliases
    expanded = expand_city_aliases(expanded)

    # Step 4: Strip noise words
    cleaned = expanded
    for pattern in NOISE_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

    # Step 5: Combine with airport expansions
    if airport_expansions:
        # Prepend airport expansions for stronger signal
        cleaned = " | ".join(airport_expansions) + " | " + cleaned

    # Clean up extra whitespace and punctuation
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    cleaned = re.sub(r'\|\s*\|', '|', cleaned)  # Remove empty segments
    cleaned = re.sub(r'^\s*\|\s*', '', cleaned)  # Remove leading pipe

    return cleaned if cleaned else original


def preprocess_location_for_embedding(location: str, entity_locs: list[str] | None = None) -> str:
    """Preprocess a location string for geographic embedding.

    Combines location field with entity_locs and normalizes the result.

    Parameters
    ----------
    location : str
        The location field from the account profile.
    entity_locs : list[str] | None
        Additional location entities extracted from bio.

    Returns
    -------
    str
        Normalized location string ready for embedding.
    """
    parts = []

    if location:
        processed = extract_location_signal(location)
        if processed:
            parts.append(processed)

    if entity_locs:
        for loc in entity_locs:
            processed = extract_location_signal(loc)
            if processed:
                parts.append(processed)

    result = " | ".join(parts)

    # If we couldn't extract anything, fall back to original
    if not result and location:
        return location

    return result


if __name__ == "__main__":
    # Test cases
    test_cases = [
        "PVD",
        "Providence, RI",
        "The juice truck, Providence RI",
        "North Kingstown, RI",
        "San Francisco, CA",
        "SFO",
        "NYC",
        "Washington DC",
        "LAX",
        "Denver, CO",
        "Boston, MA",
        "Worldwide",
        "Internet",
    ]

    print("Location Preprocessing Test")
    print("=" * 70)
    for loc in test_cases:
        processed = extract_location_signal(loc)
        print(f"{loc:<35} → {processed}")