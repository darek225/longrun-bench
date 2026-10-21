from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .adapters import make_adapter
from .checks import run_checks
from .driver import Driver, ScriptedAdapter, TranscriptWriter
from .judge import JudgeError, MockJudge, grade_run, prompt_sha256
from .manifest import ManifestError, load_manifest, parse_param_overrides, render_instance
from .pricing import actual_cost, estimate_cost_range, load_pricing
from .redact import redact_transcript_file
from .scoring import score_checks_only
from .sessions import SessionState, load_session
from .signing import build_submission
from .tools import WorkspaceTools


def _print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, default=str))


def _load_instance(args: argparse.Namespace):
    manifest = load_manifest(args.task_dir)
    overrides = parse_param_overrides(args.param)
    return manifest, render_instance(manifest, seed=args.seed, overrides=overrides)


def _load_instance_or_resume(args: argparse.Namespace):
    """With --resume, the instance comes from the session snapshot, not the
    CLI seed/params: a resumed session must be the same instance (plan 09 §4)."""
    if not getattr(args, "resume", False):
        return _load_instance(args)
    state = load_session(Path(args.out))
    if state is None:
        raise ManifestError(f"no session.json in {args.out}; nothing to resume")
    if state.status not in ("in_progress", "paused"):
        raise ManifestError(f"session in {args.out} is {state.status}; only in_progress/paused sessions resume")
    manifest = load_manifest(state.task_dir)
    instance = render_instance(manifest, seed=state.seed, overrides=state.params)
    if instance.task_id != state.task_id:
        raise ManifestError(f"task_dir renders {instance.task_id}, session is for {state.task_id}")
    return manifest, instance


def cmd_validate_task(args: argparse.Namespace) -> int:
    try:
        manifest = load_manifest(args.task_dir)
        instance = render_instance(manifest, seed=args.seed)
    except ManifestError as exc:
        _print_json({"ok": False, "error": str(exc)})
        return 1
    _print_json(
        {
            "ok": True,
            "task_id": manifest.id,
            "level": manifest.level,
            "category": manifest.category,
            "checks": len(manifest.deterministic_checks),
            "sample_params": instance.params,
        }
    )
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    try:
        _, instance = _load_instance(args)
    except ManifestError as exc:
        _print_json({"ok": False, "error": str(exc)})
        return 1
    _print_json(instance.to_dict())
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    try:
        _, instance = _load_instance(args)
    except ManifestError as exc:
        _print_json({"ok": False, "error": str(exc)})
        return 1
    workspace = Path(args.workspace or instance.task_dir)
    deliverable = Path(args.deliverable) if args.deliverable else None
    if deliverable is not None and not deliverable.is_absolute():
        deliverable = workspace / deliverable
    outcomes = run_checks(
        instance.deterministic_checks,
        workspace=workspace,
        deliverable_path=deliverable,
        task_params=instance.params,
    )
    score = score_checks_only(
        instance,
        outcomes,
        steps_used=int(args.steps_used),
        deliverable_present=deliverable is not None and deliverable.exists(),
    )
    if args.out:
        Path(args.out).write_text(json.dumps(score, indent=2, sort_keys=True), encoding="utf-8")
    _print_json(score)
    return 0 if all(outcome.result.passed for outcome in outcomes) else 2


def _copy_fixtures(task_dir: Path, workspace: Path) -> None:
    fixtures = task_dir / "fixtures"
    if not fixtures.exists():
        return
    for item in fixtures.iterdir():
        destination = workspace / item.name
        if item.is_dir():
            shutil.copytree(item, destination, dirs_exist_ok=True)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, destination)


