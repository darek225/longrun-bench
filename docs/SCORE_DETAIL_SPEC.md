# Score detail view: spec (2026-11-02, Darek's complaint)

Problem: the board shows a number and nothing else. A visitor cannot see
what the task was, what the rubric is, which checks passed or failed and
why, what the agent produced, or what it did step by step.

## What gets stored

At ingest, `verify_and_replay` already computes everything and discards
it. It now also returns a `detail` object per run, built ONLY from
server-verified data (replayed check outcomes and criteria, never the
claim) plus hash-covered bundle content (the transcript whose sha256 was
verified against the signed submission, and the workspace files the
checks replayed against):

- task: id, category, level, rendered prompt, params, budgets, rubric
  (criterion, weight, anchors)
- totals: steps, input/output tokens, wall clock; end_reason
- checks: id, check type, passed, score, detail, caps (the replayed ones)
- criteria: per-criterion weight, score, caps_applied (replayed/combined)
- deliverable: uri + full text content (or null)
- transcript: parsed events; any single string truncated at 4000 chars
  with a truncation marker (the full transcript stays proven by its hash)

Stored in a new `run_details` table (manifest_id PK, detail JSON),
written inside `insert_score_group`. Scores stay append-only; detail is
write-once with its manifest.

## API

`GET /api/scores/<id>` (existing route) attaches `detail` to each entry
of `run_manifests` when a detail row exists. Runs ingested before this
change have no detail row; the frontend says so plainly on those rows.

## Frontend

Board rows are clickable and route to `#/score/<id>`. The detail view
renders, per score: header (agent, model, profile, level, tier, status,
submitter, mean/CI), then per run:

1. The task: title/category, rendered prompt, seed, parameters.
2. The rubric: criterion bars (score of weight) with caps applied listed,
   plus the rubric anchors for the task.
3. The checks: table with pass/fail, the check's own detail string
   (e.g. "found 56.0 near 'total tax', expected 147.0"), and caps.
4. The run: steps, tokens, wall clock, end reason.
5. The deliverable: full text.
6. The transcript: collapsible step-by-step timeline (tool calls with
   arguments, tool results truncated, model text, errors).

## Acceptance

- Leaderboard tests pass, including a new test: ingest a real bundle,
  GET the score, detail contains the replayed checks, the deliverable
  text, and transcript events.
- Local E2E with the two 2026-11-02 gateway bundles shows both runs'
  tax/length check failures with their detail strings.
- Live: after deploy, both gateway score rows open a working detail view.
