# Task bank release

Authoring: docs/plan/02-task-bank.md and docs/plan/14-task-generation.md.

## Adding or changing tasks

1. Generated families live in `tasks/generate_bank.py`. Change the
   generator, never the generated task folders by hand, then regenerate:
   `python3 tasks/generate_bank.py`.
2. Hand-authored tasks follow the same layout: `task.md`, `manifest.json`,
   `rubric.md`, fixtures, and a `smoke-script.json` scripted solver that
   genuinely performs the pinned instance from the fixtures.
3. Ground truth is derived from drawn parameters (`derived_params`), never
   hard-coded per instance. Known traps: regex patterns must not start with
   `$` (regex anchor); `numeric_within` labels must not collide with earlier
   words in the deliverable; the graded deliverable must be the artifact
   that carries the checked claims.

## The gate

```bash
python3 tasks/validate_bank.py
```

Every task must pass: manifest validates, two seeds render, the scripted
solver passes every deterministic check on the pinned instance, and a
garbage deliverable fails at least one check (seen-to-fail). Results land in
`tasks/PROGRESS.md`. A red sweep blocks the release, no exceptions; a
solver/check mismatch is a defect in the task or the solver, and it gets
fixed in the generator.

## Cutting a release

1. Green sweep + green CI.
2. Bump the task set version in the manifests (semver; new tasks or changed
   checks = minor, new level = major).
3. Update `tasks/bank_index.json` (the generator writes it) and commit with
   the sweep results.
4. Scores are pinned to task set versions; old boards keep working because
   ingestion replays against the bank the server is configured with.
