import json

from longrun.cli import main
from longrun.sessions import load_session

from conftest import TASKS_DIR

ULTRA_TASK = TASKS_DIR.parent / "ultra" / "ultra-research-004"
PINNED = ["--seed", "42", "--param", "round=final", "--param", "committee=standard"]


def _split_script(tmp_path):
    script = json.loads((ULTRA_TASK / "smoke-script.json").read_text(encoding="utf-8"))
    first = tmp_path / "sess1.json"
    rest = tmp_path / "sess2.json"
    first.write_text(json.dumps(script[:1]), encoding="utf-8")
    rest.write_text(json.dumps(script[1:]), encoding="utf-8")
    return first, rest


def test_session_pause_then_resume_completes(tmp_path):
    first, rest = _split_script(tmp_path)
    out_dir = tmp_path / "run"
    code = main([
        "run-scripted", str(ULTRA_TASK), *PINNED,
        "--script", str(first), "--out", str(out_dir), "--session-steps", "1",
    ])
    assert code == 3  # paused, not finished
    state = load_session(out_dir)
    assert state is not None and state.status == "paused"
    assert state.session_number == 1 and state.steps_used == 1
    # The workspace persists across the boundary, memory file included.
    assert (out_dir / "workspace" / "memory.md").exists()
    assert (out_dir / "workspace" / "rfp.md").exists()
    # No final scoring artifacts exist for a paused run.
    assert not (out_dir / "submission.json").exists()

    code = main([
        "run-scripted", str(ULTRA_TASK),
        "--script", str(rest), "--out", str(out_dir), "--resume",
    ])
    assert code == 0
    state = load_session(out_dir)
    assert state.status == "completed" and state.session_number == 2
    assert state.steps_used == 3  # cumulative across sessions
    assert len(state.schedule) == 2
    assert state.schedule[0]["end_reason"] == "session_pause"

    run_record = json.loads((out_dir / "run.json").read_text(encoding="utf-8"))
    assert run_record["sessions"] == 2
    assert run_record["totals"]["steps"] == 3
    assert run_record["totals"]["input_tokens"] == 700  # 120 + 580 across sessions
    score = json.loads((out_dir / "score.json").read_text(encoding="utf-8"))
    assert score["total"] > 95

    events = [json.loads(line) for line in (out_dir / "transcript.jsonl").read_text(encoding="utf-8").splitlines()]
    types = [event["type"] for event in events]
    assert types.count("run_start") == 1  # one run, two sessions, one transcript
    assert "session_start" in types and "session_pause" in types and "session_resume" in types
    assert types[-1] == "run_end"


def test_resume_requires_a_session(tmp_path):
    out_dir = tmp_path / "empty"
    out_dir.mkdir()
    code = main([
        "run-scripted", str(ULTRA_TASK),
        "--script", str(ULTRA_TASK / "smoke-script.json"), "--out", str(out_dir), "--resume",
    ])
    assert code == 1


def test_abandon_grades_what_exists(tmp_path):
    first, _rest = _split_script(tmp_path)
    out_dir = tmp_path / "run"
    code = main([
        "run-scripted", str(ULTRA_TASK), *PINNED,
        "--script", str(first), "--out", str(out_dir), "--session-steps", "1",
    ])
    assert code == 3
    assert main(["abandon", "--dir", str(out_dir)]) == 0
    state = load_session(out_dir)
    assert state.status == "abandoned"
    run_record = json.loads((out_dir / "run.json").read_text(encoding="utf-8"))
    assert run_record["abandoned"] is True
    assert run_record["end_reason"] == "abandoned"
    # No deliverable was produced: correctness/completeness are zeroed by the
    # existing scoring rule, and the run is still submittable as data.
    score = json.loads((out_dir / "score.json").read_text(encoding="utf-8"))
    assert score["total"] == 20.0
    assert (out_dir / "submission.json").exists()
    events = [json.loads(line)["type"] for line in (out_dir / "transcript.jsonl").read_text(encoding="utf-8").splitlines()]
    assert events[-1] == "run_abandoned"
    # An abandoned run cannot be abandoned twice or resumed.
    assert main(["abandon", "--dir", str(out_dir)]) == 1
    _first, rest = _split_script(tmp_path)
    code = main([
        "run-scripted", str(ULTRA_TASK),
        "--script", str(rest), "--out", str(out_dir), "--resume",
    ])
    assert code == 1
