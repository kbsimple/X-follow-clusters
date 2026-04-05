"""Cluster module: embedding + semi-supervised K-Means clustering."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from src.cluster.embed import (
    ClusterResult,
    cluster_all,
    compute_clusters,
    compute_silhouette_scores,
    embed_accounts,
    generate_size_histogram,
    get_text_for_embedding,
    load_seed_embeddings,
)

__all__ = [
    "ClusterResult",
    "cluster_all",
    "compute_clusters",
    "compute_silhouette_scores",
    "embed_accounts",
    "generate_size_histogram",
    "get_text_for_embedding",
    "load_seed_embeddings",
]
