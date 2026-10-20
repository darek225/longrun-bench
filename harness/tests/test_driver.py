import dataclasses
import json
import shutil

from longrun.driver import Driver, ScriptedAdapter
from longrun.manifest import load_manifest, render_instance
from longrun.models import Budgets
from longrun.tools import WorkspaceTools

from conftest import TASKS_DIR

AGENT = {"name": "test-agent", "model": "scripted", "profile": "standard"}


def _instance(task_id="sprint-code-001", seed=7, steps=None):
    manifest = load_manifest(TASKS_DIR / task_id)
    instance = render_instance(manifest, seed=seed)
    if steps is not None:
        instance = dataclasses.replace(instance, budgets=Budgets(steps=steps, wall_clock_minutes=15))
    return instance


def _copy_fixtures(task_id, workspace):
    fixtures = TASKS_DIR / task_id / "fixtures"
    for item in fixtures.iterdir():
        dest = workspace / item.name
        if item.is_dir():
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)


def _run(tmp_path, instance, responses, task_id="sprint-code-001"):
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    if task_id:
        _copy_fixtures(task_id, workspace)
    tools = WorkspaceTools(workspace, allowlist=instance.network_allowlist)
    driver = Driver(tools, tmp_path / "transcript.jsonl")
    return driver.run(instance, ScriptedAdapter(responses), agent=AGENT)


def test_ultra_run_seeds_memory_file(tmp_path):
    # docs/plan/15 §8: Ultra runs start with a memory.md skeleton in the
    # workspace; Sprint runs do not get one.
    manifest = load_manifest(TASKS_DIR.parent / "ultra" / "ultra-research-004")
    instance = render_instance(manifest, seed=42)
    instance = dataclasses.replace(instance, budgets=Budgets(steps=1, wall_clock_minutes=15))
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    fixtures = TASKS_DIR.parent / "ultra" / "ultra-research-004" / "fixtures"
    for item in fixtures.iterdir():
        dest = workspace / item.name
        if item.is_dir():
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)
    tools = WorkspaceTools(workspace, allowlist=instance.network_allowlist)
    driver = Driver(tools, tmp_path / "transcript.jsonl")
    driver.run(instance, ScriptedAdapter([]), agent=AGENT)
    memory = (workspace / "memory.md").read_text(encoding="utf-8")
    assert memory.startswith("# Memory — ultra-research-004")
    assert "memory_seeded" in [event["type"] for event in driver.transcript.events]


def test_ultra_memory_never_overwritten(tmp_path):
    from longrun.driver import seed_ultra_memory

    (tmp_path / "memory.md").write_text("agent state\n", encoding="utf-8")
    assert seed_ultra_memory(tmp_path, "ultra-x") is None
    assert (tmp_path / "memory.md").read_text(encoding="utf-8") == "agent state\n"


def test_scripted_happy_path_delivers(tmp_path):
    script = json.loads((TASKS_DIR / "sprint-code-001" / "smoke-script.json").read_text(encoding="utf-8"))
    result = _run(tmp_path, _instance(), script)
    assert result.end_reason == "deliverable"
    assert result.totals["steps"] == 5
    assert result.deliverable and result.deliverable["artifact_uri"] == "summary.md"
    types = [event["type"] for event in result.events]
    assert types[0] == "run_start" and types[-1] == "run_end"
    assert "tool_call" in types and "deliverable" in types
    lines = (tmp_path / "transcript.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == len(result.events)


def test_malformed_calls_burn_budget_and_end_cleanly(tmp_path):
    responses = [{"tool_calls": [{"name": "nope.tool", "args": {}}]} for _ in range(10)]
    result = _run(tmp_path, _instance(steps=3), responses)
    assert result.end_reason == "budget"
    assert result.totals["steps"] == 3
    assert any(event["type"] == "budget_exceeded" for event in result.events)


def test_silent_model_fails_after_three_strikes(tmp_path):
    result = _run(tmp_path, _instance(), [{} for _ in range(6)])
    assert result.end_reason == "error"
    assert result.totals["steps"] == 0


def test_persistent_model_errors_end_run(tmp_path):
    result = _run(tmp_path, _instance(), [{"error": "boom"} for _ in range(5)])
    assert result.end_reason == "error"
    assert sum(1 for event in result.events if event["type"] == "model_error") == 3


def test_text_only_streak_triggers_nudge_then_recovers(tmp_path):
    responses = [
        {"text": "thinking"},
        {"text": "still thinking"},
        {"text": "almost there"},
        {"tool_calls": [{"name": "file.write", "args": {"path": "summary.md", "content": "done"}}]},
        {"tool_calls": [{"name": "deliver", "args": {"summary": "s", "artifact_uri": "summary.md"}}]},
    ]
    result = _run(tmp_path, _instance(), responses)
    assert result.end_reason == "deliverable"
    assert any(event["type"] == "nudge" for event in result.events)


def test_deliver_with_missing_artifact_costs_a_step_and_continues(tmp_path):
    responses = [
        {"tool_calls": [{"name": "deliver", "args": {"summary": "s", "artifact_uri": "nope.md"}}]},
        {"tool_calls": [{"name": "file.write", "args": {"path": "summary.md", "content": "done"}}]},
        {"tool_calls": [{"name": "deliver", "args": {"summary": "s", "artifact_uri": "summary.md"}}]},
    ]
    result = _run(tmp_path, _instance(), responses)
    assert result.end_reason == "deliverable"
    assert result.totals["steps"] == 3
