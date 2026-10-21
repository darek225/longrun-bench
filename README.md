# LongRun Bench

The benchmark for long multi-step agent runs.

Every existing AI benchmark measures single answers: one prompt, one response, one score. But that is not how people actually use AI. Real usage is a 40-step run: research, try, fail, recover, verify, deliver. No benchmark measures the actual job. LongRun Bench does.

## How it works

- **Tasks, not questions.** Each task is a long multi-step job (research and write, repair a codebase, plan under constraints) with a public weighted rubric, school-project style. Partial credit everywhere; no pass/fail.
- **Agent profiles, not models.** The unit under test is the agent configuration: `bare` (raw API, no tools), `standard` (fixed harness toolset), or `native` (the product as shipped). Scores never mix across profiles.
- **Levels.** Sprint (under 20 steps), Marathon (20-100 steps), Ultra (100+ steps with persistent memory). Small models can own Sprint; frontier agents fight at Ultra.
- **Gaming-resistant.** Tasks are parameterized templates drawn at run time. Task sets are versioned. Held-out canary tasks detect training on the test set, and the generalization gap is published.
- **Two leaderboards.** Official (bench org runs it, controlled conditions, verified) and Community (self-run with the open harness, signed results, marked unverified).

## Repo map

- `SPEC.md` — the complete technical specification. Start here.
- `docs/DECISIONS.md` — every design question and the answer chosen. If you wonder "why is it this way," the answer is there.
- `LICENSE` — MIT.

## Status

Phase 2 is complete (2026-10-20): the standard harness, provider adapters and BYO-key runner, protocol server, LLM judge with calibration machinery, the full 85-task bank (validation sweep 85/85, discrimination index 1.0), and the leaderboard with signature-verifying ingestion, server-side check replay, the verification lottery, and staked disputes. See `docs/DEFINITION_OF_DONE_AUDIT.md`.

Phase 3 systems are built: the enterprise API (key-gated score history and head-to-head comparisons), the public price list and paid-service order ledger (flat $2,500/level evaluations, pass-through priority verification), and monthly official run tooling, exercised by the 2026-10 dry run (`docs/monthly-runs/2026-10-dry-run/`). Phase 4's session layer is built: Ultra runs pause and resume across sessions with cumulative budgets, a persistent workspace and memory file, and an abandon path that grades what exists. See `docs/PHASE_3_4_AUDIT.md`.

What remains is not code: real vendor evaluations, enterprise buyers, the human judge-calibration panel, counsel review of the legal drafts, a Docker-capable machine to verify the harness image, and a community to submit and verify scores.

## Contributing

Task proposals via pull request against the task manifest schema in `SPEC.md` §3. All tasks are versioned and rotated; see `SPEC.md` §7.