def _finish_run(out_dir: Path, workspace: Path, instance: Any, result: Any, agent: dict[str, Any]) -> dict[str, Any]:
    deliverable_path = None
    if result.deliverable:
        deliverable_path = Path(str(result.deliverable["artifact_path"]))
    outcomes = run_checks(
        instance.deterministic_checks,
        workspace=workspace,
        deliverable_path=deliverable_path,
        task_params=instance.params,
    )
    score = score_checks_only(
        instance,
        outcomes,
        steps_used=int(result.totals["steps"]),
        input_tokens=int(result.totals["input_tokens"]),
        output_tokens=int(result.totals["output_tokens"]),
        wall_clock_s=float(result.totals["wall_clock_s"]),
        deliverable_present=deliverable_path is not None and deliverable_path.exists(),
    )
    run_record = {
        "run_id": result.run_id,
        "end_reason": result.end_reason,
        "task_id": instance.task_id,
        "task_set": instance.task_set_version,
        "seed": instance.seed,
        "params": instance.params,
        "agent": agent,
        "totals": result.totals,
        "deliverable": result.deliverable,
        "score_total": score["total"],
    }
    submission = build_submission(
        run_record=run_record,
        transcript_path=out_dir / "transcript.jsonl",
        score=score,
    )
    (out_dir / "score.json").write_text(json.dumps(score, indent=2, sort_keys=True), encoding="utf-8")
    (out_dir / "run.json").write_text(json.dumps(run_record, indent=2, sort_keys=True), encoding="utf-8")
    (out_dir / "submission.json").write_text(json.dumps(submission, indent=2, sort_keys=True), encoding="utf-8")
    run_record["submission_signature"] = submission["signature"]["alg"]
    return run_record


def _prepare_workspace(task_dir: str, out_dir: Path) -> Path:
    workspace = out_dir / "workspace"
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    _copy_fixtures(Path(task_dir), workspace)
    return workspace


def _execute(args: argparse.Namespace, instance: Any, adapter: Any, agent: dict[str, Any]):
    """Run one session of a run and post-process it.

    Plain runs are one session that ends the run. Session mode (Ultra,
    docs/plan/09 §4) is entered with --session-steps or --resume: budgets and
    the transcript are cumulative across sessions, the workspace and memory
    file persist, and a session that hits its step cap pauses (exit code 3)
    instead of ending the run.
    """
    out_dir = Path(args.out)
    session_steps = getattr(args, "session_steps", None)
    state: SessionState | None = None
    if getattr(args, "resume", False):
        state = load_session(out_dir)
    session_mode = session_steps is not None or state is not None
    if state is not None:
        workspace = out_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
    else:
        workspace = _prepare_workspace(args.task_dir, out_dir)
    if session_mode and state is None:
        state = SessionState(
            run_id=str(uuid.uuid4()),
            task_id=instance.task_id,
            task_dir=str(args.task_dir),
            seed=instance.seed,
            params=instance.params,
            agent=agent,
        )
    tools = WorkspaceTools(workspace, allowlist=instance.network_allowlist)
    driver = Driver(tools, out_dir / "transcript.jsonl")
    if state is not None:
        wall_before = state.wall_clock_s
        state.session_number += 1
        result = driver.run(
            instance,
            adapter,
            agent=agent,
            run_id=state.run_id,
            initial_steps=state.steps_used,
            initial_input_tokens=state.input_tokens,
            initial_output_tokens=state.output_tokens,
            initial_wall_clock_s=state.wall_clock_s,
            session_number=state.session_number,
            session_step_cap=session_steps,
        )
        state.steps_used = int(result.totals["steps"])
        state.input_tokens = int(result.totals["input_tokens"])
        state.output_tokens = int(result.totals["output_tokens"])
        state.wall_clock_s = float(result.totals["wall_clock_s"])
        state.record_session(
            steps=int(result.totals.get("session_steps", result.totals["steps"])),
            wall_clock_s=state.wall_clock_s - wall_before,
            end_reason=result.end_reason,
        )
        if result.end_reason == "session_pause":
            state.status = "paused"
            state.save(out_dir)
            record = {
                "run_id": result.run_id,
                "task_id": instance.task_id,
                "seed": instance.seed,
                "params": instance.params,
                "agent": agent,
                "status": "paused",
                "sessions": state.session_number,
                "end_reason": "session_pause",
                "totals": result.totals,
            }
            (out_dir / "run.json").write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
            return 3, record, result
        state.status = "completed"
        state.save(out_dir)
    else:
        result = driver.run(instance, adapter, agent=agent)
    run_record = _finish_run(out_dir, workspace, instance, result, agent)
    if state is not None:
        run_record["sessions"] = state.session_number
        (out_dir / "run.json").write_text(json.dumps(run_record, indent=2, sort_keys=True), encoding="utf-8")
    return (0 if result.end_reason == "deliverable" else 2), run_record, result


