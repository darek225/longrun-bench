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

Phase 1: specification. The harness, seed tasks, and leaderboard site are not built yet. See `SPEC.md` §10 (Roadmap).

## Contributing

Task proposals via pull request against the task manifest schema in `SPEC.md` §3. All tasks are versioned and rotated; see `SPEC.md` §7.
