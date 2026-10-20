from __future__ import annotations

import csv
import io
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Result:
    passed: bool
    score: float
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "score": self.score, "detail": self.detail}


@dataclass
class CheckContext:
    workspace: Path
    deliverable_path: Path | None
    task_params: dict[str, Any]

    @property
    def deliverable_text(self) -> str:
        if self.deliverable_path is None or not self.deliverable_path.exists():
            return ""
        return self.deliverable_path.read_text(encoding="utf-8", errors="replace")


@dataclass
class CheckOutcome:
    id: str
    check: str
    result: Result
    caps: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "check": self.check,
            "passed": self.result.passed,
            "score": self.result.score,
            "detail": self.result.detail,
            "caps": self.caps,
        }


class Check:
    """Base class for custom task checks.

    The Phase 2 built-ins are function-backed below; custom task checks can use
    this interface in later slices without changing the manifest shape.
    """

    id = "custom"
    params_schema: dict[str, Any] = {}

    def run(self, context: CheckContext, params: dict[str, Any]) -> Result:
        raise NotImplementedError


def _missing_deliverable(context: CheckContext) -> Result | None:
    if context.deliverable_path is None:
        return Result(False, 0.0, "no deliverable was produced")
    if not context.deliverable_path.exists():
        return Result(False, 0.0, f"deliverable does not exist: {context.deliverable_path}")
    return None


def _regex_all(context: CheckContext, params: dict[str, Any]) -> Result:
    missing = _missing_deliverable(context)
    if missing:
        return missing
    patterns = [str(item) for item in params.get("patterns", [])]
    if not patterns:
        return Result(False, 0.0, "regex_all requires at least one pattern")
    text = context.deliverable_text
    absent = [pattern for pattern in patterns if not re.search(pattern, text, re.IGNORECASE)]
    score = 1.0 - (len(absent) / len(patterns))
    return Result(not absent, score, "all patterns found" if not absent else f"missing patterns: {absent}")


def _regex_any(context: CheckContext, params: dict[str, Any]) -> Result:
    missing = _missing_deliverable(context)
    if missing:
        return missing
    patterns = [str(item) for item in params.get("patterns", [])]
    text = context.deliverable_text
    found = [pattern for pattern in patterns if re.search(pattern, text, re.IGNORECASE)]
    return Result(bool(found), 1.0 if found else 0.0, f"found patterns: {found}" if found else "no patterns found")


def _banned_phrases(context: CheckContext, params: dict[str, Any]) -> Result:
    missing = _missing_deliverable(context)
    if missing:
        return missing
    phrases = [str(item) for item in params.get("phrases", [])]
    text = context.deliverable_text.lower()
    found = [phrase for phrase in phrases if phrase.lower() in text]
    return Result(not found, 1.0 if not found else 0.0, "no banned phrases" if not found else f"banned phrases found: {found}")


def _word_count(context: CheckContext, params: dict[str, Any]) -> Result:
    missing = _missing_deliverable(context)
    if missing:
        return missing
    count = len(re.findall(r"\S+", context.deliverable_text))
    minimum = int(params.get("min", 0))
    maximum = int(params.get("max", 10**9))
    passed = minimum <= count <= maximum
    return Result(passed, 1.0 if passed else 0.0, f"word count {count}, expected {minimum}..{maximum}")


def _csv_valid(context: CheckContext, params: dict[str, Any]) -> Result:
    missing = _missing_deliverable(context)
    if missing:
        return missing
    required = [str(item) for item in params.get("columns", [])]
    try:
        reader = csv.DictReader(io.StringIO(context.deliverable_text))
        rows = list(reader)
    except Exception as exc:  # csv is forgiving; keep the failure explicit.
        return Result(False, 0.0, f"CSV parse failed: {exc}")
    fields = reader.fieldnames or []
    absent = [column for column in required if column not in fields]
    if absent:
        return Result(False, 0.0, f"missing CSV columns: {absent}")
    if not rows:
        return Result(False, 0.0, "CSV has no data rows")
    return Result(True, 1.0, f"CSV parsed with {len(rows)} rows and columns {fields}")


def _extract_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
        if not match:
            raise
        return json.loads(match.group(1))


def _json_path_value(data: Any, path: str) -> Any:
    if not path.startswith("$"):
        raise ValueError("json_path must start with $")
    tokens = re.findall(r"\.([A-Za-z0-9_]+)|\[(\d+)\]", path[1:])
    current = data
    for key, index in tokens:
        if key:
            if not isinstance(current, dict) or key not in current:
                raise KeyError(key)
            current = current[key]
        else:
            current = current[int(index)]
    return current


def _json_path(context: CheckContext, params: dict[str, Any]) -> Result:
    missing = _missing_deliverable(context)
    if missing:
        return missing
    path = str(params["path"])
    try:
        data = _extract_json(context.deliverable_text)
        value = _json_path_value(data, path)
    except Exception as exc:
        return Result(False, 0.0, f"json_path {path} failed: {exc}")
    if "expected" in params:
        passed = value == params["expected"]
        return Result(passed, 1.0 if passed else 0.0, f"{path}={value!r}, expected {params['expected']!r}")
    return Result(True, 1.0, f"{path} present: {value!r}")


