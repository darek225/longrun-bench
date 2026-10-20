#!/usr/bin/env python3
"""Validation sweep for the LongRun Bench task bank (docs/plan/14 section 9).

For every task in bank_index.json:
1. validate + render two seeds (manifest sanity, derived ground truth total),
2. run the scripted solver on the pinned instance: every deterministic check
   must pass,
3. broken-deliverable control: a garbage deliverable in a fresh fixture
   workspace must fail at least one check (seen-to-fail requirement).

Writes tasks/PROGRESS.md with the per-task outcome. Exit 1 on any failure.

Run: python3 tasks/validate_bank.py
"""
from __future__ import annotations

import contextlib
import io
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
sys.path.insert(0, str(REPO / "harness" / "src"))

from longrun.cli import main as cli_main  # noqa: E402
from longrun.manifest import load_manifest, render_instance  # noqa: E402


def _quiet(fn, *args):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = fn(*args)
    return code, buf.getvalue()


def _deliverable_name(task_dir: Path) -> str:
    script = json.loads((task_dir / "smoke-script.json").read_text(encoding="utf-8"))
    for response in reversed(script):
        for call_ in response.get("tool_calls", []):
            if call_["name"] == "deliver":
                return str(call_["args"]["artifact_uri"])
    return "deliverable.md"


def sweep_entry(entry: dict, tmp_root: Path) -> dict:
    task_dir = ROOT / entry["dir"]
    result = {"task_id": entry["task_id"], "level": entry["level"], "category": entry["category"]}
    manifest = load_manifest(task_dir)
    render_instance(manifest, seed=1)
    render_instance(manifest, seed=2)
    result["render"] = "ok"

    out_dir = tmp_root / entry["task_id"]
    args = ["run-scripted", str(task_dir), "--seed", "42"]
    for key, value in entry["pinned_params"].items():
        args += ["--param", f"{key}={json.dumps(value) if not isinstance(value, str) else value}"]
    args += ["--script", str(task_dir / "smoke-script.json"), "--out", str(out_dir)]
    code, _ = _quiet(cli_main, args)
    score = json.loads((out_dir / "score.json").read_text(encoding="utf-8"))
    checks = score["checks"]
    passed = sum(1 for c in checks if c["passed"])
    result["solver"] = f"{passed}/{len(checks)} checks, total {score['total']}"
    result["solver_ok"] = code == 0 and passed == len(checks)
    result["solver_total"] = float(score["total"])
    # Trial transcript (docs/plan/15 §10): the merged bank keeps the trial
    # run's evidence per task, not just a pass mark.
    trial_dir = ROOT / "trials" / entry["task_id"]
    trial_dir.mkdir(parents=True, exist_ok=True)
    for name in ("transcript.jsonl", "score.json", "run.json", "submission.json"):
        artifact = out_dir / name
        if artifact.exists():
            shutil.copy2(artifact, trial_dir / name)

    artifact = _deliverable_name(task_dir)
    control_ws = tmp_root / (entry["task_id"] + "-control")
    fixtures = task_dir / "fixtures"
    if fixtures.exists():
        shutil.copytree(fixtures, control_ws)
    else:
        control_ws.mkdir(parents=True)
    garbage = control_ws / artifact
    garbage.parent.mkdir(parents=True, exist_ok=True)
    garbage.write_text("Wrong answer. Nothing correct here at all, no figures, no names, no work.\n", encoding="utf-8")
    check_args = ["check", str(task_dir), "--seed", "42"]
    for key, value in entry["pinned_params"].items():
        check_args += ["--param", f"{key}={json.dumps(value) if not isinstance(value, str) else value}"]
    check_args += ["--workspace", str(control_ws), "--deliverable", str(garbage), "--out", str(control_ws / "control-score.json")]
    _quiet(cli_main, check_args)
    control_score = json.loads((control_ws / "control-score.json").read_text(encoding="utf-8"))
    failed = sum(1 for c in control_score["checks"] if not c["passed"])
    result["control"] = f"{failed} checks failed on garbage"
    result["control_ok"] = failed >= 1
    result["control_total"] = float(control_score["total"])
    result["ok"] = result["solver_ok"] and result["control_ok"]
    return result


def main() -> int:
    index = json.loads((ROOT / "bank_index.json").read_text(encoding="utf-8"))
    only = sys.argv[1] if len(sys.argv) > 1 else None
    results = []
    with tempfile.TemporaryDirectory(prefix="longrun-bank-") as tmp:
        tmp_root = Path(tmp)
        for entry in index:
            if only and only not in entry["task_id"]:
                continue
            try:
                results.append(sweep_entry(entry, tmp_root))
            except Exception as exc:
                results.append({"task_id": entry["task_id"], "level": entry["level"], "category": entry["category"], "ok": False, "solver": f"ERROR {exc}", "control": "-", "render": "?"})
    failures = [r for r in results if not r["ok"]]
    lines = [
        "# Task bank progress (docs/plan/14 section 9)",
        "",
        "Generated by tasks/generate_bank.py; validated by tasks/validate_bank.py.",
        "Status per task: solver = scripted solver checks on the pinned instance;",
        "control = broken-deliverable control (at least one check must fail).",
        "",
        "| Task | Level | Category | Solver | Control | Verdict |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(f"| {r['task_id']} | {r['level']} | {r['category']} | {r['solver']} | {r['control']} | {'PASS' if r['ok'] else 'FAIL'} |")
    lines.append("")
    lines.append(f"Totals: {len(results) - len(failures)}/{len(results)} tasks pass the sweep.")
    scored = [r for r in results if "solver_total" in r and "control_total" in r]
    if scored:
        discriminating = sum(1 for r in scored if r["ok"])
        mean_solver = sum(r["solver_total"] for r in scored) / len(scored)
        mean_control = sum(r["control_total"] for r in scored) / len(scored)
        index = {
            "tasks": len(scored),
            "discriminating_tasks": discriminating,
            "discrimination_index": round(discriminating / len(scored), 4),
            "mean_solver_total": round(mean_solver, 2),
            "mean_control_total": round(mean_control, 2),
            "mean_gap": round(mean_solver - mean_control, 2),
        }
        lines.append("")
        lines.append(
            "Discrimination index: "
            f"{index['discrimination_index']} of tasks separate the scripted solver from the garbage control "
            f"(mean solver total {index['mean_solver_total']}, mean control total {index['mean_control_total']}, "
            f"mean gap {index['mean_gap']}). Machine-readable copy: tasks/discrimination.json. "
            "Trial transcripts: tasks/trials/<task_id>/."
        )
        if not only:
            (ROOT / "discrimination.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    if not only:
        (ROOT / "PROGRESS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for r in failures:
        print("FAIL", r["task_id"], "| solver:", r["solver"], "| control:", r["control"])
    print(f"swept {len(results)} tasks, {len(failures)} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
