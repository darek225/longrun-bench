# Ingestion incidents

The ingestion API (`leaderboard/ingest.py`) verifies every submission before
anything reaches the board. A rejection is the system working, not an outage.
This runbook is for triaging rejection patterns.

## What a submitter sees

`POST /api/scores/submit` returns 400 with one of:

| Error starts with | Meaning | Submitter fix |
|---|---|---|
| `submission signature does not verify` | The signed manifest was altered after signing, or signed with a different harness key | Re-run; do not hand-edit submission.json |
| `transcript hash does not match` | The transcript in the bundle is not the transcript that was signed | Upload the run directory as produced (`longrun upload --dir`) |
| `unknown task_id` | Task not in the server's task bank | Check the task set version; the server may be on an older bank |
| `check replay mismatch` | The server's replay of a check disagrees with the claim | See below |
| `total mismatch` | Replayed total differs from the claimed total beyond rounding | Re-run with the matching harness version |

## Replay mismatch triage

1. Confirm harness versions match: the submission records the harness
   version and hash; the checker code is shared, so a version skew is the
   usual cause.
2. Reproduce locally: run the same task and seed with `longrun run`, then
   `longrun check` the produced workspace. If local replay agrees with the
   server, the bundle was corrupted or hand-assembled.
3. If local replay agrees with the *submitter*, that is a real checker bug:
   file it (reputation-worthy, see docs/plan/06 §6), and do not hand-admit
   the score. Scores are never hand-entered.

## Rejection storm (many submitters at once)

Almost always a task-bank or harness release that changed check behavior
without a version bump. Freeze submissions by stopping the API, roll the
bank/harness back to the last green CI state, and re-run
`python3 tasks/validate_bank.py` before reopening.
