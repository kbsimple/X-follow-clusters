"""X API profile enrichment module.

Exports:
    enrich_all: Main orchestration function
    EnrichmentResult: Result dataclass
    XEnrichmentClient: API client wrapper
    ExponentialBackoff: Rate limit backoff handler
    RateLimitError: Rate limit exception
    CacheWriteError: Cache write failure exception
"""

from src.enrich.enrich import enrich_all, EnrichmentResult
from src.enrich.api_client import XEnrichmentClient, CacheWriteError, EnrichmentResponse
from src.enrich.rate_limiter import ExponentialBackoff, RateLimitError

__all__ = [
    "enrich_all",
    "EnrichmentResult",
    "XEnrichmentClient",
    "CacheWriteError",
    "EnrichmentResponse",
    "ExponentialBackoff",
    "RateLimitError",
]
