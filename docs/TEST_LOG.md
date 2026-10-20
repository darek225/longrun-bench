# Test Log

## 2026-10-20 — Phase 2 slice 1 verification

Environment: dev VM, Python 3, pytest 9.1.1, harness installed via `PYTHONPATH=harness/src` (no package install, no Docker).

### Unit and conformance tests

- `cd harness && python -m pytest` → **27 passed** in 5.61s.
- Coverage: manifest validation/rendering/derived params, all built-in checks used by the seed tasks, workspace tools (including path-traversal rejection and allowlist enforcement), driver conformance (happy path, malformed calls, silent model, persistent provider errors, text-only nudge, missing-artifact deliver), scoring caps and the efficiency formula.

### Scripted smoke runs (checks tier, provisional)

| Task | Steps | Checks | Correctness | Total |
|---|---|---|---|---|
| sprint-data-001 (region=north, top_n=3) | 3 | 4/4 passed | 40/40 | 98.84 |
| sprint-code-001 (seed 7) | 5 | 4/4 passed | 40/40 | 98.06 |
| sprint-vendor-001 (product=crm) | 3 | 4/4 passed | 40/40 | 98.84 |

- Totals are below 100 purely from the spec efficiency formula (steps/tokens/time vs budget); every deterministic check passed in all three runs.
- sprint-code-001's `pytest_pass` check ran the real suite inside the run workspace: failing before the scripted fix, green after.

### Broken-deliverable control (checks must be seen to fail)

- `longrun check` on sprint-data-001 with a deliberately wrong report ($12 revenue, wrong products, no anomalies): all 4 checks failed; caps applied (correctness 40→20, completeness 25→15, instruction adherence 10→5, efficiency scaled by the correctness ratio); total 56.94; CLI exit code 2.

### Driver abuse cases (from docs/plan/11-driver.md §6)

- Adversarial malformed-call agent: burns the step budget and ends `budget` cleanly, no hang.
- Silent model (empty responses): ends `error` after 3 strikes, 0 steps consumed.
- Persistent provider errors: ends `error` after exactly 3 `model_error` events.

## 2026-10-20 — Phase 2 slices 2-4 verification

- Full suite: **51 passed** (`cd harness && python -m pytest`), up from 27.
- Adapters: OpenAI/Anthropic/Google rendering and response parsing verified against fake transports (tool-call id pairing, strict role alternation for Anthropic, functionCall parsing for Google); missing-key errors name the env var; malformed argument JSON degrades to a driver validation error, not a crash.
- Runner: pricing estimate for anthropic/claude-opus-5.5 at 100 steps = $0.80-$3.20 (matches hand computation); redaction catches sk-, xai-, AIza, ghp_, bearer, and PEM shapes; submission signatures verify and tampering with the claimed total fails verification; `run` without a key exits 1 before step 1.
- Protocol server: scripted run over HTTP returns 201, reaches done with score >95, transcript retrievable; external-mode run waits in `running`, accepts a deliverable, and is graded by the server (score >95 on the vendor-brief fixture).
- Judge: a stub judge awarding 40/40 correctness is capped to 20 by failed checks; MockJudge separates the good data-task report (98+) from the broken one by >30 points; non-JSON judge output is rejected; calibration machinery reports agreement rate and mean bias.

## 2026-10-20 — Phase 2 slice 5 verification (task bank sweep)

- Generator run: `python3 tasks/generate_bank.py` → 85 tasks, level counts {Sprint: 40, Marathon: 30, Ultra: 15}, no duplicate IDs.
- Full sweep: `python3 tasks/validate_bank.py` → **85/85 tasks pass**: every scripted solver passes all of its task's deterministic checks on the pinned instance, and every garbage-deliverable control fails at least one check. Per-task detail in `tasks/PROGRESS.md`.
- First sweep was 58/85; all 27 failures were diagnosed individually (10 solver word-count shortfalls, 1 `numeric_within` label collision with "subtotal", plus smaller variants) and fixed in the generator — never by weakening a check to fit a solver, and never by editing generated output by hand. Fixes regenerated the whole bank.
- Harness suite after slice 5: **51 passed** (unchanged; the bank is data, not harness code).
