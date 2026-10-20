import pytest

from longrun.manifest import ManifestError, load_manifest, parse_param_overrides, render_instance

from conftest import TASKS_DIR

TASK_IDS = ["sprint-data-001", "sprint-code-001", "sprint-vendor-001"]


@pytest.mark.parametrize("task_id", TASK_IDS)
def test_seed_tasks_load_and_validate(task_id):
    manifest = load_manifest(TASKS_DIR / task_id)
    assert manifest.id == task_id
    assert sum(item.weight for item in manifest.rubric) == 100
    assert len(manifest.deterministic_checks) >= 3


def test_render_is_deterministic_and_fully_substituted():
    manifest = load_manifest(TASKS_DIR / "sprint-data-001")
    first = render_instance(manifest, seed=42)
    second = render_instance(manifest, seed=42)
    assert first.params == second.params
    assert first.prompt == second.prompt
    assert "{{" not in first.prompt


def test_derived_params_feed_checks():
    manifest = load_manifest(TASKS_DIR / "sprint-data-001")
    instance = render_instance(manifest, seed=1, overrides={"region": "west", "top_n": 2})
    assert instance.params["expected"] == {"top_products": ["Gamma", "Alpha"], "total_revenue": 975}
    checks = {check["id"]: check for check in instance.deterministic_checks}
    assert checks["top_products_named"]["params"]["patterns"] == ["Gamma", "Alpha"]
    assert checks["total_revenue_correct"]["params"]["value"] == 975


def test_unknown_template_parameter_raises():
    manifest = load_manifest(TASKS_DIR / "sprint-data-001")
    manifest.prompt_template = "Hello {{missing_param}}"
    with pytest.raises(ManifestError):
        render_instance(manifest, seed=1)


def test_parse_param_overrides_types():
    overrides = parse_param_overrides(["region=north", "top_n=3", "flag=true"])
    assert overrides == {"region": "north", "top_n": 3, "flag": True}
