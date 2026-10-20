# Definition-of-done audit (docs/plan/15 §10)

Audited 2026-10-20 against the built tree. Each item is marked DONE with
evidence, or EXTERNAL with the blocker named. Nothing is marked done on
intention.

| # | Item | Status | Evidence |
|---|---|---|---|
| 1 | Harness image builds, all tests green, survives adversarial/silent mock agents | PARTIAL | Tests green: harness 53 passed incl. adversarial malformed-call, silent-model, and persistent-error conformance sequences (docs/TEST_LOG.md). The Dockerfile follows docs/plan/01, but the image build is UNVERIFIED: this dev VM cannot run a Docker daemon. Build command in docs/runbooks/harness-release.md for Docker-capable hardware. |
| 2 | Driver handles all conformance sequences without hanging | DONE | Harness conformance tests (happy path, malformed calls burn budget and end cleanly, silent model 3-strikes, persistent provider errors, text-only nudge, missing-artifact deliver) all pass. |
| 3 | 85 tasks merged with trial transcripts, discrimination index computed | DONE | 85 tasks (40/30/15) committed; full sweep 85/85; trial transcripts kept at tasks/trials/<task_id>/; discrimination index 1.0 (mean solver 99.19 vs mean garbage control 54.40, gap 44.78) in tasks/discrimination.json and tasks/PROGRESS.md. |
| 4 | Judge calibrated (±5 on 90% of the 30-transcript set, no systematic bias) | EXTERNAL | Calibration machinery is built and tested (agreement rate, mean bias, per-entry deltas; MockJudge plumbing tests). The 30-transcript set needs real human hand-grades; fabricating them would invalidate the calibration, so this waits on the human panel. |
| 5 | Leaderboard site live: board, drill-down, methodology, tasks, submit, disputes | DONE (reference implementation) | leaderboard/ serves all six routes plus FAQ, with ingestion that verifies signatures and replays checks server-side; 15 leaderboard tests pass over HTTP. "Live" means running the service (docs/runbooks/leaderboard-ops.md); public hosting/deployment is an ops choice, not a build gap. |
| 6 | 20+ community submissions across 5+ agent configurations | EXTERNAL | Requires a community. The ingestion path they will use is built and tested end to end with real run bundles. |
| 7 | First verification lottery completed with at least 3 verified badges | EXTERNAL | The lottery is built and tested end to end (draw, blind reproduction, CI comparison, rewards, expiry, disputes) with scripted runs. Real badges require real independent verifiers in the pool. |
| 8 | Legal docs reviewed by counsel and published | EXTERNAL | Drafts written in plain language at docs/legal/terms-of-service.md and docs/legal/privacy-policy.md, marked DRAFT. Counsel review is a human step; publishing unreviewed drafts as terms would be worse than not publishing. |
| 9 | Quickstart tested on a fresh machine, first-try success | EXTERNAL | The quickstart path is the harness CLI plus the submit page instructions; a genuinely fresh machine (and a Docker-capable one for the image path) is a human-run test. Everything testable from the dev VM is covered by the suites above. |

## What "built" means here

Every item the build itself controls is done and evidenced in
docs/TEST_LOG.md. The EXTERNAL items are not engineering gaps: they are a
human calibration panel, a community, independent verifiers, counsel, and
a fresh machine. The systems those people will use are the ones tested
above.
