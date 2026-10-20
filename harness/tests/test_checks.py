import shutil

from longrun.checks import run_checks
from longrun.manifest import load_manifest, render_instance
from longrun.scoring import score_checks_only

from conftest import TASKS_DIR


def _run(task_id, workspace, deliverable_path, overrides=None, seed=42):
    manifest = load_manifest(TASKS_DIR / task_id)
    instance = render_instance(manifest, seed=seed, overrides=overrides or {})
    outcomes = run_checks(
        instance.deterministic_checks,
        workspace=workspace,
        deliverable_path=deliverable_path,
        task_params=instance.params,
    )
    return instance, outcomes


def test_data_checks_pass_on_correct_report(tmp_path):
    report = tmp_path / "report.md"
    report.write_text(
        "Total revenue: $2,550.00 for the north region.\n\n"
        "Top products: Alpha, Gamma, Beta.\n\n"
        "Issues: duplicate order row, a future-dated row, and a missing unit price row. "
        "More detail follows here to clear the minimum length for this check suite case. "
        "The analysis deduplicated exact duplicate orders first, excluded the row with "
        "no unit price from revenue, and counted the future-dated row while flagging "
        "it here for review by the data owner.\n",
        encoding="utf-8",
    )
    _, outcomes = _run("sprint-data-001", tmp_path, report, {"region": "north", "top_n": 3})
    assert all(outcome.result.passed for outcome in outcomes), [o.to_dict() for o in outcomes]


def test_data_checks_fail_on_wrong_report(tmp_path):
    report = tmp_path / "report.md"
    report.write_text(
        "Total revenue: $975.00.\n\nTop products: Gamma, Alpha, Beta.\n\nNothing unusual found.\n",
        encoding="utf-8",
    )
    instance, outcomes = _run("sprint-data-001", tmp_path, report, {"region": "north", "top_n": 3})
    by_id = {outcome.id: outcome for outcome in outcomes}
    assert not by_id["total_revenue_correct"].result.passed
    assert not by_id["anomalies_named"].result.passed
    score = score_checks_only(instance, outcomes, steps_used=3, deliverable_present=True)
    assert score["criteria"]["correctness"]["score"] <= 25
    assert score["total"] < 80


def test_code_checks_fail_before_fix_and_pass_after(tmp_path):
    fixtures = TASKS_DIR / "sprint-code-001" / "fixtures"
    for item in fixtures.iterdir():
        dest = tmp_path / item.name
        if item.is_dir():
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)
    _, outcomes = _run("sprint-code-001", tmp_path, tmp_path / "summary.md", seed=7)
    by_id = {outcome.id: outcome for outcome in outcomes}
    assert not by_id["tests_pass"].result.passed

    dedupe = tmp_path / "dedupe.py"
    dedupe.write_text(
        dedupe.read_text(encoding="utf-8").replace(
            "    return list(set(items))",
            "    seen = set()\n    result = []\n    for item in items:\n"
            "        if item not in seen:\n            seen.add(item)\n            result.append(item)\n"
            "    return result",
        ),
        encoding="utf-8",
    )
    (tmp_path / "summary.md").write_text(
        "Bug: list(set(items)) loses first-seen order because sets are unordered. "
        "Fix: one pass with a seen set, appending each item on first sight. "
        "The full suite now passes and the tests were not modified at all.\n",
        encoding="utf-8",
    )
    _, outcomes = _run("sprint-code-001", tmp_path, tmp_path / "summary.md", seed=7)
    assert all(outcome.result.passed for outcome in outcomes), [o.to_dict() for o in outcomes]


def test_missing_deliverable_fails_checks(tmp_path):
    _, outcomes = _run("sprint-vendor-001", tmp_path, tmp_path / "nope.md", {"product": "crm"})
    assert outcomes
    assert not any(outcome.result.passed for outcome in outcomes if outcome.check != "banned_phrases")
