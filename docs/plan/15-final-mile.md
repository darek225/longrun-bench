# 15 — Final Mile: Native Profile, Legal, Launch Content, and the Rest

## Decisions

- **Native profile v1 is vendor-driven.** The bench org does not build product drivers in phase 2. If a vendor won't implement the protocol, their product isn't on the native board. The board is honest about absence.
- **Legal docs are plain language.** No legalese where plain words work. Counsel reviews before launch; the docs below are the drafts counsel reviews.

## 1. Native profile: the actual design

Two paths, in order of preference:

**Path A — vendor implements the protocol** (`01-harness.md` §5):
The vendor runs `POST /run` against their own agent infrastructure and returns transcripts in the standard JSONL format. The bench org replays deterministic checks from the transcript. The vendor's harness is their product; the transcript format is the contract. Requirements: the transcript must include per-step tool calls with the same event schema (§09.1); the vendor must disclose the method (which product surface, what tools the agent had).

**Path B — bench drives the public interface** (fallback, community volunteer):
A scripted session: the task prompt is pasted into the product's chat UI via automation, the session is recorded (screenshots + exported transcript), tool use is whatever the product does internally. The transcript is reconstructed by hand into the JSONL schema, marked `method: ui_driven`, and the reconstruction notes are public. Scores from Path B are labeled `native (ui-driven)` and never mixed with Path A rows.

- Path B is labor-intensive and doesn't scale; it exists so the board isn't empty while vendors decide. Two Path B scores maximum per product, then the vendor implements Path A or the product stays off the native board.

## 2. Terms of service (draft)

1. Scores are measurements under stated conditions (task set version, harness hash, seed). They are not endorsements, certifications, or safety guarantees.
2. By submitting, you grant LongRun Bench a perpetual, irrevocable license to publish your score, your redacted transcript hashes, and your per-task breakdown. You retain all other rights.
3. Do not submit transcripts you did not produce. Proven fabrication = permanent ban, public note.
4. Do not train on held-out or newly-added tasks for the purpose of inflating your score. The generalization gap is published; train on the public set all you want, the gap will show it.
5. The bench org may remove scores for proven fraud, with public evidence. It may not alter scores for any other reason.
6. Disputes follow the published process. The panel's decision is final.

## 3. Privacy policy (draft)

1. We store: your GitHub identity, your submitted scores, transcript hashes, and redacted transcripts you choose to upload.
2. We never receive your model API keys. The harness redacts key-shaped strings before signing; the upload contains hashes, not keys.
3. Redacted transcripts are public by design (they are the evidence). Redact before submitting; the `harness redact` tool helps, but the responsibility is yours.
4. We use no tracking cookies. Analytics, if any, is self-hosted and aggregated.
5. Data deletion: scores are append-only and cannot be deleted (they are the public record), but your account and future submissions can be removed on request. Revoked scores stay visible as revoked.

## 4. Methodology page (outline — the actual copy ships with the site)

1. "We measure the job, not the answer." (one paragraph)
2. The three levels, in plain words.
3. The three profiles, and why scores never mix.
4. Rubrics: what they are, one worked example with anchors.
5. The time-based canary: new tasks are the tripwire, the gap is public.
6. Score tiers: checks, graded, verified — what each means.
7. "What a score is not": not an endorsement, not a safety certificate, not comparable across versions.
8. Link to SPEC.md for the full technical version.

## 5. FAQ (ships with the site)

1. **How do I run it?** Docker pull, your API key, one command. (quickstart)
2. **What does it cost me?** Your model's API usage, a few cents to a few dollars per task. The benchmark charges nothing.
3. **Can I use a local model?** Yes — point the OpenAI-compatible adapter at localhost.
4. **Why is my score lower than I expected?** Read your rubric breakdown on the drill-down page. Most commonly: incomplete deliverables and unverified claims.
5. **Someone's score looks fake.** Click "reproduce" on their score page. If it doesn't reproduce, the protocol handles it.
6. **Do you sell scores?** No. Flat verification fees and enterprise API in phase 3; the price list is public.
7. **Can I suggest a task?** Yes — PR against the task schema. Trial grading required.
8. **Why three profiles?** Because a raw API and a finished product are different things and comparing them is meaningless.
9. **What happens to my API key?** Nothing. It never leaves your machine.
10. **Who runs this?** A GitHub org and a handful of maintainers. The spec, the harness, and the board are all public.

