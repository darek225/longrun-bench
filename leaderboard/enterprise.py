from __future__ import annotations

import hashlib
import secrets
from typing import Any

from .store import Store

# Enterprise API (SPEC.md §9.3, docs/plan/08 §3): paid access to score
# history, CI data, and head-to-head comparisons for buyers choosing agent
# platforms. Keys are bearer credentials issued by the operator; only the
# sha256 hash is stored, the key is shown exactly once at creation, and a
# revoked key stops working immediately. The data behind the API is the
# same append-only score record the public board reads; the API sells
# depth (full history incl. superseded rows, per-task deltas), never
# different numbers.

KEY_PREFIX = "lrk_"


class EnterpriseError(ValueError):
    pass


def hash_key(key: str) -> str:
    return "sha256:" + hashlib.sha256(key.encode("utf-8")).hexdigest()


def create_api_key(store: Store, *, label: str) -> dict[str, Any]:
    """Issue a key. Returns the plaintext key once; it cannot be recovered."""
    key = KEY_PREFIX + secrets.token_urlsafe(32)
    key_id = store.create_api_key(key_hash=hash_key(key), label=label, scope="enterprise")
    return {"id": key_id, "label": label, "scope": "enterprise", "key": key}


def authenticate(store: Store, header_value: str | None) -> dict[str, Any] | None:
    """Resolve an X-API-Key header to its key record, or None."""
    if not header_value:
        return None
    record = store.api_key_by_hash(hash_key(header_value.strip()))
    if record is None or record.get("revoked_at"):
        return None
    return record


def history(store: Store, **filters: Any) -> dict[str, Any]:
    rows = store.score_history(**filters)
    return {"scores": rows, "count": len(rows)}


def compare(store: Store, *, left_id: str, right_id: str) -> dict[str, Any]:
    """Head-to-head between two score rows.

    Profiles and levels are never compared (DECISIONS.md #20): a compare
    across either is refused, not computed. Cross task-set versions are
    computed but marked approximate (SPEC.md §7.2).
    """
    left = store.get_score(left_id)
    if left is None:
        raise KeyError(f"unknown score id: {left_id}")
    right = store.get_score(right_id)
    if right is None:
        raise KeyError(f"unknown score id: {right_id}")
    if left["profile"] != right["profile"]:
        raise EnterpriseError(
            f"scores are never compared across profiles ({left['profile']} vs {right['profile']})"
        )
    if left["level"] != right["level"]:
        raise EnterpriseError(
            f"scores are never compared across levels ({left['level']} vs {right['level']})"
        )
    left_tasks = {row["task_id"]: row for row in left["task_scores"]}
    right_tasks = {row["task_id"]: row for row in right["task_scores"]}
    shared = sorted(set(left_tasks) & set(right_tasks))
    per_task = [
        {
            "task_id": task_id,
            "left_mean": left_tasks[task_id]["mean_score"],
            "right_mean": right_tasks[task_id]["mean_score"],
            "delta": round(left_tasks[task_id]["mean_score"] - right_tasks[task_id]["mean_score"], 4),
        }
        for task_id in shared
    ]
    return {
        "left": {key: left[key] for key in ("id", "agent_name", "model", "profile", "level", "task_set", "mean_score", "ci_low", "ci_high", "median_score", "tier", "status")},
        "right": {key: right[key] for key in ("id", "agent_name", "model", "profile", "level", "task_set", "mean_score", "ci_low", "ci_high", "median_score", "tier", "status")},
        "mean_delta": round(left["mean_score"] - right["mean_score"], 4),
        "ci_overlap": left["ci_low"] <= right["ci_high"] and right["ci_low"] <= left["ci_high"],
        "shared_tasks": shared,
        "per_task": per_task,
        "approximate": left["task_set"] != right["task_set"],
    }


def export_scores(store: Store, *, board: str | None = None) -> dict[str, Any]:
    """Bulk export of the current board with full CI data."""
    rows = store.latest_scores(board=board)
    return {"scores": rows, "count": len(rows)}
