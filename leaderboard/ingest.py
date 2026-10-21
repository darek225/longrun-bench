from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from longrun.checks import run_checks
from longrun.judge import JudgeError, combine_graded_scores, prompt_sha256
from longrun.manifest import load_manifest, render_instance
from longrun.scoring import score_checks_only
from longrun.signing import verify_submission

from .store import LEVEL_NAMES, TIER_RANK

TOTAL_TOLERANCE = 0.011  # the claim rounds totals to 4 decimals
CHECK_SCORE_TOLERANCE = 0.01


class IngestError(ValueError):
    pass


def _task_index(tasks_root: Path) -> dict[str, Path]:
    index: dict[str, Path] = {}
    for manifest_path in tasks_root.rglob("manifest.json"):
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if "id" in data:
            index[str(data["id"])] = manifest_path.parent
    return index


def verify_and_replay(bundle: dict[str, Any], *, tasks_root: str | Path, index: dict[str, Path] | None = None) -> dict[str, Any]:
    """Verify one run bundle and replay its deterministic checks server-side.

    The bundle is what `longrun upload` sends: the signed submission manifest,
    the run record, the raw transcript, and the run workspace files. The
    server never trusts the claimed score: it re-renders the task instance,
    materializes the workspace, replays the same checker code as the harness,
    and rejects on any mismatch (docs/plan/04 §2, docs/plan/06 §4).
    """
    submission = bundle.get("submission")
    run_record = bundle.get("run_record")
    transcript_text = bundle.get("transcript")
    workspace_files = bundle.get("workspace_files")
    if not isinstance(submission, dict) or not isinstance(run_record, dict):
        raise IngestError("bundle requires submission and run_record objects")
    if not isinstance(transcript_text, str) or not isinstance(workspace_files, dict):
        raise IngestError("bundle requires transcript text and workspace_files")
    if not verify_submission(submission):
        raise IngestError("submission signature does not verify")

    digest = "sha256:" + hashlib.sha256(transcript_text.encode("utf-8")).hexdigest()
    if digest != submission.get("transcript_sha256"):
        raise IngestError("transcript hash does not match the signed submission")

    task_id = str(submission.get("task_id"))
    index = index if index is not None else _task_index(Path(tasks_root))
    if task_id not in index:
        raise IngestError(f"unknown task_id: {task_id}")
    manifest = load_manifest(index[task_id])
    instance = render_instance(manifest, seed=int(run_record["seed"]), overrides=dict(run_record.get("params", {})))
    totals = dict(run_record.get("totals", {}))

    tmp = Path(tempfile.mkdtemp(prefix="longrun-replay-"))
    try:
        workspace = tmp / "workspace"
        workspace.mkdir(parents=True)
        for rel, content in workspace_files.items():
            target = (workspace / rel).resolve()
            if not str(target).startswith(str(workspace.resolve())):
                raise IngestError(f"workspace file escapes the workspace: {rel}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(str(content), encoding="utf-8")
        deliverable = run_record.get("deliverable") or {}
        artifact_path = None
        if deliverable.get("artifact_path"):
            rel = bundle.get("deliverable_rel")
            if rel:
                artifact_path = workspace / str(rel)
            else:
                # Run records carry the client machine's absolute path; the
                # deliverable itself sits at the workspace root or a subpath
                # named by artifact_uri.
                uri = str(deliverable.get("artifact_uri", ""))
                artifact_path = workspace / uri if uri else workspace / Path(str(deliverable["artifact_path"])).name
        outcomes = run_checks(
            instance.deterministic_checks,
            workspace=workspace,
            deliverable_path=artifact_path,
            task_params=instance.params,
        )
        replay = score_checks_only(
            instance,
            outcomes,
            steps_used=int(totals.get("steps", 0)),
            input_tokens=int(totals.get("input_tokens", 0)),
            output_tokens=int(totals.get("output_tokens", 0)),
            wall_clock_s=float(totals.get("wall_clock_s", 0.0)),
            deliverable_present=artifact_path is not None and artifact_path.exists(),
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    claim = submission.get("score_claim", {})
    claim_checks = {check["id"]: check for check in claim.get("checks", [])}
    for outcome in outcomes:
        claimed = claim_checks.get(outcome.id)
        if claimed is None:
            raise IngestError(f"claim is missing check {outcome.id}")
        if bool(claimed["passed"]) != outcome.result.passed:
            raise IngestError(f"check replay mismatch on {outcome.id}: claimed passed={claimed['passed']}, replayed passed={outcome.result.passed}")
        if abs(float(claimed["score"]) - outcome.result.score) > CHECK_SCORE_TOLERANCE:
            raise IngestError(f"check replay mismatch on {outcome.id}: claimed score {claimed['score']}, replayed {outcome.result.score}")

    tier = str(claim.get("tier", "checks"))
    if tier == "graded":
        # Graded tier (docs/plan/06 §3): the LLM judge's criterion scores
        # are the submitter's evidence, declared in the signed claim. The
        # server does not take the total on faith: it verifies the judge
        # attestation names the fixed disclosed prompt, then recomputes
        # the graded score from the declared judge scores with its own
        # replayed check outcomes (caps and the efficiency formula are
        # recomputed, never trusted). Inflated post-cap criteria or a
        # total that does not follow from the declared judge scores are
        # rejected here; a fabricated judge score itself is what signed
        # attestation, reproduction, and disputes police.
        judge_block = submission.get("judge")
        if not isinstance(judge_block, dict) or not judge_block.get("model"):
            raise IngestError("graded claim requires a judge attestation (judge model, prompt hash)")
        if judge_block.get("prompt_sha256") != prompt_sha256():
            raise IngestError("graded claim judge prompt hash does not match the disclosed prompt")
        judge_scores = claim.get("judge_scores")
        if not isinstance(judge_scores, dict):
            raise IngestError("graded claim requires the raw judge criterion scores")
        try:
            combined = combine_graded_scores(
                instance=instance,
                outcomes=outcomes,
                judge_scores={name: float(value) for name, value in judge_scores.items()},
                run_totals=totals,
            )
        except (JudgeError, ValueError) as exc:
            raise IngestError(f"graded claim judge scores invalid: {exc}")
        claimed_criteria = claim.get("criteria") or {}
        for name, item in combined["criteria"].items():
            claimed_value = claimed_criteria.get(name)
            if claimed_value is None or abs(float(claimed_value) - float(item["score"])) > CHECK_SCORE_TOLERANCE:
                raise IngestError(
                    f"graded criterion mismatch on {name}: claimed {claimed_value}, recomputed {item['score']} "
                    "(check caps and the efficiency formula are applied by the server)"
                )
        verified_total = float(combined["total"])
    elif tier == "checks":
        verified_total = float(replay["total"])
    else:
        raise IngestError(f"unknown score tier in claim: {tier}")
    if abs(float(claim.get("total", -1)) - verified_total) > TOTAL_TOLERANCE:
        raise IngestError(f"total mismatch: claimed {claim.get('total')}, verified {verified_total}")

    agent = submission.get("agent", {})
    return {
        "run_id": str(submission.get("run_id")),
        "task_id": task_id,
        "level": LEVEL_NAMES.get(manifest.level, "sprint"),
        "seed": int(run_record["seed"]),
        "agent_name": str(agent.get("name", "unknown")),
        "model": str(agent.get("model", "unknown")),
        "profile": str(agent.get("profile", "standard")),
        "task_set": str(submission.get("task_set", "0.1.0")),
        "harness_hash": str(submission.get("harness", {}).get("hash", "")),
        "tier": tier,
        "transcript_sha256": digest,
        "claimed_total": float(claim["total"]),
        "replayed_total": verified_total,
    }


def ingest_submission(payload: dict[str, Any], *, store: Any, tasks_root: str | Path) -> dict[str, Any]:
    """Ingest one or more run bundles into board score rows.

    Runs are grouped by (agent, model, profile, level, task_set, board); each
    group becomes one append-only score row. Any rejected run rejects the
    whole submission: a partial board row built on unverified runs is worse
    than no row.
    """
    board = str(payload.get("board", "community"))
    if board not in ("official", "community"):
        raise IngestError("board must be 'official' or 'community'")
    bundles = payload.get("runs")
    if bundles is None and "submission" in payload:
        bundles = [payload]
    if not isinstance(bundles, list) or not bundles:
        raise IngestError("submission requires a non-empty runs list")
    index = _task_index(Path(tasks_root))
    verified = [verify_and_replay(bundle, tasks_root=tasks_root, index=index) for bundle in bundles]

    groups: dict[tuple, dict[str, Any]] = {}
    for run in verified:
        key = (run["agent_name"], run["model"], run["profile"], run["level"], run["task_set"], board)
        group = groups.setdefault(key, {"task_runs": {}, "manifests": [], "tier": "verified", "harness_hash": run["harness_hash"]})
        group["task_runs"].setdefault(run["task_id"], []).append(run["replayed_total"])
        group["manifests"].append(run)
        if TIER_RANK.get(run["tier"], 0) < TIER_RANK.get(group["tier"], 0):
            group["tier"] = run["tier"]

    score_ids = []
    for (agent_name, model, profile, level, task_set, group_board), group in groups.items():
        score_id = store.insert_score_group(
            agent_name=agent_name,
            model=model,
            profile=profile,
            level=level,
            task_set=task_set,
            harness_hash=group["harness_hash"],
            board=group_board,
            tier=group["tier"],
            task_runs=group["task_runs"],
            manifests=group["manifests"],
        )
        score_ids.append(score_id)
    return {"score_ids": score_ids, "runs_verified": len(verified)}
