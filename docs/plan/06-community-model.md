# 06 — Community-Run Operating Model

## Decisions

- **The community board is the real board.** There is no central "official" evaluation pipeline. The bench org's job is to maintain the spec, the harness, the task bank, and the scoreboard — not to run evals.
- **Verification by reproduction, not by authority.** A score becomes "verified" when an independent party re-runs the same seed and lands within the reported confidence interval. Two independent reproductions = verified badge.
- **Fixed cost target:** under $50/month total, ideally under $15. Every design choice below serves this number.
- **The bench org never pays for agent compute.** Not in phase 1, not ever.

## 1. What the bench org actually runs

| Service | Implementation | Cost |
|---|---|---|
| Scoreboard site | Static Next.js on Cloudflare Pages | $0 |
| Score database | Postgres, Supabase or Neon free tier (scores are kilobytes) | $0 |
| Ingestion API | Serverless function, replays deterministic checks from transcripts | $0-5/mo |
| Transcript storage | Content-addressed; submitters host their own (IPFS, R2, S3) — only hashes on the board | $0 |
| Domain | One domain | ~$12/yr |
| **Total** | | **~$10-50/mo** |

## 2. Who pays for what

| Cost | Paid by |
|---|---|
| Agent compute for a run | The runner (vendor, enthusiast, researcher) |
| LLM judge grading | The submitter (cents per run), or bring-your-own API key, or accept checks-only scoring |
| Human audit | Only for disputes; the disputing parties split the cost |
| Verification re-runs | The verifier (volunteers earn reputation; vendors pay for priority verification) |
| Everything else | Nobody — it doesn't exist |

## 3. Score tiers

Not every score needs full grading. Three tiers, all on the same board, clearly labeled:

| Tier | What's graded | Cost to submitter | Label |
|---|---|---|---|
| Checks-only | Deterministic checks, replayed by the server | Free | `checks` |
| Full | Checks + LLM judge on fuzzy criteria | Judge compute (~$0.05-0.50/run) or BYO key | `graded` |
| Verified | Full, plus 2 independent reproductions | Reproduction compute by verifiers | `verified` |

- Checks-only scores are real and rankable; they just don't have rubric nuance. Most community runs will be checks-only.
- A `graded` score without verification is still self-reported hardware; the label says so.

## 4. The verification protocol

1. Runner submits: signed transcript hashes, task set version, harness hash, seed, claimed score.
2. Server replays deterministic checks from the transcript. Mismatch = rejection, public.
3. Score appears as `provisional` (checks or graded).
4. Any logged-in user can click "reproduce": the site gives them the seed + task instance. They run it on their own hardware and submit their transcript.
5. If the reproducer's score falls within the original 95% CI, that's one confirmation. Two confirmations = `verified`.
6. If reproduction lands outside the CI twice, the score is flagged `disputed` and both transcripts are public for inspection.

Verifiers earn reputation points (see §6). Vendors can pay a priority fee to jump the verification queue; the fee goes to the verifier who completes it, not the bench org.

## 5. Time-based canary (replaces secret held-out tasks)

The spec's secret canary set (§7.3) requires a trusted secret-holder — centralization. Community model replaces it:

- Tasks are timestamped on addition. The **generalization gap** = mean score on tasks added in the last quarter minus mean on older tasks.
- New tasks are the canary. No secrets, no trustees, same signal: training on the public set shows up as a gap favoring old tasks.
- The gap is computed automatically from the timestamps already in the manifest. Zero infrastructure.

## 6. Reputation and governance

- **Contributors** earn reputation: task authorship (accepted PR), verifications completed, judge calibration contributions, bug reports on the harness.
- **Maintainers** are contributors with sustained reputation, granted merge rights by existing maintainers. No elections, no bureaucracy: do the work, get the rights.
- **Task bounties without money:** bountied tasks are marked on the task board; authors get prominent credit and reputation multipliers. Reputation converts to: verification priority, early access to new task quarters (1 week), and a public author leaderboard.
- **Disputes:** resolved by reproduction first. If reproduction is inconclusive, a 3-maintainer panel reviews both transcripts; decision published with reasoning. Panel members recuse on conflicts.

## 7. What "the bench org" means now

A GitHub org, a domain, and 2-3 maintainers with merge rights. Not a company, not a payroll. If revenue ever materializes (enterprise API, priority verification fees), it funds infrastructure first and task bounties second, decided in the open.