## 6. Verification lottery: implementation

Lives in the ingestion API:

```sql
CREATE TABLE verifiers (
  user_id TEXT PRIMARY KEY,
  reputation INT DEFAULT 0,
  opted_in BOOLEAN DEFAULT FALSE,
  org TEXT  -- for conflict exclusion
);
CREATE TABLE verification_jobs (
  id UUID PRIMARY KEY, score_id UUID REFERENCES scores(id),
  verifier TEXT REFERENCES verifiers(user_id),
  state TEXT CHECK (state IN ('assigned','submitted','expired')),
  assigned_at TIMESTAMPTZ, due_at TIMESTAMPTZ
);
```

- Draw: `SELECT user_id FROM verifiers WHERE opted_in AND org != $submitter_org ORDER BY RANDOM() LIMIT 2`.
- 7-day TTL; expiry re-draws and docks 2 reputation.
- Confirmation logic compares the reproducer's task means against the original 95% CI (already in `scores`).

## 7. Provider pricing table

`harness/pricing.json`, updated quarterly:

```json
{
  "updated": "2026-10-19",
  "providers": {
    "anthropic/claude-opus-5.5": {"input_per_mtok": 4.0, "output_per_mtok": 20.0, "source": "https://anthropic.com/pricing"},
    "openai/gpt-6": {"input_per_mtok": 10.0, "output_per_mtok": 50.0, "source": "https://openai.com/pricing"}
  }
}
```

- The cost estimator reads this file. Unknown models: the runner supplies `--price-in` and `--price-out`, recorded in the transcript.
- Stale pricing (>1 quarter old) triggers a warning, not a failure.

## 8. Ultra memory file format

```markdown
# Memory — {task_id} — session {n}

## Goals
- [ ] ...

## State
<!-- What is done, what is in progress. Updated every session. -->

## Open questions
<!-- Things the agent still needs to figure out. -->

## Session log
<!-- Append-only: date, what was attempted, outcome. -->
```

- The harness creates it empty at run start and persists it across sessions. The agent may structure it freely; the format above is a suggestion, not a requirement.
- The judge's instruction-adherence criterion includes "maintained usable state across sessions" for Ultra tasks.

## 9. CI plan (repo itself)

GitHub Actions, on every PR:

1. **Harness tests:** `pytest harness/tests/` — tools, budgets, network policy, protocol.
2. **Driver conformance:** mock-adapter sequences (valid, malformed, refusal, silent) — must not hang.
3. **Task validation:** every task dir must have manifest.json (schema-valid), checks.py (imports clean), rubric.md, and ground_truth/ (non-empty). New tasks must include trial transcripts.
4. **Spec links:** every `§` reference in docs resolves to a real section. (A 20-line script.)
5. **Pricing freshness:** warn if `pricing.json` is >1 quarter old.

## 10. Definition of done (project)

The benchmark is "built" when:

- [ ] Harness image builds, all tests green, survives the adversarial/silent mock agents
- [ ] Driver handles all conformance sequences without hanging
- [ ] 85 tasks merged with trial transcripts, discrimination index computed
- [ ] Judge calibrated (±5 on 90% of the 30-transcript set, no systematic bias)
- [ ] Leaderboard site live: board, drill-down, methodology, tasks, submit, disputes
- [ ] 20+ community submissions across 5+ agent configurations
- [ ] First verification lottery completed with at least 3 verified badges
- [ ] Legal docs reviewed by counsel and published
- [ ] Quickstart tested on a fresh machine, first-try success
