# Monthly run: 2026-10 official dry run

Generated 2026-10-21T01:12:25Z on the `official` board. Seeds: 42, 43, 44. Tasks: sprint/sprint-data-001, sprint/sprint-vendor-001, sprint/sprint-code-001.

**PRELIMINARY (dry run).** These rows exercise the official-run pipeline end to end with the task bank's scripted solvers. They are machinery evidence, not vendor results, and must not be cited as agent scores.

First run of the Phase 3 monthly-run pipeline. Both configurations use the task bank's scripted solvers, so identical scores across configurations are expected: this run validates the batch, ingestion, and reporting machinery, not agent quality. The pinned task parameters make the drawn instances identical across seeds for these seed tasks; seed variation exercises the run bookkeeping (n=3 per task, SPEC.md §6.2) rather than instance variety.

| Agent | Model | Level | Mean | 95% CI | Median | Tasks | Runs | Tier | Status |
|---|---|---|---|---|---|---|---|---|---|
| scripted-alpha | scripted | sprint | 98.58 | 98.08 to 99.08 | 98.84 | 3 | 9 | checks | provisional |
| scripted-beta | scripted | sprint | 98.58 | 98.08 to 99.08 | 98.84 | 3 | 9 | checks | provisional |

Scores were ingested through the standard path: signature verification and server-side check replay (leaderboard/ingest.py). No score in this report was entered by hand.
