---
name: eval-geo-clustering
description: Run geographic clustering pipeline and produce a report on efficacy, coverage, and improvement opportunities. Use when evaluating or improving geographic topic assignments.
---

# Evaluate Geographic Clustering

Run the geographic clustering pipeline and produce a report on efficacy, coverage, and improvement opportunities.

## Process

### Step 1: Clear existing geo assignments

```bash
.venv/bin/python << 'EOF'
import json
from pathlib import Path
for fpath in Path("data/enrichment").glob("*.json"):
    if fpath.stem in ("suspended", "protected", "errors"): continue
    try:
        data = json.load(open(fpath))
        data.pop("geo_clusters", None)
        data.pop("geo_confidences", None)
        json.dump(data, open(fpath, "w"), indent=2)
    except: pass
print("Cleared geo_clusters from all files")
EOF
```

### Step 2: Run geographic clustering

```bash
.venv/bin/python -m src.cluster.geo_cluster
```

### Step 3: Analyze coverage

```bash
.venv/bin/python << 'EOF'
import json
from pathlib import Path
from collections import Counter

cache_dir = Path("data/enrichment")
has_geo = 0
no_geo = []
geo_counts = Counter()

for fpath in cache_dir.glob("*.json"):
    if fpath.stem in ("suspended", "protected", "errors"):
        continue
    data = json.load(open(fpath))
    geo = data.get("geo_clusters", [])
    loc = data.get("location", "")
    if geo:
        has_geo += 1
        for g in geo:
            geo_counts[g] += 1
    elif loc:
        no_geo.append(loc)

print(f"GEOGRAPHIC CLUSTERING REPORT")
print(f"{'='*60}")
print(f"Total files: {has_geo + len(no_geo)}")
print(f"With geo assignment: {has_geo}")
print(f"Without geo (has location): {len(no_geo)}")
print(f"Coverage: {has_geo / (has_geo + len(no_geo)) * 100:.1f}%")
print(f"\nGEOGRAPHIC CLUSTERS:")
for geo, cnt in geo_counts.most_common():
    print(f"  {geo:<25} {cnt:>5} accounts")
EOF
```

### Step 4: Categorize edge cases

```bash
.venv/bin/python << 'EOF'
import json
from pathlib import Path
from collections import Counter
import re

cache_dir = Path("data/enrichment")
no_geo = []

for fpath in cache_dir.glob("*.json"):
    if fpath.stem in ("suspended", "protected", "errors"):
        continue
    data = json.load(open(fpath))
    if not data.get("geo_clusters") and data.get("location"):
        no_geo.append(data.get("location"))

# Categorize
categories = {
    "Too broad (country only)": [],
    "Non-geographic (Worldwide/Internet)": [],
    "Not in topic list": [],
    "Multi-location (LI | DC, etc.)": [],
    "Joke/fake location": [],
    "Specific city not covered": [],
    "Non-location text": [],
    "Emoji/special chars": [],
    "Other": [],
}

for loc in no_geo:
    loc_lower = loc.lower()
    if loc_lower in ("usa", "united states", "us") or re.match(r'^[A-Z]{2},?\s*(USA)?$', loc, re.I):
        categories["Too broad (country only)"].append(loc)
    elif any(x in loc_lower for x in ["worldwide", "internet", "everywhere", "global"]):
        categories["Non-geographic (Worldwide/Internet)"].append(loc)
    elif any(x in loc_lower for x in ["dallas", "atlanta", "texas", "ohio", "florida", "orlando", "houston", "oregon"]):
        categories["Not in topic list"].append(loc)
    elif "|" in loc or " and " in loc_lower:
        categories["Multi-location (LI | DC, etc.)"].append(loc)
    elif any(x in loc_lower for x in ["aintblackistan", "nowhere", "republic"]):
        categories["Joke/fake location"].append(loc)
    elif re.search(r'[➡️→]', loc):
        categories["Emoji/special chars"].append(loc)
    elif any(x in loc_lower for x in ["links:", "real estate", "broker"]):
        categories["Non-location text"].append(loc)
    elif any(x in loc_lower for x in ["mammoth", "hanford", "stonington", "gowanus"]):
        categories["Specific city not covered"].append(loc)
    else:
        categories["Other"].append(loc)

print(f"\nEDGE CASE ANALYSIS")
print(f"{'='*60}")
for cat, locs in categories.items():
    if locs:
        unique = list(set(locs))
        print(f"\n{cat}: {len(locs)} ({len(unique)} unique)")
        for loc in unique[:5]:
            print(f"  • '{loc}'")
EOF
```

### Step 5: Generate recommendations

After running the above, analyze the results and provide:

1. **Coverage Summary**: X% of accounts with location data assigned to geo clusters
2. **Cluster Distribution**: Which geographic clusters are most/least populated
3. **Improvement Opportunities**:
   - **Add topics**: Locations in "Not in topic list" that have enough volume
   - **Combine topics**: Locations that should be merged (e.g., Dallas + Texas)
   - **Preprocessing fixes**: Emoji handling, multi-location parsing
   - **Threshold tuning**: If too many false positives/negatives

4. **Example improvements with evidence**:
   - "Add 'Texas' topic: 18 accounts with Dallas/Houston/Austin"
   - "Fix multi-location parsing: 'LI | DC' affects 4 accounts"

### Step 6: Present final report

Format as:

```
## Geographic Clustering Evaluation Report

### Coverage
- X/Y accounts assigned (Z%)
- N geographic clusters active

### Cluster Distribution
| Cluster | Accounts |
|---------|----------|
| ...     | ...      |

### Edge Cases
| Category | Count | Examples |
|-----------|-------|----------|
| ...       | ...   | ...      |

### Recommendations
1. [Specific improvement with evidence]
2. [Another improvement with evidence]

### Next Steps
- [Actionable items to improve coverage]
```

## Files Involved

- `config/seed_geographies.yaml` — Geographic topic definitions
- `config/airport_codes.yaml` — Airport IATA code mappings
- `src/cluster/geo_cluster.py` — Clustering module
- `src/cluster/geo_preprocess.py` — Location preprocessing
- `data/enrichment/*.json` — Account cache files

## Configuration

- **Threshold**: 0.55 (minimum similarity to assign geo cluster)
- **Multi-assignment**: Yes (accounts can be in multiple geo clusters)
- **Preprocessing**: Airport codes, state abbreviations, city aliases