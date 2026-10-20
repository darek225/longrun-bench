# 05 — Operations: Run Ops, Cost Model, Timeline, Risks

## Decisions

- **Official run cadence:** monthly, first Monday. All agents on the board re-run the current task set. Results published within 72 hours.
- **Who operates runs:** the bench org (initially the repo owner + contractors). Runbooks in `ops/runbooks/`.
- **Compute:** cloud VMs per run (isolated), orchestrated by a simple queue worker. No Kubernetes in phase 2; graduate when monthly runs exceed 200.
- **Cost ceiling:** an official monthly run must cost under $5,000 all-in at v1.0 scale (10 agents × 85 tasks × 3 seeds). If it doesn't, cut Ultra to n=2 before cutting anything else.

## 1. Official run procedure (runbook summary)

1. **Freeze:** Friday before run week, task set version locked, canary instances drawn, seeds committed (hashed, revealed after).
2. **Execute:** queue worker fans out runs. Each run: fresh container from pinned harness hash, instance rendered with seed, budgets enforced, transcript stored content-addressed.
3. **Grade:** deterministic checks replayed in code; judge grades fuzzy criteria; 10% human audit sample drawn.
4. **Review:** generalization gaps computed; flags raised where thresholds hit; vendors notified of flags (14-day response window before publication).
5. **Publish:** scores appended to the DB, board updates, methodology notes for anything unusual.

## 2. Cost model (v1.0 estimates)

| Item | Unit cost | Monthly |
|---|---|---|
| Agent compute (API models) | ~$2-8 per Marathon run × 30 tasks × 3 seeds × 10 agents | $1,800-7,200 |
| Judge grading | <5% of agent compute | <$360 |
| Human audit (10% sample) | $15 × ~90 transcripts | $1,350 |
| Infra (VMs, storage, site) | flat | ~$300 |
| **Total** | | **~$3,800-9,200** |

- The ceiling in Decisions assumes mid-range agent costs. If frontier agents cost more, run fewer agents per month (rotation) rather than fewer tasks.
- Phase 3 vendor fees: flat $2,500 per level per evaluation. At 10 vendors × 3 levels quarterly, that is $75k/quarter against ~$20k/quarter in run costs.

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
