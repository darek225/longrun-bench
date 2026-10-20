# 09 — Remaining Details

Everything that didn't fit elsewhere, specified anyway.

## Decisions

- **Efficiency formula:** fixed and public, in code, never tuned per task.

## 1. Transcript schema (exact)

```jsonl
{"t": "2026-10-19T20:00:00Z", "type": "run_start", "run_id": "uuid",
 "agent": {"name": "x", "model": "y", "profile": "standard"},
 "task": {"id": "m-01", "instance_seed": 42, "task_set": "1.0.0"},
 "harness": {"version": "1.0.0", "hash": "sha256:..."},
 "budgets": {"steps": 100, "wall_clock_minutes": 180}}
{"t": "...", "type": "prompt", "step": 0, "text_hash": "sha256:..."}
{"t": "...", "type": "tool_call", "step": 7, "tool": "shell.exec",
 "args_hash": "sha256:...", "result_summary": {"exit_code": 0, "chars": 412},
 "duration_ms": 830}
{"t": "...", "type": "deliverable", "step": 64, "artifact_hash": "sha256:...",
 "artifact_uri": "ipfs://..."}
{"t": "...", "type": "run_end", "step": 64, "reason": "deliverable|budget|error",
 "totals": {"steps": 64, "wall_clock_s": 5420, "input_tokens": 182000, "output_tokens": 41000}}
```

- Args and outputs are hashed, not embedded (keeps transcripts small; full logs stay with the submitter and can be requested in disputes).
- `result_summary` is structured per tool, never free text (prevents prompt-injection via tool output from reaching the judge unchecked).

## 2. Efficiency scoring (exact formula)

```
steps_ratio  = steps_used / step_budget          # 0..1 (can exceed 1 only via deliverable at exactly budget)
tokens_ratio = total_tokens / (budget_tokens)    # budget_tokens = step_budget * 4000 (empirical mean)
time_ratio   = wall_clock_s / (wall_clock_budget_s)

efficiency_raw = 1 - (0.5*steps_ratio + 0.3*tokens_ratio + 0.2*time_ratio)
efficiency_score = clamp(efficiency_raw, 0, 1) * weight  # weight = 15
```

- An agent that finishes in half the budget with full marks elsewhere gets ~7.5 bonus points over one that uses the full budget. Correctness still dominates: efficiency is capped by the correctness score (efficiency_score *= correctness/weight_correctness).
- The 4000-tokens-per-step constant is reviewed quarterly against observed data and versioned with the task set.

## 3. Version migration

- MINOR (quarterly): new tasks added, old tasks retired per the rotation schedule. Scores comparable; the board shows task set version per row.
- MAJOR: rubric structure, harness tools, or judge model changes. The board forks: `/v1` stays live and frozen, `/v2` starts empty. Vendors re-run. No score is ever rewritten into a new version.
- The migration guide for each MAJOR version documents exactly what changed and why, with calibration runs showing the old and new judge on the same transcripts.

## 4. Ultra level operations (community-run)

Multi-day runs coordinated by volunteers need structure:

- The runner commits to a schedule (e.g., 3 sessions over 48h). The harness enforces session boundaries: at each boundary the container pauses, state snapshots, and the runner resumes with the memory file intact.
- If a runner abandons mid-task, the partial transcript is submittable as `abandoned` — graded on what exists, flagged, and it still counts for the runner's participation stats (abandoning is data).
- Session pause/resume is the feature that makes Ultra community-runnable. Without it, only vendors with dedicated infra could play.

## 5. Minimum viable participation

A solo dev with a laptop can:
1. `docker pull longrun/harness:1.0.0` (~500MB).
2. Run one Sprint task (~15 min, a few cents of API).
3. Submit the signed transcript → checks-only score on the board.

No account beyond GitHub. No cost beyond the agent's own API usage. This is the onboarding funnel, and it must work on the first try. The quickstart is tested on a fresh machine before every release.

## 6. Metrics for the benchmark itself

The benchmark is instrumented like a product:

- **Discrimination index** per task: variance of scores across agents. Near-zero variance = the task doesn't discriminate = revise or retire.
- **Judge agreement rate:** % of judge grades within ±5 of human audit. Published quarterly. Below 85% triggers recalibration.
- **Reproduction rate:** % of verification attempts that confirm. Below 90% suggests transcript fraud or harness nondeterminism — investigated, not ignored.
- **Canary gap distribution:** the generalization gap across all verified scores. The benchmark is healthy when most gaps are small and the occasional large one gets investigated publicly.

## 7. Legal

- **Terms:** submissions grant the bench org a perpetual license to publish the score, the redacted transcript hashes, and the task breakdown. Submitters retain all other rights.
- **Flags:** generalization-gap flags and fraud removals are statements of measured fact with published methodology. Vendors get 14 days to respond before publication. Counsel reviews the flag policy before launch.
- **Entity:** operate as an unincorporated project until revenue exists. If the enterprise API launches, form an LLC. Not before.
- **No warranties:** scores are measurements under stated conditions, not endorsements or safety certifications. The methodology page says this in plain language.
