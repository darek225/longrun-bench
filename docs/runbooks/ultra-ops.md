# Ultra operations: sessions, pause/resume, abandonment

Process: docs/plan/09-remaining-details.md §4, SPEC.md §2. Code:
`harness/src/longrun/sessions.py`, the driver's session mode, and the CLI
flags below.

Ultra tasks run up to 500 steps over 24 hours. Nobody runs that in one
sitting, so Ultra runs are session-based:

- The runner commits to a schedule (for example 3 sessions over 48h) and
  runs each session with a step cap: `--session-steps N`.
- At the cap, the harness pauses: it logs `session_pause`, snapshots the
  run into `session.json` in the run directory (instance seed and params,
  cumulative steps/tokens/wall-clock, the schedule log), and exits with
  code 3. A paused run has no score and no submission yet.
- The workspace is the continuity: files and `memory.md` persist between
  sessions exactly as the agent left them. Conversation history does not
  carry over; the memory file is the agent's state, which is the point of
  the level (docs/plan/15 §8).
- Budgets are cumulative. Steps, tokens, and wall-clock spent in earlier
  sessions count against the same run budgets. The transcript is one
  record across sessions (`run_start` once, then `session_start` /
  `session_resume` / `session_pause` events, one final `run_end`).

## Commands

```bash
# Session 1: start, capped at 150 steps
longrun run tasks/ultra/<task> --model <provider/model> --out runs/<run> --session-steps 150
# (exit code 3 = paused)

# Session 2: resume the same run directory; seed/params come from session.json
longrun run tasks/ultra/<task> --model <provider/model> --out runs/<run> --resume --session-steps 150

# Final session: resume without a cap; the run ends on deliver/budget/error
longrun run tasks/ultra/<task> --model <provider/model> --out runs/<run> --resume

# Abandon: grade what exists and close the run as abandoned
longrun abandon --dir runs/<run>
```

`run-scripted` accepts the same `--session-steps` / `--resume` flags.

## Rules

- Resume only works on `in_progress` / `paused` sessions, and the instance
  is re-rendered from the snapshot, never from new CLI seed/params. A
  resumed session on a different instance would be a different run.
- Abandoning is data (plan 09 §4): the partial transcript and workspace
  are graded on what exists, the run record is flagged `abandoned`, and
  the bundle is submittable like any other. An abandoned run cannot be
  resumed or abandoned again.
- A `run_end` event with reason `session_pause` marks a session boundary,
  not the end of the run; the run's final `run_end` is the last one.
