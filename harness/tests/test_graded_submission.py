import json

from longrun.cli import apply_grade, main
from longrun.judge import prompt_sha256
from longrun.signing import verify_submission

from conftest import TASKS_DIR

TASK = TASKS_DIR / "sprint-data-001"
PARAMS = ["--seed", "42", "--param", "region=north", "--param", "top_n=3"]


def _run(tmp_path):
    out_dir = tmp_path / "out"
    code = main(["run-scripted", str(TASK), *PARAMS, "--script", str(TASK / "smoke-script.json"), "--out", str(out_dir)])
    assert code == 0
    return out_dir


def _claim(out_dir):
    return json.loads((out_dir / "submission.json").read_text(encoding="utf-8"))["score_claim"]


def test_mock_grade_never_resigns_submission(tmp_path):
    out_dir = _run(tmp_path)
    assert _claim(out_dir)["tier"] == "checks"
    code = main(["grade", "--task", str(TASK), "--run-dir", str(out_dir), "--mock-judge"])
    assert code == 0
    graded = json.loads((out_dir / "graded-score.json").read_text(encoding="utf-8"))
    assert graded["tier"] == "graded"
    # The mock judge is a test double: the submission keeps its checks claim.
    assert _claim(out_dir)["tier"] == "checks"


def test_apply_grade_resigns_with_attestation(tmp_path):
    out_dir = _run(tmp_path)
    graded = json.loads((out_dir / "score.json").read_text(encoding="utf-8"))
    graded = dict(graded)
    graded["tier"] = "graded"
    graded["total"] = 88.5
    graded["judge_scores"] = {"correctness": 34, "completeness": 21, "error_recovery": 9, "instruction_adherence": 9}
    graded["flags"] = []
    for name, value in graded["judge_scores"].items():
        graded["criteria"][name]["score"] = float(value)
    apply_grade(out_dir, graded, judge_label="stub/judge-1")
    submission = json.loads((out_dir / "submission.json").read_text(encoding="utf-8"))
    assert submission["score_claim"]["tier"] == "graded"
    assert submission["score_claim"]["total"] == 88.5
    assert submission["score_claim"]["judge_scores"]["correctness"] == 34
    assert submission["judge"]["model"] == "stub/judge-1"
    assert submission["judge"]["prompt_sha256"] == prompt_sha256()
    assert verify_submission(submission)
    run_record = json.loads((out_dir / "run.json").read_text(encoding="utf-8"))
    assert run_record["tier"] == "graded" and run_record["score_total"] == 88.5