def cmd_run_scripted(args: argparse.Namespace) -> int:
    try:
        _, instance = _load_instance_or_resume(args)
    except ManifestError as exc:
        _print_json({"ok": False, "error": str(exc)})
        return 1
    responses = json.loads(Path(args.script).read_text(encoding="utf-8"))
    if not isinstance(responses, list):
        _print_json({"ok": False, "error": "script must be a JSON list of adapter responses"})
        return 1
    agent = {"name": args.agent_name, "model": args.model, "profile": "standard"}
    code, run_record, _result = _execute(args, instance, ScriptedAdapter(responses), agent)
    _print_json(run_record)
    return code


def cmd_run(args: argparse.Namespace) -> int:
    try:
        manifest, instance = _load_instance_or_resume(args)
    except ManifestError as exc:
        _print_json({"ok": False, "error": str(exc)})
        return 1
    price_override = None
    if args.price_in is not None and args.price_out is not None:
        price_override = (float(args.price_in), float(args.price_out))
    try:
        adapter = make_adapter(args.model, base_url=args.base_url)
    except ValueError as exc:
        _print_json({"ok": False, "error": str(exc)})
        return 1
    key_env = getattr(adapter, "api_key_env", None)
    if key_env and not os.environ.get(key_env):
        # Fail before step 1 (docs/plan/10-runner-flow.md §5). The key is only
        # ever read from the environment; it is never a CLI argument.
        _print_json({"ok": False, "error": f"missing API key: set {key_env} in the environment"})
        return 1
    pricing = load_pricing()
    estimate = estimate_cost_range(model=args.model, step_budget=instance.budgets.steps, pricing=pricing, price_override=price_override)
    out_dir = Path(args.out)
    agent = {"name": args.agent_name, "model": args.model, "profile": "standard"}
    print(
        f"Task: {instance.task_id} ({manifest.category}, level {manifest.level}) "
        f"Budgets: {instance.budgets.steps} steps, {instance.budgets.wall_clock_minutes} min. "
        f"Est. cost: {('$%.2f-$%.2f' % (estimate['low_usd'], estimate['high_usd'])) if estimate else 'unknown pricing'}. "
        f"Key: {key_env or 'none'} (from env, never transmitted).",
        file=sys.stderr,
    )
    code, run_record, result = _execute(args, instance, adapter, agent)
    if code != 3:  # a paused session has no final cost yet
        run_record["actual_cost_usd"] = actual_cost(
            model=args.model,
            input_tokens=int(result.totals["input_tokens"]),
            output_tokens=int(result.totals["output_tokens"]),
            pricing=pricing,
            price_override=price_override,
        )
        (out_dir / "run.json").write_text(json.dumps(run_record, indent=2, sort_keys=True), encoding="utf-8")
    _print_json(run_record)
    return code


