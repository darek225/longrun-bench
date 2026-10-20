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