def _numeric_within(context: CheckContext, params: dict[str, Any]) -> Result:
    missing = _missing_deliverable(context)
    if missing:
        return missing
    label = str(params["label"])
    expected = float(params["value"])
    tolerance = float(params.get("tolerance", 0.0))
    text = context.deliverable_text
    label_match = re.search(re.escape(label), text, re.IGNORECASE)
    if not label_match:
        return Result(False, 0.0, f"label not found: {label}")
    window = text[label_match.end() : label_match.end() + int(params.get("search_chars", 240))]
    number_match = re.search(r"[-+]?\$?\s*([0-9][0-9,]*(?:\.[0-9]+)?)", window)
    if not number_match:
        return Result(False, 0.0, f"no number found after label: {label}")
    found = float(number_match.group(1).replace(",", ""))
    delta = abs(found - expected)
    passed = delta <= tolerance
    return Result(passed, 1.0 if passed else 0.0, f"found {found} near {label!r}, expected {expected} ± {tolerance}")


def _workspace_path(context: CheckContext, raw: str) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = context.workspace / path
    return path


def _file_exists(context: CheckContext, params: dict[str, Any]) -> Result:
    path = _workspace_path(context, str(params["path"]))
    return Result(path.exists(), 1.0 if path.exists() else 0.0, f"path exists: {path}" if path.exists() else f"missing path: {path}")


def _file_contains(context: CheckContext, params: dict[str, Any]) -> Result:
    path = _workspace_path(context, str(params["path"]))
    if not path.exists():
        return Result(False, 0.0, f"missing file: {path}")
    text = path.read_text(encoding="utf-8", errors="replace")
    patterns = [str(item) for item in params.get("patterns", [])]
    absent = [pattern for pattern in patterns if not re.search(pattern, text, re.IGNORECASE)]
    score = 1.0 - (len(absent) / len(patterns)) if patterns else 0.0
    return Result(not absent, score, "all patterns found" if not absent else f"missing patterns in {path}: {absent}")


def _pytest_pass(context: CheckContext, params: dict[str, Any]) -> Result:
    test_path = _workspace_path(context, str(params.get("test_path", "tests")))
    timeout = int(params.get("timeout", 30))
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", str(test_path)],
            cwd=context.workspace,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return Result(False, 0.0, f"pytest timed out after {timeout}s")
    output = (completed.stdout + completed.stderr).strip().splitlines()
    detail = output[-1] if output else f"pytest exited {completed.returncode}"
    passed = completed.returncode == 0
    return Result(passed, 1.0 if passed else 0.0, detail)


def _git_diff_empty(context: CheckContext, params: dict[str, Any]) -> Result:
    paths = [str(item) for item in params.get("paths", [])]
    completed = subprocess.run(
        ["git", "diff", "--quiet", "--", *paths],
        cwd=context.workspace,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode == 0:
        return Result(True, 1.0, "git diff empty for requested paths")
    if completed.returncode == 1:
        return Result(False, 0.0, "git diff is not empty for requested paths")
    return Result(False, 0.0, f"git diff failed: {completed.stderr.strip()}")


def _diff_line_limit(context: CheckContext, params: dict[str, Any]) -> Result:
    max_lines = int(params["max_lines"])
    completed = subprocess.run(
        ["git", "diff", "--numstat"],
        cwd=context.workspace,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return Result(False, 0.0, f"git diff failed: {completed.stderr.strip()}")
    total = 0
    for line in completed.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            total += int(parts[0]) + int(parts[1])
    passed = total <= max_lines
    return Result(passed, 1.0 if passed else 0.0, f"diff lines {total}, max {max_lines}")


BUILTIN_CHECKS = {
    "regex_all": _regex_all,
    "regex_any": _regex_any,
    "banned_phrases": _banned_phrases,
    "word_count": _word_count,
    "csv_valid": _csv_valid,
    "json_path": _json_path,
    "numeric_within": _numeric_within,
    "file_exists": _file_exists,
    "file_contains": _file_contains,
    "pytest_pass": _pytest_pass,
    "git_diff_empty": _git_diff_empty,
    "diff_line_limit": _diff_line_limit,
}


def run_checks(
    checks: list[dict[str, Any]],
    *,
    workspace: str | Path,
    deliverable_path: str | Path | None,
    task_params: dict[str, Any],
) -> list[CheckOutcome]:
    context = CheckContext(
        workspace=Path(workspace),
        deliverable_path=Path(deliverable_path) if deliverable_path is not None else None,
        task_params=task_params,
    )
    outcomes: list[CheckOutcome] = []
    for check in checks:
        check_name = str(check["check"])
        params = dict(check.get("params", {}))
        caps = {str(key): float(value) for key, value in dict(check.get("caps", {})).items()}
        fn = BUILTIN_CHECKS.get(check_name)
        if fn is None:
            result = Result(False, 0.0, f"unknown built-in check: {check_name}")
        else:
            result = fn(context, params)
        outcomes.append(CheckOutcome(id=str(check["id"]), check=check_name, result=result, caps=caps))
    return outcomes
