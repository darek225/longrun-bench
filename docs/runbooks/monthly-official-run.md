# Monthly official run

Process: SPEC.md §10 (Phase 3), docs/plan/05 §3 (first official run is a dry
run, scores marked preliminary). Code: `scripts/monthly_run.py`.

An official run is a batch over agent configurations. Every configuration
runs the selected tasks at n>=3 seeds (SPEC.md §6.2) and the results are
ingested onto the `official` board through the standard path: signature
verification and server-side check replay. There is no other way for a
score to reach the official board; never hand-enter one.

## Running a batch

1. Write a config (see `scripts/monthly-runs/2026-10-dry-run.json` for the
   shape): label, board, seeds, task dirs with pinned params, and the agent
   configurations. Real vendor runs use `longrun run` per task into run
   directories and ingest the bundles; the batch script drives the same
   ingestion for scripted configurations.
2. Execute:

```bash
python3 scripts/monthly_run.py --config scripts/monthly-runs/<run>.json \
    --db leaderboard.db --tasks-root tasks \
    --out docs/monthly-runs/<run> --workdir /tmp/monthly-run-work
```

3. Commit the generated `report.md` / `report.json` under
   `docs/monthly-runs/<run>/` with the work log entry.

## Dry runs

A dry run sets `"preliminary": true` and uses the task bank's scripted
solvers as configurations. Its report carries the PRELIMINARY banner and
the scores are machinery evidence only. The 2026-10 dry run
(`docs/monthly-runs/2026-10-dry-run/`) is the template: two scripted
configurations, 3 Sprint tasks, 3 seeds, 9 runs per configuration, mean
98.58, all replay-verified at ingestion.

## Paid evaluations

A vendor evaluation under an order (see `docs/pricing.md`) runs exactly
like any other official batch. Fulfillment links the order to the score
row ingestion produced (`POST /api/orders/{id}/transition` with
`status=fulfilled` and the `score_id`). The order never influences the
run, the grading, or the row.