def cmd_abandon(args: argparse.Namespace) -> int:
    """Close a session-mode run as abandoned (docs/plan/09 §4).

    The partial transcript and workspace are graded on what exists and the
    run becomes submittable, flagged abandoned. Abandoning is data: it still
    counts for the runner's participation stats.
    """
    out_dir = Path(args.dir)
    state = load_session(out_dir)
    if state is None:
        _print_json({"ok": False, "error": f"no session.json in {args.dir}; only session-mode runs can be abandoned"})
        return 1
    if state.status in ("completed", "abandoned"):
        _print_json({"ok": False, "error": f"session is already {state.status}"})
        return 1
    try:
        manifest = load_manifest(state.task_dir)
        instance = render_instance(manifest, seed=state.seed, overrides=state.params)
    except ManifestError as exc:
        _print_json({"ok": False, "error": str(exc)})
        return 1
    writer = TranscriptWriter(out_dir / "transcript.jsonl")
    writer.log("run_abandoned", session=state.session_number, step=state.steps_used)
    state.status = "abandoned"
    state.save(out_dir)
    result = SimpleNamespace(
        run_id=state.run_id,
        end_reason="abandoned",
        deliverable=None,
        totals={
            "steps": state.steps_used,
            "input_tokens": state.input_tokens,
            "output_tokens": state.output_tokens,
            "wall_clock_s": state.wall_clock_s,
        },
    )
    workspace = out_dir / "workspace"
    run_record = _finish_run(out_dir, workspace, instance, result, state.agent)
    run_record["abandoned"] = True
    run_record["sessions"] = state.session_number
    (out_dir / "run.json").write_text(json.dumps(run_record, indent=2, sort_keys=True), encoding="utf-8")
    _print_json(run_record)
    return 0


def cmd_grade(args: argparse.Namespace) -> int:
    try:
        manifest = load_manifest(args.task)
    except ManifestError as exc:
        _print_json({"ok": False, "error": str(exc)})
        return 1
    run_dir = Path(args.run_dir)
    run_record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    instance = render_instance(manifest, seed=int(run_record["seed"]), overrides=dict(run_record.get("params", {})))
    workspace = run_dir / "workspace"
    deliverable = run_record.get("deliverable")
    deliverable_path = Path(str(deliverable["artifact_path"])) if deliverable else None
    deliverable_text = deliverable_path.read_text(encoding="utf-8", errors="replace") if deliverable_path and deliverable_path.exists() else ""
    outcomes = run_checks(
        instance.deterministic_checks,
        workspace=workspace,
        deliverable_path=deliverable_path,
        task_params=instance.params,
    )
    events = []
    transcript_path = run_dir / "transcript.jsonl"
    if transcript_path.exists():
        for line in transcript_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(json.loads(line))
    if args.mock_judge:
        judge: Any = MockJudge(instance, outcomes, events, deliverable_text)
    else:
        if not args.judge_model:
            _print_json({"ok": False, "error": "--judge-model is required unless --mock-judge is given"})
            return 1
        try:
            judge = make_adapter(args.judge_model, base_url=args.judge_base_url)
        except ValueError as exc:
            _print_json({"ok": False, "error": str(exc)})
            return 1
        key_env = getattr(judge, "api_key_env", None)
        if key_env and not os.environ.get(key_env):
            _print_json({"ok": False, "error": f"missing judge API key: set {key_env} in the environment"})
            return 1
    try:
        graded = grade_run(
            instance=instance,
            outcomes=outcomes,
            events=events,
            deliverable_text=deliverable_text,
            judge=judge,
            run_totals=dict(run_record.get("totals", {})),
        )
    except JudgeError as exc:
        _print_json({"ok": False, "error": str(exc)})
        return 1
    (run_dir / "graded-score.json").write_text(json.dumps(graded, indent=2, sort_keys=True), encoding="utf-8")
    if args.mock_judge:
        # The mock judge is a labeled test double: its grades exercise the
        # pipeline locally but never re-sign a submission, so a mock grade
        # can never reach the board as a graded claim.
        submission_tier = "checks (mock grade not submitted)"
    else:
        apply_grade(run_dir, graded, judge_label=str(args.judge_model))
        submission_tier = "graded"
    _print_json(
        {
            "ok": True,
            "tier": graded["tier"],
            "total": graded["total"],
            "flags": graded["flags"],
            "five_percent_rule_violated": graded["judge"]["five_percent_rule_violated"],
            "submission_tier": submission_tier,
        }
    )
    return 0


