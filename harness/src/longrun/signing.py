from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any

from . import __version__

HARNESS_KEY_ENV = "LONGRUN_HARNESS_KEY"


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def build_submission(
    *,
    run_record: dict[str, Any],
    transcript_path: str | Path,
    score: dict[str, Any],
    harness_hash: str = "sha256:local-dev",
    redactions_applied: bool = True,
) -> dict[str, Any]:
    """The upload payload from docs/plan/10-runner-flow.md §2.3.

    Contains hashes and the score claim only: never the API key (which never
    enters the harness's data paths), never full tool args.
    """
    submission: dict[str, Any] = {
        "run_id": run_record["run_id"],
        "agent": run_record.get("agent", {}),
        "task_id": run_record["task_id"],
        "seed": run_record["seed"],
        "task_set": run_record.get("task_set", "0.1.0"),
        "harness": {"version": __version__, "hash": harness_hash},
        "transcript_sha256": sha256_file(transcript_path),
        "score_claim": {
            "tier": score.get("tier", "checks"),
            "total": score.get("total"),
            "criteria": {name: item.get("score") for name, item in score.get("criteria", {}).items()},
            "checks": [
                {"id": check["id"], "passed": check["passed"], "score": check["score"]}
                for check in score.get("checks", [])
            ],
        },
        "totals": run_record.get("totals", {}),
        "end_reason": run_record.get("end_reason"),
        "redactions_applied": redactions_applied,
    }
    submission["signature"] = sign_submission(submission)
    return submission


def sign_submission(submission: dict[str, Any]) -> dict[str, Any]:
    payload = {key: value for key, value in submission.items() if key != "signature"}
    digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    key = os.environ.get(HARNESS_KEY_ENV)
    if key:
        mac = hmac.new(key.encode("utf-8"), canonical_json(payload).encode("utf-8"), hashlib.sha256).hexdigest()
        return {"alg": "hmac-sha256", "digest": "sha256:" + digest, "mac": mac}
    return {"alg": "sha256", "digest": "sha256:" + digest, "mac": None}


def verify_submission(submission: dict[str, Any]) -> bool:
    signature = submission.get("signature")
    if not isinstance(signature, dict):
        return False
    expected = sign_submission(submission)
    if expected["digest"] != signature.get("digest"):
        return False
    if signature.get("alg") == "hmac-sha256":
        return bool(expected.get("mac")) and hmac.compare_digest(str(expected["mac"]), str(signature.get("mac")))
    return True
