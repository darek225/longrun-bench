# Phase 3 and Phase 4 audit (SPEC.md §10)

Audited 2026-10-20 against the built tree, in the style of
`docs/DEFINITION_OF_DONE_AUDIT.md`. DONE means built and evidenced in
`docs/TEST_LOG.md`; EXTERNAL means the blocker is people or deployment,
not code.

## Phase 3: first official monthly run, paid evaluations, enterprise API

| Item | Status | Evidence |
|---|---|---|
| Monthly official run tooling | DONE | `scripts/monthly_run.py`: config-driven batch over configurations x tasks x seeds, ingested through signature verification and server-side check replay; runbook `docs/runbooks/monthly-official-run.md` |
| First official monthly run | DONE (dry run) | 2026-10 dry run per docs/plan/05 §3 (first run is a dry run, scores marked preliminary): 2 scripted configurations, 9 runs each, mean 98.58, report at `docs/monthly-runs/2026-10-dry-run/`. A run with real vendor configurations is an operations event, not a build item. |
| Paid evaluations | DONE (system) | Public flat price list ($2,500/level) at `leaderboard/prices.json` + `docs/pricing.md`, served at `GET /api/pricing` and on the board pricing page; order ledger in `leaderboard/orders.py` with a strict lifecycle and payment recorded by reference. No real charge is processed by this code, by design. Selling the first evaluation is external. |
| Priority verification (paid) | DONE | Order kind `priority_verification`: requester-set fee, recorded as payable in full to the completing verifier (org cut zero, docs/plan/06 §4); fulfillment draws priority lottery jobs. |
| Enterprise API | DONE | `leaderboard/enterprise.py`: key-gated history (incl. superseded rows), bulk export with CI data, head-to-head compare with cross-profile/cross-level refusal and cross-version `approximate` marking. Keys are hash-only at rest, shown once, revocable. First paying buyer is external. |
| Sponsored task categories | RULES ONLY | Disclosure, 1-quarter quarantine, and no-sponsor-rubric rules recorded in `docs/pricing.md` (SPEC.md §9). No sponsor exists; there is nothing to enforce against yet. |

## Phase 4: Ultra level live

| Item | Status | Evidence |
|---|---|---|
| Persistent-memory harness | DONE | Memory file seeded for Ultra runs (Phase 2) and preserved across sessions; session snapshots in `harness/src/longrun/sessions.py` |
| Multi-day run ops: session pause/resume | DONE | Driver session mode with cumulative step/token/wall-clock budgets, one transcript per run, `--session-steps` / `--resume` on `run` and `run-scripted`, exit code 3 on pause; runbook `docs/runbooks/ultra-ops.md` |
| Abandoned runs | DONE | `longrun abandon` grades what exists, flags the record, and produces a submittable bundle (docs/plan/09 §4) |
| Ultra goes live | EXTERNAL | The machinery is live in the harness. A populated Ultra board needs real multi-day runs by real agents, which is participation, not code. |

## What "built" means here

Every Phase 3/4 item the build controls is done and tested: harness 56
passed, leaderboard 26 passed. The remaining work across all phases is
the same external list as the Phase 2 audit: the human judge-calibration
panel, real community submissions and verifiers, real vendor evaluations
and enterprise buyers, counsel review, the Docker image build on
Docker-capable hardware, and the fresh-machine quickstart.
