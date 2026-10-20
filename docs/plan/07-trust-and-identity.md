# 07 — Trust, Identity, and Anti-Sybil

## Decisions

- **No one is trusted by default, including the bench org.** Every trust claim in this system is checkable by a third party.
- **Identity = GitHub OAuth minimum.** Submitting scores requires a GitHub account older than 30 days with at least 5 public contributions. This kills drive-by spam; it does not stop determined Sybils (see below).
- **Sybil resistance comes from cost, not identity.** Faking a good score requires faking a transcript that passes server-replayed deterministic checks AND survives reproduction. That costs as much as earning the score. There is no cheap attack.
- **Vendors get a higher bar:** verified organization identity (domain-verified) for `native` profile submissions.

## 1. Threat model

| Attack | Cost to attacker | Defense |
|---|---|---|
| Submit a fabricated high score | Must fabricate a full transcript whose tool outputs are self-consistent and pass checks | Server replays checks; reproduction exposes it |
| Train on the task set, then submit | Compute cost of training; the time-based canary exposes it | Generalization gap published (§06.5) |
| Flood the board with Sybil accounts | Each account needs 30-day history; each submission needs a plausible transcript | Rate limits per account; transcripts are expensive to fake |
| Bribe a verifier | Verifier is random from the pool; two independent verifications needed | Verifier assignment is blind; collusion needs 3 parties |
| Poison a task via PR | PR needs 2 maintainer approvals + trial grading | Trial grading with 2 agents exposes broken or biased tasks |
| Attack the judge (prompt injection in transcripts) | Judge flags `prompt_injection_attempt`; transcript quarantined | Judge never sees agent identity; flags are public |

## 2. The verification lottery

Verifiers are not self-selected per score (that invites cherry-picking). Assignment:

1. Verifier opts into the pool, stakes reputation (minimum 10 points).
2. When a score requests verification, 2 verifiers are drawn uniformly at random from the pool, excluding anyone who shares an org with the submitter.
3. Verifiers have 7 days. No response = drawn again, reputation docked.
4. Successful verification: +5 reputation each. Failed verification (score doesn't reproduce): +10 (finding problems pays more), score flagged.

## 3. Transcript privacy

Transcripts can contain API keys, personal data, or proprietary prompts. Policy:

- **Submitters redact before submitting.** The harness provides `harness redact` which scans for key patterns (API keys, tokens, emails) and replaces with `[REDACTED]`.
- **Redaction is declared:** the submission manifest lists redaction rules applied. Undeclared redaction discovered on audit = score removal.
- **Deterministic checks must pass on the redacted transcript.** If your redaction breaks the checks, your submission is invalid. This keeps redaction honest.
- **Raw transcripts are never required.** The hash-committed redacted transcript is the evidence. Reproduction uses the seed, not the transcript.

## 4. Dispute process (step by step)

1. Dispute filed on the score page (logged-in user, must stake 5 reputation).
2. Automatic: the disputed score's seed is published to the verification pool as priority.
3. Two fresh reproductions run blind (reproducers don't see the original transcript).
4. If both reproductions land within the original CI: dispute rejected, stake forfeited to the pool.
5. If either falls outside: 3-maintainer panel reviews all three transcripts, publishes reasoning and a final grade.
6. Panel decision is final. All materials stay public.

## 5. What the bench org cannot do

- It cannot alter a score. The scores table is append-only (see `04-leaderboard.md`).
- It cannot hide a generalization gap. The column renders unconditionally.
- It cannot grant a `verified` badge. Only the reproduction protocol can.
- It can: merge task PRs, rotate the task set, ban accounts for proven fraud (with public evidence), and shut down the site. That is the complete list.
