from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Any

from .models import TaskInstance, TaskManifest

_PLACEHOLDER = re.compile(r"{{\s*([A-Za-z0-9_.-]+)\s*}}")
_WHOLE_PLACEHOLDER = re.compile(r"^{{\s*([A-Za-z0-9_.-]+)\s*}}$")


class ManifestError(ValueError):
    pass


def load_manifest(task_dir: str | Path) -> TaskManifest:
    path = Path(task_dir)
    manifest_path = path / "manifest.json"
    if not manifest_path.exists():
        raise ManifestError(f"missing manifest.json in {path}")
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest = TaskManifest.from_dict(path, data)
    validate_manifest(manifest)
    return manifest


def validate_manifest(manifest: TaskManifest) -> None:
    errors: list[str] = []
    if not manifest.id:
        errors.append("manifest id is required")
    if manifest.level not in (1, 2, 3):
        errors.append("level must be 1, 2, or 3")
    if not manifest.prompt_template.strip():
        errors.append("prompt_template is required")
    if not manifest.rubric:
        errors.append("rubric is required")
    total = sum(item.weight for item in manifest.rubric)
    if abs(total - 100.0) > 0.001:
        errors.append(f"rubric weights must sum to 100, got {total}")
    if not manifest.deterministic_checks:
        errors.append("at least one deterministic check is required")
    for check in manifest.deterministic_checks:
        if "id" not in check or "check" not in check:
            errors.append(f"deterministic check missing id/check: {check!r}")
    task_md = manifest.task_dir / "task.md"
    rubric_md = manifest.task_dir / "rubric.md"
    if not task_md.exists():
        errors.append("task.md is required")
    if not rubric_md.exists():
        errors.append("rubric.md is required")
    if errors:
        raise ManifestError("; ".join(errors))


def _lookup(params: dict[str, Any], dotted: str) -> Any:
    current: Any = params
    for part in dotted.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            raise ManifestError(f"unknown template parameter: {dotted}")
    return current


def _stringify(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    return str(value)


def render_value(value: Any, params: dict[str, Any]) -> Any:
    if isinstance(value, str):
        whole = _WHOLE_PLACEHOLDER.match(value.strip())
        if whole:
            return _lookup(params, whole.group(1))
        return _PLACEHOLDER.sub(lambda match: _stringify(_lookup(params, match.group(1))), value)
    if isinstance(value, list):
        return [render_value(item, params) for item in value]
    if isinstance(value, dict):
        return {key: render_value(item, params) for key, item in value.items()}
    return value


def _sample_parameter(name: str, spec: dict[str, Any], rng: random.Random) -> Any:
    kind = spec.get("type")
    if kind == "integer":
        return rng.randint(int(spec["min"]), int(spec["max"]))
    if kind == "number":
        return rng.uniform(float(spec["min"]), float(spec["max"]))
    if kind == "enum":
        values = list(spec["values"])
        if not values:
            raise ManifestError(f"enum parameter {name} has no values")
        return rng.choice(values)
    if kind == "string":
        values = list(spec.get("values", []))
        if values:
            return rng.choice(values)
        return str(spec.get("default", ""))
    if "default" in spec:
        return spec["default"]
    raise ManifestError(f"unsupported parameter spec for {name}: {spec!r}")


def render_instance(
    manifest: TaskManifest,
    seed: int,
    overrides: dict[str, Any] | None = None,
) -> TaskInstance:
    rng = random.Random(seed)
    params: dict[str, Any] = {}
    overrides = overrides or {}

    for name, spec in manifest.parameters.items():
        if name in overrides:
            params[name] = overrides[name]
        else:
            params[name] = _sample_parameter(name, dict(spec), rng)

    for derived in manifest.raw.get("derived_params", []):
        key_template = str(derived["key"])
        key = str(render_value(key_template, params))
        mapping = dict(derived["map"])
        if key not in mapping:
            raise ManifestError(f"derived param {derived['name']} has no mapping for key {key!r}")
        params[str(derived["name"])] = mapping[key]

    prompt = str(render_value(manifest.prompt_template, params))
    checks = render_value(manifest.deterministic_checks, params)
    return TaskInstance(
        task_id=manifest.id,
        task_dir=manifest.task_dir,
        seed=seed,
        params=params,
        prompt=prompt,
        budgets=manifest.budgets,
        rubric=manifest.rubric,
        deterministic_checks=list(checks),
        network_allowlist=manifest.network_allowlist,
        task_set_version=str(manifest.raw.get("task_set_version", "0.1.0")),
        level=manifest.level,
    )


def parse_param_overrides(items: list[str] | None) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    for item in items or []:
        if "=" not in item:
            raise ManifestError(f"parameter override must be key=value, got {item!r}")
        key, raw = item.split("=", 1)
        try:
            value: Any = json.loads(raw)
        except json.JSONDecodeError:
            value = raw
        overrides[key] = value
    return overrides
