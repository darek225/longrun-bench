import json

import pytest

from leaderboard.ingest import IngestError, ingest_submission
from leaderboard.store import Store
from longrun.cli import apply_grade, build_bundle, main
from longrun.driver import AdapterResponse
from longrun.judge import grade_run, prompt_sha256
from longrun.manifest import load_manifest, render_instance
from longrun.checks import run_checks
from longrun.signing import build_submission

from conftest import TASKS_DIR

TASK = "sprint/sprint-data-001"
PARAMS = ["--seed", "42", "--param", "region=north", "--param", "top_n=3"]


class StubJudge:
    """A real-shaped judge adapter: returns fixed criterion JSON.

    This is how a community member's BYO-key judge behaves from the
    pipeline's point of view (docs/plan/06 §3: grading is submitter-funded).
    """

    def __init__(self, scores):
        self.scores = scores

    def complete(self, history, tools):
        payload = {name: {"score": score, "evidence": "stub judge"} for name, score in self.scores.items()}
        payload["flags"] = []
        return AdapterResponse(text=json.dumps(payload), usage={"input_tokens": 10, "output_tokens": 10})


def _run_and_grade(tmp_path, judge_scores):
    task_dir = TASKS_DIR / TASK
    out_dir = tmp_path / "out-graded"
    code = main(["run-scripted", str(task_dir), *PARAMS, "--script", str(task_dir / "smoke-script.json"), "--out", str(out_dir)])
    assert code == 0
    manifest = load_manifest(task_dir)
    run_record = json.loads((out_dir / "run.json").read_text(encoding="utf-8"))
    instance = render_instance(manifest, seed=42, overrides=dict(run_record["params"]))
    workspace = out_dir / "workspace"
    deliverable_path = workspace / "report.md"
    outcomes = run_checks(instance.deterministic_checks, workspace=workspace, deliverable_path=deliverable_path, task_params=instance.params)
    events = [json.loads(line) for line in (out_dir / "transcript.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    graded = grade_run(
        instance=instance,
        outcomes=outcomes,
        events=events,
        deliverable_text=deliverable_path.read_text(encoding="utf-8"),
        judge=StubJudge(judge_scores),
        run_totals=dict(run_record["totals"]),
    )
    apply_grade(out_dir, graded, judge_label="stub/judge-1")
    return out_dir, graded


def test_graded_bundle_ingests_as_graded(tmp_path):
    out_dir, graded = _run_and_grade(
        tmp_path,
        {"correctness": 36, "completeness": 20, "error_recovery": 10, "instruction_adherence": 9},
    )
    checks_total = json.loads((out_dir / "score.json").read_text(encoding="utf-8"))["total"]
    assert graded["total"] != checks_total  # the judge's grades, not the checks-only score
    store = Store(tmp_path / "board.db")
    result = ingest_submission({"board": "community", "runs": [build_bundle(out_dir)]}, store=store, tasks_root=TASKS_DIR)
    assert result["runs_verified"] == 1
    row = store.get_score(result["score_ids"][0])
    assert row["tier"] == "graded"
    assert row["mean_score"] == pytest.approx(graded["total"], abs=0.011)
    manifest = row["run_manifests"][0]
    assert manifest["tier"] == "graded"
    assert manifest["claimed_total"] == manifest["replayed_total"]


def test_graded_claim_ignoring_caps_is_rejected(tmp_path):
    out_dir, graded = _run_and_grade(
        tmp_path,
        {"correctness": 40, "completeness": 25, "error_recovery": 10, "instruction_adherence": 10},
    )
    # Rebuild the run with a deliverable that fails checks, then claim the
    # judge's raw scores as final criteria (caps skipped) with a valid
    # signature and a correct prompt hash. The server replays the checks,
    # applies the caps itself, and must reject.
    bad_dir = tmp_path / "out-bad"
    task_dir = TASKS_DIR / TASK
    bad_script = tmp_path / "bad.json"
    bad_script.write_text(json.dumps([
        {"tool_calls": [{"name": "file.write", "args": {"path": "report.md", "content": "Wrong answer, no figures.\n"}}]},
        {"tool_calls": [{"name": "deliver", "args": {"summary": "bad", "artifact_uri": "report.md"}}]},
    ]), encoding="utf-8")
    code = main(["run-scripted", str(task_dir), *PARAMS, "--script", str(bad_script), "--out", str(bad_dir)])
    assert code == 0
    manifest = load_manifest(task_dir)
    run_record = json.loads((bad_dir / "run.json").read_text(encoding="utf-8"))
    instance = render_instance(manifest, seed=42, overrides=dict(run_record["params"]))
    outcomes = run_checks(
        instance.deterministic_checks,
        workspace=bad_dir / "workspace",
        deliverable_path=bad_dir / "workspace" / "report.md",
        task_params=instance.params,
    )
    assert any(not outcome.result.passed for outcome in outcomes)
    events = [json.loads(line) for line in (bad_dir / "transcript.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    bad_graded = grade_run(
        instance=instance,
        outcomes=outcomes,
        events=events,
        deliverable_text="Wrong answer, no figures.\n",
        judge=StubJudge({"correctness": 40, "completeness": 25, "error_recovery": 10, "instruction_adherence": 10}),
        run_totals=dict(run_record["totals"]),
    )
    # The honest combination caps correctness well below the raw judge score.
    assert bad_graded["criteria"]["correctness"]["score"] < 40
    forged = json.loads(json.dumps(bad_graded))
    forged["criteria"]["correctness"]["score"] = 40.0
    forged["total"] = round(bad_graded["total"] + (40.0 - bad_graded["criteria"]["correctness"]["score"]), 4)
    submission = build_submission(
        run_record=run_record,
        transcript_path=bad_dir / "transcript.jsonl",
        score=forged,
        judge={"model": "stub/judge-1", "prompt_sha256": prompt_sha256(), "flags": []},
    )
    (bad_dir / "submission.json").write_text(json.dumps(submission, indent=2, sort_keys=True), encoding="utf-8")
    store = Store(tmp_path / "board.db")
    with pytest.raises(IngestError) as excinfo:
        ingest_submission({"board": "community", "runs": [build_bundle(bad_dir)]}, store=store, tasks_root=TASKS_DIR)
    assert "graded criterion mismatch" in str(excinfo.value)


def test_graded_claim_with_wrong_prompt_hash_is_rejected(tmp_path):
    out_dir, graded = _run_and_grade(
        tmp_path,
        {"correctness": 36, "completeness": 20, "error_recovery": 10, "instruction_adherence": 9},
    )
    run_record = json.loads((out_dir / "run.json").read_text(encoding="utf-8"))
    submission = build_submission(
        run_record=run_record,
        transcript_path=out_dir / "transcript.jsonl",
        score=graded,
        judge={"model": "stub/judge-1", "prompt_sha256": "sha256:deadbeef", "flags": []},
    )
    (out_dir / "submission.json").write_text(json.dumps(submission, indent=2, sort_keys=True), encoding="utf-8")
    store = Store(tmp_path / "board.db")
    with pytest.raises(IngestError) as excinfo:
        ingest_submission({"board": "community", "runs": [build_bundle(out_dir)]}, store=store, tasks_root=TASKS_DIR)
    assert "prompt hash" in str(excinfo.value)


def test_graded_claim_without_attestation_is_rejected(tmp_path):
    out_dir, graded = _run_and_grade(
        tmp_path,
        {"correctness": 36, "completeness": 20, "error_recovery": 10, "instruction_adherence": 9},
    )
    run_record = json.loads((out_dir / "run.json").read_text(encoding="utf-8"))
    submission = build_submission(
        run_record=run_record,
        transcript_path=out_dir / "transcript.jsonl",
        score=graded,
    )
    (out_dir / "submission.json").write_text(json.dumps(submission, indent=2, sort_keys=True), encoding="utf-8")
    store = Store(tmp_path / "board.db")
    with pytest.raises(IngestError) as excinfo:
        ingest_submission({"board": "community", "runs": [build_bundle(out_dir)]}, store=store, tasks_root=TASKS_DIR)
    assert "attestation" in str(excinfo.value)
