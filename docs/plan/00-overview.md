# LongRun Bench — Master Build Plan

This directory is the complete plan to take LongRun Bench from spec (Phase 1, done) to a live benchmark with a populated leaderboard (Phase 3). Every document here is buildable as written.

## Documents

| File | Contents |
|---|---|
| `01-harness.md` | Standard harness: Docker image, tool implementations, protocol, step counting, network policy |
| `02-task-bank.md` | Task authoring guide, manifest schema reference, 15 fully-specified exemplar tasks, generation plan for the remaining 70 |
| `03-judge.md` | The LLM judge: exact prompt, calibration methodology, disagreement handling, cost |
| `04-leaderboard.md` | Leaderboard site: architecture, database schema, API endpoints, page specs, anti-tamper |
| `05-operations.md` | Run operations, infrastructure, cost model, timeline, milestones, risk register |

## Target repo layout (end of Phase 2)

```
longrun-bench/
  SPEC.md
  README.md
  LICENSE
  docs/
    DECISIONS.md
    plan/
  harness/
    Dockerfile
    pyproject.toml
    src/
      tools/        # shell, file, python, http, browser
      protocol/     # /run and /transcript server
      judge/        # judge prompt, calibration set
      netpolicy/    # per-task allowlist enforcement
    tests/
  tasks/
    sprint/         # 40 task dirs
    marathon/       # 30 task dirs
    ultra/         # 15 task dirs
    _heldout/       # 17 canary tasks (NOT in public repo; private mirror)
    _archive/       # retired tasks
  leaderboard/
    site/           # Next.js app
    api/            # score ingestion, verification
    schema.sql
  ops/
    runbooks/       # official run procedure
    cost-model.md
```

## Decision log

All Phase 2 decisions are recorded in the relevant plan doc under "Decisions." The rule from Phase 1 holds: if a question could be asked, the answer is written down.
