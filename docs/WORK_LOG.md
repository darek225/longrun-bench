# Work Log

## 2026-10-20 — Phase 2 begins: harness vertical slice + seed tasks

First build slice of Phase 2, following `docs/plan/` in dependency order (harness core before judge, leaderboard, and the full task bank).

Built:

- `harness/` Python package (`longrun`, zero runtime dependencies):
  - `manifest.py` — loads and validates `manifest.json` (rubric weights must sum to 100, task.md/rubric.md required, at least one check), renders seeded parameterized instances, supports `derived_params` (instance ground truth keyed by drawn parameters) and dotted template lookups like `{{expected.total_revenue}}`.
  - `checks.py` — the check framework from `docs/plan/12-check-dsl.md`: `Result(passed, score, detail)`, built-ins `regex_all`, `regex_any`, `banned_phrases`, `word_count`, `csv_valid`, `json_path`, `numeric_within`, `file_exists`, `file_contains`, `pytest_pass`, `git_diff_empty`, `diff_line_limit`. Checks carry rubric `caps` (a failed check is a ceiling, not a score).
  - `tools.py` — the standard tool surface from `docs/plan/01-harness.md`: `shell.exec`, `file.read/write/edit` (edit requires exactly one match), `python.exec`, `http.fetch` (allowlist enforced), `browser.task` (explicit not-implemented result), `code.nav` (AST-backed list/search symbols, find definition/references; Python at launch, per DECISIONS #40). All file paths are confined to the workspace.
  - `driver.py` — the agent loop from `docs/plan/11-driver.md`: one tool call = one step including errors and `deliver`; schema validation with hint results for malformed calls; text-only nudge after 3 turns; 3-strike model-error and empty-response handling; budget enforcement with an 80% warning; deterministic history compaction; JSONL transcript in the `docs/plan/09` schema (hashed args, structured result summaries). Ships a `ScriptedAdapter` for conformance tests and smoke runs.
  - `scoring.py` — checks-only provisional scoring (tier `checks`): rubric caps applied, no-deliverable zeroes correctness/completeness, efficiency uses the exact spec formula and is capped by the correctness ratio.
  - `cli.py` — `longrun validate-task | render | check | run-scripted`.
  - `Dockerfile` — per plan §01 (image build not yet verified; see below).
- `tasks/sprint/` — three seed tasks built to the authoring checklist in `docs/plan/02-task-bank.md`, each with `task.md`, `manifest.json`, `rubric.md`, fixtures, and a `smoke-script.json` scripted agent:
  - `sprint-data-001` (data_analysis): sales CSV with planted duplicate/future-dated/missing-price rows; ground truth derived per instance.
  - `sprint-code-001` (code_repair): order-preserving dedupe bug with a pytest suite; fix verified by `pytest_pass` inside the run.
  - `sprint-vendor-001` (research_synthesis): offline vendor comparison against a `vendors.json` fixture with per-product derived catalogs.
- `harness/tests/` — 27 tests (manifest, checks, tools, driver conformance, scoring). Every check in the seed tasks has been seen to fail on a broken deliverable (see `docs/TEST_LOG.md`).

Deliberately not in this slice (later Phase 2 work, in plan order):

- Real provider adapters and the BYO-key runner flow (`docs/plan/10-runner-flow.md`) — only the scripted adapter exists.
- The `/run` protocol server for native/bare submissions.
- `browser.task` implementation.
- The LLM judge and calibration set (`docs/plan/03-judge.md`).
- The remaining ~82 tasks (`docs/plan/14-task-generation.md`) and trial-grading/discrimination passes.
- The leaderboard site and ingestion API (`docs/plan/04-leaderboard.md`).
- Docker image build verification: the Dockerfile follows the plan, but this dev VM cannot run a Docker daemon, so the image build is unverified until run on a Docker-capable machine.
