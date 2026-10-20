# Verification lottery ops

Protocol: docs/plan/07 §2 and docs/plan/15 §6. Code: `leaderboard/trust.py`.

## Steady state

- Verifiers opt in with `POST /api/verifiers/opt-in` (requires a reputation
  balance of at least 10; the pool is a stake, not a signup form).
- Verification is requested with `POST /api/scores/{id}/request-verification`
  (and automatically, as priority, when a dispute is filed). Two verifiers
  are drawn uniformly at random, excluding the submitter's org.
- Jobs carry a 7-day TTL. A verifier submits reproduction bundles with
  `POST /api/verification-jobs/{id}/submit`; bundles are replayed by the
  ingestion checker before they count.
- Two independent reproductions inside the score's 95% CI mark it
  `verified`; two outside mark it `disputed`. Rewards: +5 for an inside
  reproduction, +10 for an outside one (finding problems pays more).

## Expiry sweep

Run at least daily (cron or a timer):

```bash
curl -X POST http://localhost:8787/api/admin/expire-verification-jobs
```

Each past-due assigned job expires, its verifier is docked 2 reputation, and
a replacement is drawn (never the just-expired verifier for that draw).

## Pool shortfall

A request can return `pool_shortfall > 0` when fewer than two eligible
verifiers exist (org conflicts and live jobs shrink the pool). The score
stays provisional. Do not lower the bar to fill slots: recruit verifiers
instead. Reputation sources are task authorship (+10), calibration (+5),
bug reports (+3), and verifications themselves.
