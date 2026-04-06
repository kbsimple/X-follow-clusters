from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
import json, uuid, os

APPROVAL_REGISTRY_PATH = Path("data/clusters/approved.json")
AUTOMATION_ROUNDS = int(os.environ.get("REVIEW_AUTOMATION_ROUNDS", 2))


@dataclass
class ApprovalRegistry:
    """Approval registry for tracking cluster review decisions across sessions.

    Attributes
    ----------
    version : int
        Schema version (currently 1).
    session_id : str
        Unique UUID for this review session.
    rounds_completed : int
        Count of times user has approved a NEW cluster (not re-approvals).
        Incremented only when cluster_id is not already in clusters["approved"].
    automation_offered : bool
        Whether full automation mode has been offered to the user.
    automation_enabled : bool
        Whether full automation mode is active.
    batch_approved_count : int
        Number of clusters approved via batch action.
    timestamp : str
        ISO timestamp of last registry save.
    clusters : dict
        Mapping with keys "approved", "deferred", "rejected".
        Each value is a list of cluster decision dicts.
    """
    version: int = 1
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    rounds_completed: int = 0
    automation_offered: bool = False
    automation_enabled: bool = False
    batch_approved_count: int = 0
    timestamp: str = ""
    clusters: dict = field(default_factory=lambda: {
        "approved": [],   # {cluster_id, cluster_name, size, silhouette, members, round_approved}
        "deferred": [],   # {cluster_id, cluster_name, size, silhouette, members}
        "rejected": []    # {cluster_id, cluster_name, size}
    })


def load_registry(path: Path = APPROVAL_REGISTRY_PATH) -> ApprovalRegistry:
    """Load existing registry or return a fresh one.

    Parameters
    ----------
    path : Path
        Path to the approval registry JSON file.

    Returns
    -------
    ApprovalRegistry
        Loaded registry or a new empty one if file does not exist.
    """
    if not path.exists():
        return ApprovalRegistry()
    with open(path) as f:
        data = json.load(f)
    return ApprovalRegistry(**data)


def save_registry(reg: ApprovalRegistry, path: Path = APPROVAL_REGISTRY_PATH) -> None:
    """Write registry to disk atomically.

    Writes to a temporary file first, then renames to the target path
    to avoid partial writes on crash.

    Parameters
    ----------
    reg : ApprovalRegistry
        The registry to save.
    path : Path
        Destination path for the registry JSON file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    reg.timestamp = datetime.now().isoformat()
    tmp = path.with_suffix(".tmp")
    json.dump(asdict(reg), tmp, indent=2)
    tmp.rename(path)


def is_new_approval(reg: ApprovalRegistry, cluster_id: int) -> bool:
    """Return True if cluster_id is not already in the approved list.

    Used to determine whether to increment rounds_completed.

    Parameters
    ----------
    reg : ApprovalRegistry
        The current registry.
    cluster_id : int
        Cluster ID being approved.

    Returns
    -------
    bool
        True if this is a new (first-time) approval for this cluster.
    """
    approved_ids = {c["cluster_id"] for c in reg.clusters.get("approved", [])}
    return cluster_id not in approved_ids