def apply_grade(run_dir: Path, graded: dict[str, Any], *, judge_label: str) -> dict[str, Any]:
    """Attach a graded score to a finished run (docs/plan/03, plan 06 §3).

    Re-signs the submission with the graded claim plus the judge
    attestation (judge model, hash of the fixed disclosed prompt, flags)
    and the raw judge criterion scores, so the leaderboard can verify the
    claim by replaying the checks and recomputing caps and the total
    itself. The transcript is untouched, so its signed hash still matches.
    """
    run_record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    judge_block = {
        "model": judge_label,
        "prompt_sha256": prompt_sha256(),
        "flags": list(graded.get("flags", [])),
    }
    submission = build_submission(
        run_record=run_record,
        transcript_path=run_dir / "transcript.jsonl",
        score=graded,
        judge=judge_block,
    )
    (run_dir / "submission.json").write_text(json.dumps(submission, indent=2, sort_keys=True), encoding="utf-8")
    run_record["score_total"] = graded["total"]
    run_record["tier"] = "graded"
    (run_dir / "run.json").write_text(json.dumps(run_record, indent=2, sort_keys=True), encoding="utf-8")
    return run_record


def cmd_redact(args: argparse.Namespace) -> int:
    manifest = redact_transcript_file(args.transcript, args.out)
    _print_json(manifest)
    return 0


