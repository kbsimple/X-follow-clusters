# Quick Task 260412-gs4: Update enrichment to run for all accounts - Context

**Gathered:** 2026-04-12
**Status:** Ready for planning

<domain>
## Task Boundary

Update the enrichment logic to run for all accounts, not just accounts with missing information in their profiles.

</domain>

<decisions>
## Implementation Decisions

### Cache Handling
- **Overwrite all**: Re-enrich ALL accounts, overwriting existing cache files. No skipping based on existing cache.

### Module Scope
- **src/enrich/enrich.py**: Change the main enrichment module, not just the test driver. This affects the full enrichment pipeline.

### Sample Size
- **Configurable limit**: Add a parameter (e.g., `--limit` or `max_accounts`) to control how many accounts to process. Allows testing with small batches or running full enrichment.

### Claude's Discretion
- Exact parameter name for the configurable limit
- Whether to add progress tracking/estimates for large batches
- How to handle rate limiting visibility

</decisions>

<specifics>
## Specific Ideas

- User wants to re-enrich all accounts from scratch
- Main module (enrich.py) should be updated, not just test script
- Need ability to limit batch size for testing purposes

</specifics>

<canonical_refs>
## Canonical References

No external specs — requirements fully captured in decisions above

</canonical_refs>