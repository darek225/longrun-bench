from longrun.checks import CheckOutcome, Result
from longrun.manifest import load_manifest, render_instance
from longrun.scoring import compute_efficiency, score_checks_only

from conftest import TASKS_DIR


def _instance():
    manifest = load_manifest(TASKS_DIR / "sprint-data-001")
    return render_instance(manifest, seed=42, overrides={"region": "north", "top_n": 3})


def test_efficiency_formula_matches_spec():
    eff = compute_efficiency(
        steps_used=10, step_budget=20, input_tokens=0, output_tokens=0,
        wall_clock_s=0, wall_clock_budget_s=900,
    )
    assert eff["steps_ratio"] == 0.5
    assert eff["raw"] == 0.75
    assert eff["clamped"] == 0.75


def test_failed_check_caps_criterion():
    outcomes = [
        CheckOutcome(id="c1", check="regex_all", result=Result(False, 0.0, "missing"), caps={"correctness": 25}),
        CheckOutcome(id="c2", check="word_count", result=Result(True, 1.0, "ok"), caps={}),
    ]
    score = score_checks_only(_instance(), outcomes, steps_used=3, deliverable_present=True)
    assert score["tier"] == "checks" and score["provisional"] is True
    assert score["criteria"]["correctness"]["score"] == 25
    assert score["criteria"]["completeness"]["score"] == 25
    assert score["total"] < 100


def test_no_deliverable_zeroes_correctness_and_completeness():
    outcomes = [CheckOutcome(id="c1", check="regex_all", result=Result(True, 1.0, "ok"), caps={})]
    score = score_checks_only(_instance(), outcomes, steps_used=3, deliverable_present=False)
    assert score["criteria"]["correctness"]["score"] == 0
    assert score["criteria"]["completeness"]["score"] == 0


def test_efficiency_capped_by_correctness():
    outcomes = [
        CheckOutcome(id="c1", check="regex_all", result=Result(False, 0.0, "missing"), caps={"correctness": 0}),
    ]
    score = score_checks_only(_instance(), outcomes, steps_used=1, deliverable_present=True)
    assert score["criteria"]["efficiency"]["score"] == 0