def build_bundle(run_dir: str | Path) -> dict[str, Any]:
    """Assemble the upload bundle the leaderboard replays (docs/plan/04 §2).

    The signed submission manifest carries hashes and the score claim; the
    bundle adds the run record, the raw transcript, and the workspace files
    so the server can replay the deterministic checks itself. API keys are
    never part of any of these artifacts.
    """
    run_dir = Path(run_dir)
    submission = json.loads((run_dir / "submission.json").read_text(encoding="utf-8"))
    run_record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    transcript = (run_dir / "transcript.jsonl").read_text(encoding="utf-8")
    workspace = run_dir / "workspace"
    workspace_files: dict[str, str] = {}
    if workspace.exists():
        for path in sorted(workspace.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(workspace).as_posix()
            if "__pycache__" in rel or ".pytest_cache" in rel or path.suffix in (".pyc", ".db", ".sqlite"):
                continue
            if path.stat().st_size > 200_000:
                continue
            try:
                workspace_files[rel] = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
    deliverable_rel = None
    deliverable = run_record.get("deliverable") or {}
    if deliverable.get("artifact_path") and workspace.exists():
        try:
            deliverable_rel = Path(str(deliverable["artifact_path"])).relative_to(workspace.resolve()).as_posix()
        except ValueError:
            deliverable_rel = str(deliverable.get("artifact_uri", "")) or None
    return {
        "submission": submission,
        "run_record": run_record,
        "transcript": transcript,
        "workspace_files": workspace_files,
        "deliverable_rel": deliverable_rel,
    }


def cmd_upload(args: argparse.Namespace) -> int:
    submission_path = Path(args.dir) / "submission.json"
    if not submission_path.exists():
        _print_json({"ok": False, "error": f"no submission.json in {args.dir} (run a task first)"})
        return 1
    bundle = build_bundle(args.dir)
    payload: Any = {"board": args.board, "runs": [bundle]}
    url = args.api.rstrip("/") + "/api/scores/submit"
    headers = {"Content-Type": "application/json"}
    token = getattr(args, "token", None) or os.environ.get("LONGRUN_UPLOAD_TOKEN")
    if token:
        # Uploading requires an account on the board; the token ties the
        # score to that account. Boards never see a password.
        headers["X-Upload-Token"] = token
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            _print_json(json.loads(response.read().decode("utf-8")))
            return 0
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        _print_json({"ok": False, "error": f"server rejected submission: HTTP {exc.code}: {body[:300]}"})
        return 1
    except Exception as exc:
        _print_json({"ok": False, "error": f"upload failed: {exc}"})
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="longrun", description="LongRun Bench harness CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate-task", help="validate a task directory")
    validate.add_argument("task_dir")
    validate.add_argument("--seed", type=int, default=42)
    validate.set_defaults(func=cmd_validate_task)

    render = sub.add_parser("render", help="render a task instance")
    render.add_argument("task_dir")
    render.add_argument("--seed", type=int, default=42)
    render.add_argument("--param", action="append", default=[])
    render.set_defaults(func=cmd_render)

    check = sub.add_parser("check", help="run deterministic checks against a deliverable")
    check.add_argument("task_dir")
    check.add_argument("--seed", type=int, default=42)
    check.add_argument("--param", action="append", default=[])
    check.add_argument("--workspace")
    check.add_argument("--deliverable", required=True)
    check.add_argument("--steps-used", type=int, default=0)
    check.add_argument("--out")
    check.set_defaults(func=cmd_check)

    run_scripted = sub.add_parser("run-scripted", help="run a task with a scripted adapter")
    run_scripted.add_argument("task_dir")
    run_scripted.add_argument("--seed", type=int, default=42)
    run_scripted.add_argument("--param", action="append", default=[])
    run_scripted.add_argument("--script", required=True)
    run_scripted.add_argument("--out", required=True)
    run_scripted.add_argument("--agent-name", default="scripted-smoke-agent")
    run_scripted.add_argument("--model", default="scripted")
    run_scripted.add_argument("--session-steps", type=int, help="cap steps for this session; the run pauses and can be resumed (Ultra, plan 09 §4)")
    run_scripted.add_argument("--resume", action="store_true", help="resume the session-mode run in --out from its session.json snapshot")
    run_scripted.set_defaults(func=cmd_run_scripted)

    run = sub.add_parser("run", help="run a task with a real provider adapter (BYO key via env)")
    run.add_argument("task_dir")
    run.add_argument("--seed", type=int, default=42)
    run.add_argument("--param", action="append", default=[])
    run.add_argument("--model", required=True, help="provider/model, e.g. anthropic/claude-opus-5.5 or openai_compat/my-model")
    run.add_argument("--base-url", help="base URL for openai_compat/local providers")
    run.add_argument("--price-in", type=float, help="input price per Mtok (overrides pricing.json)")
    run.add_argument("--price-out", type=float, help="output price per Mtok (overrides pricing.json)")
    run.add_argument("--out", required=True)
    run.add_argument("--agent-name", default="longrun-runner")
    run.add_argument("--session-steps", type=int, help="cap steps for this session; the run pauses and can be resumed (Ultra, plan 09 §4)")
    run.add_argument("--resume", action="store_true", help="resume the session-mode run in --out from its session.json snapshot")
    run.set_defaults(func=cmd_run)

    abandon = sub.add_parser("abandon", help="close a session-mode run as abandoned and grade what exists (plan 09 §4)")
    abandon.add_argument("--dir", required=True)
    abandon.set_defaults(func=cmd_abandon)

    grade = sub.add_parser("grade", help="grade a completed run with the LLM judge (or --mock-judge)")
    grade.add_argument("--task", required=True)
    grade.add_argument("--run-dir", required=True)
    grade.add_argument("--judge-model", help="provider/model for the judge, e.g. anthropic/claude-opus-5.5")
    grade.add_argument("--judge-base-url")
    grade.add_argument("--mock-judge", action="store_true", help="use the deterministic mock judge (pipeline testing only)")
    grade.set_defaults(func=cmd_grade)

    redact = sub.add_parser("redact", help="write a redacted copy of a transcript")
    redact.add_argument("transcript")
    redact.add_argument("--out", required=True)
    redact.set_defaults(func=cmd_redact)

    upload = sub.add_parser("upload", help="upload a run bundle to the leaderboard API for check replay")
    upload.add_argument("--dir", required=True)
    upload.add_argument("--api", default="http://localhost:8787")
    upload.add_argument("--token", default=None, help="account upload token (or set LONGRUN_UPLOAD_TOKEN); boards require an account to upload")
    upload.add_argument("--board", default="community", choices=["official", "community"])
    upload.set_defaults(func=cmd_upload)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
