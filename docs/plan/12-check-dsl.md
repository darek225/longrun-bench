# 12 — Check DSL: Deterministic Check Framework

## Decisions

- **Checks are Python functions with a declared schema**, not a mini-language. A DSL would need its own parser, docs, and debugger; Python already exists. The "DSL" is a set of check-type base classes with strict interfaces.
- **Checks run in a sandbox:** subprocess, no network, 30s timeout, read-only access to the deliverable. A check that needs network is rejected at task-review time.
- **The server replays checks with the exact pinned check code** from the task's git tag. Check code is versioned with the task set; the replay uses the same bytes.

## 1. Check interface

```python
from longrun.checks import Check, Result

class VendorNamesPresent(Check):
    """All N vendors named in the deliverable."""
    id = "vendors_named"
    params_schema = {"n": int, "vendor_names": [str]}

    def run(self, deliverable_path: str, params: dict, task_params: dict) -> Result:
        text = open(deliverable_path).read().lower()
        missing = [v for v in params["vendor_names"] if v.lower() not in text]
        return Result(
            passed=not missing,
            score=1.0 - len(missing) / len(params["vendor_names"]),
            detail=f"missing: {missing}" if missing else "all present",
        )
```

- `Result(passed: bool, score: float 0..1, detail: str)`. Partial scores allowed; the rubric maps them to criterion caps.
- `task_params` carries the rendered instance parameters (e.g., which vendors were drawn), so checks adapt to the instance.

## 2. Standard check library (`harness/checks/`)

Built-ins every task author can use without writing code:

| Check | Params | What it does |
|---|---|---|
| `regex_all` | `patterns: [str]` | Every pattern found in deliverable |
| `regex_any` | `patterns: [str]` | At least one found |
| `banned_phrases` | `phrases: [str]` | None found (catches "as an AI", lorem ipsum) |
| `word_count` | `min, max` | Word count in range |
| `csv_valid` | `columns: [str]` | Parses as CSV with required columns |
| `json_path` | `path, expected` | JSONPath query matches |
| `numeric_within` | `label, value, tolerance` | Number found near label within tolerance |
| `url_alive` | `urls: [str]` | Every URL returns 200 (the one check allowed network, via the harness proxy) |
| `file_exists` | `path` | Deliverable artifact exists |
| `pytest_pass` | `test_path` | Runs pytest, passes |
| `git_diff_empty` | `paths: [str]` | No modifications under paths (e.g., tests/ untouched) |
| `diff_line_limit` | `max_lines` | Total diff under limit (minimal-fix check) |

- Custom checks subclass `Check`. The manifest lists them by module path; the module ships with the task.
- **No check may call an LLM.** If you need judgment, that's the judge's job, not a check's.

## 3. How checks bind to rubric criteria

In the manifest:

```json
"deterministic_checks": [
  {"id": "vendors_named", "check": "regex_all",
   "params": {"patterns": ["{{vendor_a}}", "{{vendor_b}}", "{{vendor_c}}"]},
   "caps": {"correctness": 25, "completeness": 15}}
]
```

- `caps`: if this check fails (score < 1.0), the listed criteria cannot exceed the given value, regardless of the judge's opinion. A failed check is a ceiling, not a score.
- Multiple failures: the lowest cap wins per criterion.
- The judge sees all check outcomes before grading (per `03-judge.md`).

## 4. Server replay

1. Submission includes transcript hashes + task set version + seed.
2. Server fetches the pinned check code for that task set version (git tag `tasks/v1.2.0`).
3. Server renders the instance with the submitted seed (deterministic — same seed, same instance).
4. Checks run in the sandbox against the submitted deliverable artifact (referenced by hash; submitter hosts it).
5. Recomputed check scores must match the claimed scores exactly. Any mismatch = rejection + public log.

## 5. Writing a good check (authoring rules)

1. Every check must be **instance-aware** (use `task_params`, never hardcode the example from the task brief).
2. Every check must have been **seen to fail**: the author runs it against a deliberately broken deliverable and confirms it catches the break.
3. Checks test the deliverable, never the transcript. How the agent got there is the judge's domain.
4. If a check is flaky (network, timing), it is not a check. Make it deterministic or delete it.
