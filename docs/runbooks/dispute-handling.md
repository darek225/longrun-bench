# Dispute handling

Process: docs/plan/07 §4. Code: `leaderboard/trust.py`. All dispute records
are public (`GET /api/disputes` and the board's disputes page).

1. **Filing.** A logged-in user files with `POST /api/disputes`
   (`score_id`, `filer`, `reason`). Filing stakes 5 of the filer's
   reputation; a filer without the stake cannot file. Filing automatically
   sends the score's task+seed set to the verification pool as priority,
   blind: reproducers never see the original transcript.
2. **Reproduction.** Two fresh reproductions run through the normal lottery
   path (`POST /api/verification-jobs/{id}/submit`). Bundles are replayed by
   the ingestion checker before they count.
3. **Panel.** If either reproduction lands outside the original CI, a
   3-maintainer panel reviews all transcripts and publishes reasoning.
   Panel members recuse on conflicts (same org as submitter or filer).
4. **Resolution.** A maintainer records the outcome with
   `POST /api/disputes/{id}/resolve` (`outcome`, `resolution`):
   - `upheld`: the score is marked `disputed`; the filer's stake is refunded.
   - `rejected`: both reproductions held inside the CI; the stake is
     forfeited to the pool.
   - `frivolous`: dismissed; the stake is forfeited.
5. **Finality.** The panel decision is final. The dispute, its reasoning,
   and the score's status stay public permanently.
