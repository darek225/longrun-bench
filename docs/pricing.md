# Public price list (Phase 3)

Source of truth: `leaderboard/prices.json`, served at `GET /api/pricing`
and rendered on the board's pricing page. SPEC.md §9 and DECISIONS.md
#36-38: pricing is public and flat, no pay-for-score, ever.

| Service | Price |
|---|---|
| Vendor evaluation, Sprint | $2,500 flat |
| Vendor evaluation, Marathon | $2,500 flat |
| Vendor evaluation, Ultra | $2,500 flat |
| Priority verification | Fee set by the requester; paid in full to the verifier who completes the reproduction. The bench org takes no cut (docs/plan/06 §4). |
| Enterprise API | Key access to score history, CI data, and head-to-head comparisons (SPEC.md §9.3). |

An evaluation is one level, run as an official monthly-run batch
(`docs/runbooks/monthly-official-run.md`), with scores produced only
through ingestion and check replay.

## Sponsored task categories

Allowed under SPEC.md §9.4 with three hard rules: the sponsorship is
disclosed on the task and the leaderboard, the category sits out the
active set for a 1-quarter quarantine, and the sponsor never authors the
rubric for their own category. No sponsored category exists yet; the
rules are recorded here so the first one is not improvised.

## Never for sale

- Score boosts.
- Leaderboard placement.
- Suppression of a generalization-gap flag.
- Early access to new task quarters beyond the 1-week author window.

Revenue funds infrastructure first and task bounties second
(docs/plan/05 §2), decided in the open. Orders are a public ledger at
`GET /api/orders`.
