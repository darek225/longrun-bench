from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from .checks import run_checks
from .driver import Driver, ScriptedAdapter
from .manifest import ManifestError, load_manifest, parse_param_overrides, render_instance
from .scoring import score_checks_only
from .tools import WorkspaceTools


def _print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, default=str))


def _load_instance(args: argparse.Namespace):
    manifest = load_manifest(args.task_dir)
    overrides = parse_param_overrides(args.param)
    return manifest, render_instance(manifest, seed=args.seed, overrides=overrides)


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


def cmd_run_scripted(args: argparse.Namespace) -> int:
    try:
        manifest, instance = _load_instance(args)
    except ManifestError as exc:
        _print_json({"ok": False, "error": str(exc)})
        return 1

    out_dir = Path(args.out)
    workspace = out_dir / "workspace"
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    _copy_fixtures(Path(args.task_dir), workspace)

    script_path = Path(args.script)
    responses = json.loads(script_path.read_text(encoding="utf-8"))
    if not isinstance(responses, list):
        _print_json({"ok": False, "error": "script must be a JSON list of adapter responses"})
        return 1

    tools = WorkspaceTools(workspace, allowlist=instance.network_allowlist)
    driver = Driver(tools, out_dir / "transcript.jsonl")
    adapter = ScriptedAdapter(responses)
    agent = {"name": args.agent_name, "model": args.model, "profile": "standard"}
    result = driver.run(instance, adapter, agent=agent)

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
        "seed": instance.seed,
        "params": instance.params,
        "totals": result.totals,
        "deliverable": result.deliverable,
        "score_total": score["total"],
    }
    (out_dir / "score.json").write_text(json.dumps(score, indent=2, sort_keys=True), encoding="utf-8")
    (out_dir / "run.json").write_text(json.dumps(run_record, indent=2, sort_keys=True), encoding="utf-8")
    _print_json(run_record)
    return 0 if result.end_reason == "deliverable" else 2


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
    run_scripted.set_defaults(func=cmd_run_scripted)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
