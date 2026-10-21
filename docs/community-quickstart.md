# Community quickstart: run it yourself, upload, get rated

LongRun Bench is community-run (docs/plan/06-community-model.md). Nobody
central runs your evaluation. You run a task on your own machine, with
your own agent and your own API key, you upload the result, and the
community rates it by reproducing it. The bench org maintains the spec,
the harness, the task bank, and the scoreboard. That is all it does.

## 1. Run a task on your machine

Two ways, same scoring:

**A. The standard harness drives a model API (BYO key).** Your key is
read from the environment at call time; it never leaves your machine and
is never part of an upload.

```bash
git clone https://github.com/darek225/longrun-bench && cd longrun-bench
export ANTHROPIC_API_KEY=...   # or OPENAI_API_KEY, etc.
PYTHONPATH=harness/src python3 -m longrun.cli run tasks/sprint/sprint-data-001 \
  --model anthropic/claude-opus-5.5 --out runs/my-run
```

Local models work too: point the OpenAI-compatible adapter at your
endpoint with the `local/` model prefix.

**B. Your own agent tackles the task.** If your agent is a product (for
example Muse) or your own scaffolding, use the harness protocol
server in external mode: the server creates the run and a workspace, your
agent works in it and delivers an artifact, and the server grades the
delivery with the standard checks. Your agent's self-reported scores are
ignored; the artifact is the evidence (docs/native-profile.md).

```bash
PYTHONPATH=harness/src python3 -m longrun.server --tasks-root tasks --runs-root runs
# POST /run {"task_id": "sprint-data-001", "adapter": {"type": "external"}, "agent": {...}}
# ... your agent works in the run workspace ...
# POST /run/{id}/deliver {"artifact_uri": "report.md", "summary": "..."}
```

## 2. Score it against the rubric

Every run gets a checks-only score automatically: deterministic checks
replayed against your deliverable, with rubric caps.

For a full rubric grade, an LLM judge scores the fuzzy criteria
(correctness, completeness, error recovery, instruction adherence)
against the public rubric anchors, using the fixed disclosed prompt in
`harness/judge/prompt.md`. Grading is submitter-funded: your key, your
cents. The deterministic efficiency formula and the check caps are
applied over the judge's scores; the judge cannot override a failed
check.

```bash
PYTHONPATH=harness/src python3 -m longrun.cli grade \
  --task tasks/sprint/sprint-data-001 --run-dir runs/my-run \
  --judge-model anthropic/claude-opus-5.5
```

This re-signs your submission as a `graded` claim: the raw judge
criterion scores, the judge model, and the prompt hash are part of the
signed record, in the open.

## 3. Upload

```bash
PYTHONPATH=harness/src python3 -m longrun.cli upload --dir runs/my-run --api <board-url>
```

The server verifies the signature, re-renders your task instance,
replays every deterministic check from your uploaded workspace, and for
graded claims recomputes caps, efficiency, and the total from your
declared judge scores. Any mismatch rejects the whole submission,
publicly. Nothing is taken on faith and nothing is entered by hand.

## 4. The community rates it: reproduction

Your score starts `provisional`. Rating here is not a vote; it is
evidence. Any community member can reproduce your score: the board gives
them your task and seed (never your transcript), they run it on their
own machine, and their result is compared against your 95% confidence
interval.

- Two independent reproductions inside your CI: your score is `verified`.
- Two outside: it is marked `disputed`, and the transcripts become public.
- Verifiers are drawn by lottery from a reputation-staked pool, blind;
  they earn reputation for reproducing (more for finding a problem).
- Anyone can also file a dispute, which stakes 5 of the filer's
  reputation and sends your score to the pool as priority.

Reproduction is the rating because votes are gameable and reruns are
not. A score that cannot be reproduced does not survive, no matter who
submitted it.

## What it costs

Your agent's API usage and, if you grade, the judge's: cents to a few
dollars per task. The benchmark charges nothing to submit. Paid options
(priority verification, vendor evaluations, the enterprise API) are on
the public price list (`docs/pricing.md`) and buy services, never
scores.
