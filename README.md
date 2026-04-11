# X Following Organizer

A Python tool that transforms a flat X (Twitter) following list into organized, named X API lists. It reads `following.js` from an X data archive export, enriches each account with rich profile data via the X API and profile page scraping, clusters followers using NLP sentence embeddings, and creates those clusters as native X API lists — all with a human review step before anything is posted.

## What it does

1. **Parses** `following.js` from your X data archive export
2. **Enriches** each account with bio, location, follower metrics, and more via the X API
3. **Scrapes** supplemental profile fields (website, join date, professional category) for accounts missing data
4. **Clusters** accounts using sentence-transformer embeddings + semi-supervised K-Means
5. **Names** clusters via LLM (OpenAI GPT-4o-mini or Anthropic Claude) or rule-based fallback
6. **Reviews** clusters interactively — you approve, merge, split, or defer
7. **Creates** native X API lists from approved clusters and exports data to CSV/Parquet

The workflow is semi-automated: the tool proposes clusters, you review and refine them, then the tool creates the lists. Full automation is available after you've established trust.

## Prerequisites

- **Python >= 3.9**
- **X API credentials** — not yet configured; see [Setup](#setup) below
- **X data archive** — request your data at [X (Twitter) data archive](https://x.com/settings/your_x_data)

## Setup

### 1. Clone and install dependencies

```bash
git clone <repository-url>
cd x-api
python -m venv .venv
source .venv/bin/activate  # on Windows: .venv\Scripts\activate
pip install -e .
```

### 2. Configure X API credentials

Copy the example env file and fill in your credentials from [developer.x.com](https://developer.x.com/en/docs/twitter-api/twitter-api-labs):

```bash
cp .env.example .env
```

Edit `.env`:

```env
X_API_KEY=your_api_key
X_API_SECRET=your_api_secret
X_ACCESS_TOKEN=your_access_token
X_ACCESS_TOKEN_SECRET=your_access_token_secret
X_BEARER_TOKEN=your_bearer_token  # optional
```

Verify credentials are working:

```bash
python -c "from src.auth import get_auth, verify_credentials; verify_credentials(get_auth())"
```

### 3. Place your following.js

Copy your X data archive's `following.js` into the `data/` directory:

```bash
cp /path/to/your/X-data-archive/data/following.js data/following.js
```

### 4. (Optional) Configure seed accounts

Edit `config/seed_accounts.yaml` with real usernames from your following list. These anchor the semi-supervised clustering. Run Phase 2 first to populate the enrichment cache, then replace placeholders with actual accounts from `data/enrichment/`.

## Usage

Run each phase sequentially. Each phase is restartable — it skips accounts already processed.

### Phase 1 — Parse the archive

```bash
x-parse [data/following.js]
```

Parses `following.js`, prints total accounts and a sample. Defaults to `data/following.js` if no path given.

### Phase 2 — Enrich via X API

```bash
python -m src.enrich --input data/following.js --output data/enrichment
```

Fetches rich profile data for all accounts, caches to `data/enrichment/{account_id}.json`. **Requires X API credentials.**

### Phase 3 — Scrape supplemental fields

```bash
python -m src.scrape --input data/enrichment --output data/enrichment
```

Scrapes accounts flagged `needs_scraping=True`. Honours `Crawl-delay: 1` from robots.txt with random 2–5s delays.

### Phase 4 — Cluster accounts

```bash
python -m src.cluster
```

Embeds bios using sentence-transformers (`all-MiniLM-L6-v2`), runs semi-supervised K-Means, names clusters via LLM or rule-based fallback. Writes cluster assignments back to cache files.

**Requires:** Phase 2 (enrichment) and `config/seed_accounts.yaml` populated with real usernames.

**Optional:** Set `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` for LLM cluster naming.

### Phase 5 — Review clusters

```bash
python -m src.review
```

Interactive CLI (via `questionary` + `rich`) for reviewing, merging, splitting, renaming, and approving clusters before list creation. Approved clusters are marked `approved: true` in cache metadata.

### Phase 6 — Create X API lists

```bash
python -m src.list
```

Creates native X lists from approved clusters, adds members in chunks. Also exports to `data/clusters/` as CSV and Parquet. **Requires X API credentials.**

## Pipeline overview

```
following.js → parse → enrich → scrape → cluster → review → X API lists
                    ↓          ↓
                 cache      cache
```

## Configuration

### Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `X_API_KEY` | Yes | X API Consumer Key |
| `X_API_SECRET` | Yes | X API Consumer Secret |
| `X_ACCESS_TOKEN` | Yes | OAuth 1.0a Access Token |
| `X_ACCESS_TOKEN_SECRET` | Yes | OAuth 1.0a Access Token Secret |
| `X_BEARER_TOKEN` | No | Bearer token for app-only auth |
| `OPENAI_API_KEY` | No | LLM cluster naming (GPT-4o-mini) |
| `ANTHROPIC_API_KEY` | No | LLM cluster naming (Claude Haiku) |

### Seed accounts (`config/seed_accounts.yaml`)

Categories and example usernames that anchor the semi-supervised clustering. Replace placeholders with real accounts from your `data/enrichment/` cache after Phase 2.

## Project structure

```
x-api/
├── src/
│   ├── auth/           # X API credential loading and verification
│   ├── parse/          # following.js parser
│   ├── enrich/         # X API enrichment client and orchestration
│   ├── scrape/         # Profile page scraping (curl_cffi + BeautifulSoup)
│   ├── cluster/        # Embedding, K-Means clustering, LLM naming
│   ├── review/         # Interactive cluster review CLI
│   └── list/           # X API list creation and data export
├── data/
│   ├── following.js     # Input: X data archive following file
│   ├── enrichment/      # Cache: per-account JSON files from Phases 2 & 3
│   └── clusters/       # Output: CSV and Parquet from Phase 6
├── config/
│   └── seed_accounts.yaml  # Seed accounts for semi-supervised clustering
├── tests/              # Unit tests
├── pyproject.toml      # Package configuration and dependencies
└── README.md
```

## Python API

```python
from src.enrich import enrich_all
from src.scrape import scrape_all
from src.cluster import cluster_all
from src.review import review_all  # interactive
from src.list import create_lists_from_clusters

result = enrich_all("data/following.js", "data/enrichment")
scrape_result = scrape_all("data/enrichment")
cluster_result = cluster_all("data/enrichment")
# review_all()  # interactive — approve, merge, split clusters
list_result = create_lists_from_clusters("data/enrichment", "data/clusters")
```
