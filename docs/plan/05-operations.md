# 05 — Operations: Run Ops, Cost Model, Timeline, Risks

> **Superseded in part by `06-community-model.md`.** The bench org does not run evaluations and does not pay for agent compute. This document now covers: what the org operates (the board, not the runs), the community cost model, timeline, and risks.

## Decisions

- **The org operates the scoreboard, not the evaluations.** Runs happen on runners' hardware. The org maintains the spec, harness, task bank, site, and ingestion API.
- **Fixed cost target:** under $50/month total, ideally under $15.
- **Release cadence:** task set MINOR version quarterly (rotation). The board updates continuously as submissions arrive.

## 1. What the org operates (runbook summary)

1. **Quarterly rotation:** task set version locked, new tasks added, retirements per the schedule in `tasks/`. Seeds for the quarter committed (hashed).
2. **Ingestion:** the API verifies harness hashes, replays deterministic checks from submitted transcripts, recomputes scores. Rejections are public.
3. **Verification lottery:** draws verifiers for scores requesting verification (§07.2).
4. **Generalization gaps:** computed automatically from task timestamps (§06.5). Flags raised where thresholds hit; vendors notified (14-day response before publication).
5. **Disputes:** reproduction-first process (§07.4).

## 2. Cost model (community-run)

| Item | Implementation | Monthly |
|---|---|---|
| Scoreboard site | Cloudflare Pages (static) | $0 |
| Score database | Supabase/Neon free tier | $0 |
| Ingestion API | Serverless, check-replay only | $0-5 |
| Domain | 1 domain | ~$1 |
| **Total** | | **~$1-6** |

Who pays for the rest:

| Cost | Paid by |
|---|---|
| Agent compute | The runner |
| Judge grading | The submitter (or BYO key, or checks-only) |
| Human audit | Disputing parties, split |
| Verification re-runs | Verifiers (reputation) / vendors (priority fees) |

- Phase 3 revenue (unchanged from spec): flat $2,500/level vendor evaluations, enterprise API, sponsored task categories. Revenue funds infra first, task bounties second.

## 3. Timeline

| Week | Milestone |
|---|---|
| 1-2 | Harness Docker image + 5 tools + protocol server + tests green |
| 3-4 | Judge prompt + calibration set (30 transcripts, 2 humans) |
| 5-8 | 15 exemplar tasks authored, trial-graded, in repo |
| 9-14 | Remaining 70 tasks via family expansion (parallelizable across authors) |
| 12-16 | Leaderboard site (schema → API → pages) |
| 16 | Task set v1.0 freeze |
| 17-18 | First official monthly run (dry run, scores marked preliminary) |
| 20 | Public launch: board live, methodology published |

Total: ~20 weeks with 1 builder + task authors. The task bank is the long pole; everything else is 6-8 weeks.

## 4. Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| Task bank takes 2× longer | High | Family expansion (§02.4) over hand-authoring; exemplar-first |
| Judge bias discovered post-launch | Medium | Quarterly recalibration is mandatory, not optional; calibration data public |
| Vendor refuses `native` protocol | Medium | Bench org drives the public interface and documents it; score stands with method note |
| Gaming via task leak | Medium | Canary + generalization gap; 14-day response before flagging |
| Legal: vendor disputes a published flag | Low | Flags are factual (numbers + method), response window given, counsel review before launch |
| Benchmark becomes pay-to-win perception | Medium | Flat public pricing, no suppression for sale, open calibration data — the integrity rules ARE the moat |
| A lab trains directly on the harness | Low | Harness is open by design; the canary tasks are what matter, and they are never public |

## 5. What success looks like (12 months)

- 3+ major labs with official scores on the board.
- The generalization gap cited in at least one major model launch.
- An enterprise buyer signed for the API tier.
- Task set v2.0 in progress with community-authored tasks in the mix.
