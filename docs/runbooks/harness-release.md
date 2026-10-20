# Harness release

## Before merging a harness change

```bash
cd harness && python3 -m pytest -q        # includes driver conformance
python3 -m pytest ../leaderboard/tests -q  # ingestion replays harness checks
python3 tasks/validate_bank.py             # bank still green end to end
```

The checker code is one source of truth: the leaderboard replays with the
same `longrun.checks` module the harness runs. Never fork check behavior
server-side.

## Pricing refresh (quarterly)

`harness/pricing.json` carries per-model input/output prices with an
`updated` date. Refresh quarterly from the providers' pricing pages and bump
`updated`. CI warns when the file is over one quarter old
(`scripts/check_pricing_freshness.py`); stale pricing warns, it never fails
the build. Unknown models fall back to the runner's `--price-in` /
`--price-out`, recorded in the transcript.

## Harness hash

Submissions record the harness version and content hash. When a release
changes scoring-relevant behavior (checks, driver, scoring), note it in
`docs/WORK_LOG.md` with the version bump: boards compare within a task set
and harness lineage, and a silent behavior change would corrupt that.

## Docker image

`harness/Dockerfile` follows docs/plan/01. Build and smoke it on a
Docker-capable machine before calling a release done:

```bash
docker build -t longrun-harness harness/
```

(The usual dev VM cannot run a Docker daemon; image builds are verified on
Docker-capable hardware, and this runbook does not pretend otherwise.)
