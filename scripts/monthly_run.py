#!/usr/bin/env python3
"""First official monthly run tooling (SPEC.md §10 Phase 3, plan 05 §3).

An official run is a batch: a set of agent configurations, each run over a
task selection at n>=3 seeds (SPEC.md §6.2), ingested onto the official
board through the same signature verification and check replay as any
community submission. The org runs the batch; it never hand-enters scores.

The dry-run mode (config "preliminary": true) exercises the whole pipeline
with the task bank's scripted solvers. Dry-run scores are machinery
evidence, marked preliminary in the report, and are not vendor results.

Usage:
  python3 scripts/monthly_run.py --config scripts/monthly-runs/<run>.json \
      --db leaderboard.db --tasks-root tasks --out docs/monthly-runs/<run> \
      --workdir /tmp/monthly-run-work
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "harness" / "src"))

from leaderboard.ingest import ingest_submission  # noqa: E402
from leaderboard.store import Store  # noqa: E402
from longrun.cli import build_bundle, main as harness_main  # noqa: E402


def run_batch(config: dict[str, Any], *, db_path: str | Path, tasks_root: str | Path, workdir: str | Path) -> dict[str, Any]:
    tasks_root = Path(tasks_root)
    workdir = Path(workdir)
    store = Store(db_path)
    seeds = [int(seed) for seed in config.get("seeds", [42, 43, 44])]
    results = []
    for agent_config in config["configs"]:
        bundles = []
        for task in config["tasks"]:
            task_dir = tasks_root / task["dir"]
            script = task.get("script") or str(task_dir / "smoke-script.json")
            for seed in seeds:
                out_dir = workdir / agent_config["agent_name"] / (Path(task["dir"]).name + f"-s{seed}")
                argv = [
                    "run-scripted", str(task_dir),
                    "--seed", str(seed),
                    "--script", str(script),
                    "--out", str(out_dir),
                    "--agent-name", str(agent_config["agent_name"]),
                    "--model", str(agent_config["model"]),
                ]
                for key, value in (task.get("params") or {}).items():
                    argv += ["--param", f"{key}={value}"]
                code = harness_main(argv)
                if code != 0:
                    raise SystemExit(f"run failed ({code}): {argv}")
                bundles.append(build_bundle(out_dir))
        ingested = ingest_submission(
            {"board": config.get("board", "official"), "runs": bundles},
            store=store,
            tasks_root=tasks_root,
        )
        for score_id in ingested["score_ids"]:
            row = store.get_score(score_id)
            results.append(
                {
                    "agent_name": row["agent_name"],
                    "model": row["model"],
                    "profile": row["profile"],
                    "level": row["level"],
                    "score_id": score_id,
                    "mean_score": row["mean_score"],
                    "ci_low": row["ci_low"],
                    "ci_high": row["ci_high"],
                    "median_score": row["median_score"],
                    "n_tasks": row["n_tasks"],
                    "n_runs": row["n_runs"],
                    "provisional": bool(row["provisional"]),
                    "tier": row["tier"],
                    "status": row["status"],
                }
            )
    return {
        "label": config.get("label", "monthly-run"),
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "board": config.get("board", "official"),
        "preliminary": bool(config.get("preliminary", False)),
        "note": config.get("note", ""),
        "seeds": seeds,
        "tasks": [task["dir"] for task in config["tasks"]],
        "results": results,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Monthly run: {report['label']}",
        "",
        f"Generated {report['generated_at']} on the `{report['board']}` board. "
        f"Seeds: {', '.join(str(s) for s in report['seeds'])}. Tasks: {', '.join(report['tasks'])}.",
        "",
    ]
    if report["preliminary"]:
        lines += [
            "**PRELIMINARY (dry run).** These rows exercise the official-run pipeline end to end "
            "with the task bank's scripted solvers. They are machinery evidence, not vendor results, "
            "and must not be cited as agent scores.",
            "",
        ]
    if report["note"]:
        lines += [report["note"], ""]
    lines += [
        "| Agent | Model | Level | Mean | 95% CI | Median | Tasks | Runs | Tier | Status |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in report["results"]:
        lines.append(
            f"| {row['agent_name']} | {row['model']} | {row['level']} | {row['mean_score']:.2f} "
            f"| {row['ci_low']:.2f} to {row['ci_high']:.2f} | {row['median_score']:.2f} "
            f"| {row['n_tasks']} | {row['n_runs']} | {row['tier']} | {row['status']}"
            f"{' (provisional)' if row['provisional'] else ''} |"
        )
    lines += [
        "",
        "Scores were ingested through the standard path: signature verification and server-side "
        "check replay (leaderboard/ingest.py). No score in this report was entered by hand.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="monthly_run", description="LongRun Bench official monthly run batch")
    parser.add_argument("--config", required=True)
    parser.add_argument("--db", required=True)
    parser.add_argument("--tasks-root", default="tasks")
    parser.add_argument("--out", required=True, help="directory for report.json + report.md")
    parser.add_argument("--workdir", required=True, help="scratch directory for run outputs")
    args = parser.parse_args(argv)
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    report = run_batch(config, db_path=args.db, tasks_root=args.tasks_root, workdir=args.workdir)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    (out_dir / "report.md").write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"label": report["label"], "results": len(report["results"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
