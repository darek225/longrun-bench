import json

import pytest

from longrun.checks import run_checks
from longrun.cli import main
from longrun.driver import AdapterResponse
from longrun.judge import JudgeError, MockJudge, grade_run, load_prompt_template, run_calibration
from longrun.manifest import load_manifest, render_instance

from conftest import TASKS_DIR

GOOD_REPORT = (
    "Total revenue: $2,550.00 for the north region.\n\n"
    "Top products: Alpha, Gamma, Beta.\n\n"
    "Issues: duplicate order row, a future-dated row, and a missing unit price row. "
    "The analysis deduplicated exact duplicate orders first, excluded the row with "
    "no unit price from revenue, and counted the future-dated row while flagging "
    "it here for review by the data owner. All figures were computed directly "
    "from the deduplicated dataset and cross-checked once more before delivery.\n"
)


def _instance_and_outcomes(tmp_path, report_text):
    manifest = load_manifest(TASKS_DIR / "sprint-data-001")
    instance = render_instance(manifest, seed=42, overrides={"region": "north", "top_n": 3})
    report = tmp_path / "report.md"
    report.write_text(report_text, encoding="utf-8")
    outcomes = run_checks(instance.deterministic_checks, workspace=tmp_path, deliverable_path=report, task_params=instance.params)
    return instance, outcomes


class _MaxStubJudge:
    def complete(self, history, tools):
        payload = {
            "correctness": {"score": 40, "evidence": "stub"},
            "completeness": {"score": 25, "evidence": "stub"},
            "error_recovery": {"score": 10, "evidence": "stub"},
            "instruction_adherence": {"score": 10, "evidence": "stub"},
            "flags": [],
        }
        return AdapterResponse(text=json.dumps(payload), usage={"input_tokens": 5, "output_tokens": 5})


def test_prompt_matches_doc_03():
    template = load_prompt_template()
    assert "A failed check caps the corresponding criterion" in template
    assert "Output ONLY valid JSON" in template
    assert "possible_fabrication" in template


def test_caps_override_judge_scores(tmp_path):
    instance, outcomes = _instance_and_outcomes(tmp_path, "Total revenue: $12.00.\n\nTop products: Delta.\n")
    graded = grade_run(
        instance=instance,
        outcomes=outcomes,
        events=[],
        deliverable_text="wrong",
        judge=_MaxStubJudge(),
        run_totals={"steps": 3, "input_tokens": 1000, "output_tokens": 200, "wall_clock_s": 1.0},
    )
    # The stub awarded 40/40 correctness; failed checks cap it at 20 (lowest cap).
    assert graded["criteria"]["correctness"]["score"] == 20
    assert graded["tier"] == "graded"


def test_mock_judge_discriminates_good_from_broken(tmp_path):
    instance, good_outcomes = _instance_and_outcomes(tmp_path, GOOD_REPORT)
    events = [{"type": "tool_call", "step": 1, "tool": "file.read", "result_summary": {}}, {"type": "deliverable", "step": 3}]
    totals = {"steps": 3, "input_tokens": 500, "output_tokens": 190, "wall_clock_s": 0.1}
    good = grade_run(instance=instance, outcomes=good_outcomes, events=events, deliverable_text=GOOD_REPORT,
                     judge=MockJudge(instance, good_outcomes, events, GOOD_REPORT), run_totals=totals)
    _, broken_outcomes = _instance_and_outcomes(tmp_path, "Total revenue: $12.00.\n\nTop products: Delta.\n")
    broken = grade_run(instance=instance, outcomes=broken_outcomes, events=events, deliverable_text="wrong",
                       judge=MockJudge(instance, broken_outcomes, events, "wrong"), run_totals=totals)
    assert good["total"] > 85
    assert broken["total"] < good["total"] - 30


def test_judge_invalid_output_rejected(tmp_path):
    instance, outcomes = _instance_and_outcomes(tmp_path, GOOD_REPORT)

    class BadJudge:
        def complete(self, history, tools):
            return AdapterResponse(text="not json at all")

    with pytest.raises(JudgeError):
        grade_run(instance=instance, outcomes=outcomes, events=[], deliverable_text=GOOD_REPORT,
                  judge=BadJudge(), run_totals={"steps": 1})


def test_calibration_machinery():
    report = run_calibration(
        [
            {"id": "a", "human_total": 90, "judge_total": 93},
            {"id": "b", "human_total": 50, "judge_total": 61},
            {"id": "c", "human_total": 70, "judge_total": 70},
        ],
        judge_factory=None,
    )
    assert report["n"] == 3
    assert report["within_5_rate"] == pytest.approx(2 / 3)
    assert report["mean_bias"] == pytest.approx(14 / 3, abs=1e-3)
    assert report["target_met"] is False


def test_cli_grade_with_mock_judge(tmp_path, capsys):
    out_dir = tmp_path / "run"
    code = main([
        "run-scripted", str(TASKS_DIR / "sprint-data-001"),
        "--seed", "42", "--param", "region=north", "--param", "top_n=3",
        "--script", str(TASKS_DIR / "sprint-data-001" / "smoke-script.json"),
        "--out", str(out_dir),
    ])
    assert code == 0
    capsys.readouterr()
    code = main(["grade", "--task", str(TASKS_DIR / "sprint-data-001"), "--run-dir", str(out_dir), "--mock-judge"])
    assert code == 0
    graded = json.loads((out_dir / "graded-score.json").read_text(encoding="utf-8"))
    assert graded["tier"] == "graded" and graded["total"] > 85
