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

## 2026-10-20 — Phase 2 slices 2-4: runner, protocol server, judge

- **Slice 2 (runner, `docs/plan/10-runner-flow.md`):** provider adapters (`adapters.py`): OpenAI-compatible (covers OpenAI/DeepSeek/xAI/Together/local endpoints), Anthropic, and Google AI, behind a `provider/model` factory; keys read from the environment at call time only, never logged or uploaded; 429 backoff per the plan. The driver now records assistant tool-call entries in history so provider APIs receive valid conversations. `pricing.py` + `harness/pricing.json` (pre-run estimate, post-run actuals), `redact.py` (key-shaped string redaction for transcripts), `signing.py` (submission manifest: transcript hash + score claim + sha256/HMAC signature; the upload payload contains hashes only). CLI gains `run` (fails before step 1 without a key), `redact`, and `upload`; every run now also writes `submission.json`.
- **Slice 3 (protocol server, `docs/plan/01-harness.md` §5):** `server.py` implements POST /run, GET /run/{id}/status, GET /run/{id}/transcript, POST /run/{id}/deliver over stdlib HTTP. Scripted/model modes run the driver server-side; external mode is the native/bare path: the run waits for a delivered artifact and the server grades it with the standard checks (vendor-reported scores are ignored, per spec).
- **Slice 4 (judge, `docs/plan/03-judge.md`):** `judge.py` with the exact v1 judge prompt in `harness/judge/prompt.md`; the judge scores the fuzzy criteria, efficiency stays the deterministic spec formula, and check caps are enforced server-side over judge scores. Flags pass through; the 5%-of-run-tokens judge cost rule is computed and reported. `MockJudge` (clearly labeled test double) exercises the pipeline; `run_calibration` computes ±5 agreement and bias against hand-graded entries. CLI gains `grade` (with `--mock-judge` for pipeline testing).

Deliberately not in this slice (later Phase 2 work, in plan order):

- `browser.task` implementation (still an explicit not-implemented result).
- Judge calibration set with real human grades (machinery built in slice 4; the 30-transcript human panel is an external step).
- The remaining ~82 tasks (`docs/plan/14-task-generation.md`) and trial-grading/discrimination passes.
- The leaderboard site and ingestion API (`docs/plan/04-leaderboard.md`).
- Docker image build verification: the Dockerfile follows the plan, but this dev VM cannot run a Docker daemon, so the image build is unverified until run on a Docker-capable machine.

## 2026-10-20 — Phase 2 slice 5: task bank to 85 tasks

- **`tasks/generate_bank.py`** — family-based generator (`docs/plan/14-task-generation.md`): 22 family builders emit 82 generated tasks alongside the 3 slice-1 seeds, each with `task.md`, `manifest.json`, `rubric.md`, frozen fixtures, and a `smoke-script.json` scripted solver that genuinely does the pinned instance's work from the fixtures (no canned answers). Writes `tasks/bank_index.json` and asserts the exact level counts: Sprint 40, Marathon 30, Ultra 15.
- **Families:** vendor comparison (6), buggy-repo repair (5), crash-fix (4), sales/invoice/inventory/traffic/support data analysis (7), planning quotes (5), web extraction (8, frozen HTML), research briefs and source dossiers (8), trip and conference travel planning (7), teardowns (5), feature/tool builds (7 code tasks incl. rate limiter, audit log, search index), marathon data joins (3), event planning (3), multi-page web with planted index/detail price contradictions (2), ultra market-entry dossiers with staged memory.md (5), relocations with a mid-task budget cut (2), quarter closes with corrections (2), scored procurements (2), and full-stack/migration builds (4).
- **Ground truth discipline:** every parameterized family derives its truth from the drawn parameters via `derived_params`; truth tables for the Q2/Q3 sales datasets were verified by an independent recomputation script (0 mismatches). Known traps fixed during authoring: regex patterns must not start with `$` (regex anchor), `numeric_within` labels must not collide with earlier words (e.g. "subtotal" before the total line), and split-deliverable tasks grade the artifact that actually carries the checked claims (procurement memo vs matrix.csv).
- **`tasks/validate_bank.py`** — the authoring-gate sweep (`docs/plan/14` §9): for every task it validates and renders two seeds, runs the scripted solver on the pinned instance through the real driver (every deterministic check must pass), then runs a garbage-deliverable control in a fresh fixture workspace (at least one check must fail: the seen-to-fail requirement). Results land in `tasks/PROGRESS.md`.

## 2026-10-20 — Phase 2 slice 6: leaderboard, ingestion API, board site

- **`leaderboard/schema.sql`** — Postgres schema per `docs/plan/04-leaderboard.md` §1: append-only `scores` with a `supersedes` chain, `task_scores`, `run_manifests` (content-addressed transcript hashes only; submitters host bytes, per `docs/plan/06`), `disputes`, plus slice-7 tables `verifications` and `reputation` declared up front. Tier (`checks`/`graded`/`verified`) and lifecycle `status` are columns, and `gap_flag` renders unconditionally.
- **`leaderboard/store.py`** — reference store (SQLite mirror of the schema) with the aggregation rule from doc 04: a board row ranks by the mean of per-task mean scores (a config cannot farm one easy task with many runs), 95% CI over per-task means, median, provisional when any task has <3 runs, and a new row superseding the previous latest row for the same (agent, model, profile, level, task_set, board).
- **`leaderboard/ingest.py`** — the load-bearing integrity path (doc 04 §2): a submission is a set of run *bundles* (signed submission manifest + run record + raw transcript + workspace files). The server verifies the signature, checks the transcript hash against the signed manifest, re-renders the task instance, materializes the workspace in a temp dir (with path-escape rejection), and **replays the deterministic checks with the same checker code as the harness**. Any check outcome or total mismatch rejects the whole submission. The server never trusts a client-computed score.
- **`leaderboard/api.py`** — stdlib HTTP service: `POST /api/scores/submit`, `GET /api/scores` (profile/level/board filters, latest rows only, ranked), `GET /api/scores/{id}` (breakdown + run manifests + verifications + disputes), `GET /api/tasks`, disputes create/list, verification recording, `GET /api/health`, and static serving of the board site.
- **`leaderboard/site/index.html`** — single-page board covering all six doc-04 routes: board (default Marathon/standard, profile × level × board tabs, CI and gen-gap shown per row), score drill-down, task bank, methodology, public dispute log, and submit instructions.
- **Harness:** `longrun upload` now assembles the full replayable bundle from a run directory (`build_bundle` in `cli.py`: submission + run record + transcript + text workspace files, caches/binaries excluded, 200KB per-file cap) and posts it with a `--board` choice. API keys are never part of any bundle artifact.

Deliberately not in this slice: verification lottery assignment, dispute resolution workflow, and reputation awards (slice 7, docs 06/07/15); gen-gap computation needs task added-dates the manifests do not yet carry (gap renders as n/a until then); the Postgres deployment wiring (schema ships; the reference implementation runs on SQLite).
