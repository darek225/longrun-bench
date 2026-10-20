# LongRun Bench — Technical Specification v0.1 (draft)

## 0. The problem

Benchmarks score models on single answers. People use agents on long jobs. The gap between what is measured and what matters is the entire product surface of agentic AI: sustaining a goal across dozens of steps, recovering from failures, using tools, verifying results, and delivering something complete.

LongRun Bench measures the job, not the answer.

## 1. Definitions

- **Task:** one long multi-step job with a prompt, a parameterized instance, a rubric, and deterministic checks. The atomic unit of the benchmark.
- **Run:** one attempt at one task instance by one agent configuration. Produces a transcript, tool-call log, and score.
- **Agent configuration:** the thing being scored. A model plus a profile (see §4) plus a harness version. Never a bare model name.
- **Rubric:** the scoring sheet for a task. Weighted criteria, each scored 0 to its max with anchor descriptions. Public for every task.
- **Instance:** one concrete parameterization of a task template, drawn with a seed at run time.
- **Task set:** the versioned collection of active tasks. Versioned with semver (see §7).
- **Bank:** the pool of task templates. The active set is drawn from the bank each quarter.

## 2. Levels

Three levels. An agent is scored separately at each; there is no single blended score.

| Level | Name | Step budget | Wall-clock budget | Min tasks in set (v1.0) |
|---|---|---|---|---|
| 1 | Sprint | 20 steps | 15 minutes | 40 |
| 2 | Marathon | 100 steps | 3 hours | 30 |
| 3 | Ultra | 500 steps | 24 hours | 15 |

- A **step** is one tool call. Model-internal thinking does not count. A tool call that errors still counts.
- Exceeding the step or time budget ends the run; the rubric is scored on what exists.
- Ultra tasks span sessions: the harness provides a persistent working directory and a memory file the agent may read and write. Wiping the memory file is allowed; the rubric rewards agents that keep useful state.

**Why three levels:** small and cheap models can meaningfully compete at Sprint, which keeps the benchmark accessible. Frontier agents differentiate at Ultra. One ladder, three rungs, no blending.

## 3. Tasks

### 3.1 Categories

Every task belongs to one category. The v1.0 set balances across all five:

1. **Research & synthesis** — gather from multiple sources, resolve contradictions, produce a structured deliverable.
2. **Code repair & building** — fix, extend, or build software against tests the agent cannot see in advance.
3. **Multi-step planning** — produce a feasible plan under real constraints (budget, time, availability), verified against live sources where applicable.
4. **Data analysis** — clean, analyze, and report on a dataset; numbers must check out.
5. **Web navigation & extraction** — complete a multi-page web task; extracted facts must be sourced.

### 3.2 Task manifest

Every task is a directory containing `task.md` (human brief) and `manifest.json`:

```json
{
  "id": "research-014",
  "level": 2,
  "category": "research_synthesis",
  "version": "1.2.0",
  "quarters_active": ["2026-Q4", "2027-Q1"],
  "prompt_template": "Compare {{n}} vendors of {{product}} for a {{business_type}}...",
  "parameters": {
    "n": {"type": "integer", "min": 3, "max": 6},
    "product": {"type": "enum", "values": ["crm", "accounting_software", "voip"]},
    "business_type": {"type": "enum", "values": ["dental_practice", "food_truck", "law_firm"]}
  },
  "budgets": {"steps": 100, "wall_clock_minutes": 180},
  "rubric": [
    {"criterion": "correctness", "weight": 40, "anchors": {"0": "...", "20": "...", "40": "..."}},
    {"criterion": "completeness", "weight": 25, "anchors": {...}},
    {"criterion": "efficiency", "weight": 15, "anchors": {...}},
    {"criterion": "error_recovery", "weight": 10, "anchors": {...}},
    {"criterion": "instruction_adherence", "weight": 10, "anchors": {...}}
  ],
  "deterministic_checks": [
    {"id": "mentions_all_vendors", "type": "regex_all", "patterns": ["{{vendor_a}}", "{{vendor_b}}"]},
    {"id": "price_table_present", "type": "json_path", "path": "$.pricing_table"}
  ]
}
```

- `prompt_template` uses `{{parameter}}` placeholders. The instance is rendered with a seed at run time (§7).
- `deterministic_checks` run in code against the deliverable. They feed the correctness and completeness criteria but do not replace rubric grading.
- Every task's rubric is public. The instances are not.

### 3.3 Task authorship and rotation

- The seed set is authored by the maintainers. Community proposals come via pull request and require two maintainer approvals plus a trial grading pass.
- A task may be active for at most 4 consecutive quarters, then it retires to the public archive. Retirement is automatic; no vote needed.
- Retired tasks remain runnable for community history but never count toward official scores.

## 4. Agent profiles

The benchmark scores agent configurations, never bare models. Three profiles:

| Profile | What it is | Tools |
|---|---|---|
| `bare` | Raw model API. No tools, no browsing, single response per turn. | None |
| `standard` | Model driven through the standard harness (§5). | Fixed set: shell, file read/write, Python execution, HTTP fetch (text), text-mode browser |
| `native` | The vendor's product as shipped, driven through its own interface. | Whatever the product provides |

Rules:

- Scores are **never compared across profiles**. The leaderboard has one tab per profile. A `bare` 82 and a `native` 82 are different achievements and are displayed separately, always.
- `bare` exists to isolate model capability from agent scaffolding. It is expected that `bare` scores lower; that is the point.
- For `native` official runs, the vendor provides an agent endpoint conforming to the harness protocol (§5.4), or the bench org drives the product's public interface and documents exactly how. The method is published alongside the score.
- The profile, model name and version, harness version, and task set version are recorded with every run. A score without all four is not publishable.

## 5. The standard harness

### 5.1 Implementation

- The harness is a versioned Docker image, open source, MIT licensed, in this repo under `harness/`.
- Every run records the harness image hash. Community results without a matching hash for the task set version are rejected from the community board.
- Network access inside the container is restricted to an allowlist declared per task (e.g., specific documentation domains). Everything else is denied. The allowlist is part of the task manifest.

### 5.2 Tool surface (`standard` profile)

| Tool | Description |
|---|---|
| `shell.exec` | Run a shell command. Timeout 120s. |
| `file.read` / `file.write` / `file.edit` | File operations inside the workspace. |
| `python.exec` | Run Python 3 with numpy, pandas, requests preinstalled. |
| `http.fetch` | GET a URL, return text (markdown-converted). Respects the allowlist. |
| `browser.task` | Text-mode browser task for multi-page navigation. Returns observations. |

No tool may exfiltrate the task manifest, the rubric, or the deterministic checks. The container is rebuilt from the image for every run; nothing persists between runs except the Ultra memory file, which is task-scoped.

### 5.3 Step counting

One tool call = one step, including calls that error or time out. Prompt turns without tool calls do not count. The harness enforces the budget and terminates the run at the limit.

### 5.4 Harness protocol (for `native` and `bare` submissions)

Vendors implementing the protocol expose:

```
POST /run { task_instance, budgets } -> { run_id }
GET  /run/{id}/transcript -> { steps[], tool_calls[], deliverable }
```

The bench org replays the transcript through the deterministic checks independently. A vendor may not self-report check results; the transcript is the evidence.

## 6. Scoring

### 6.1 Rubric grading

- Each criterion is scored 0 to its weight against the anchor descriptions. Anchors describe concrete evidence (e.g., correctness 40/40: "every deterministic check passes and no fabricated facts found on audit").
- Deterministic checks (§3.2) are scored in code and constrain the correctness/completeness grades: a failed check caps the corresponding criterion at the anchor below the failure.
- Fuzzy criteria (efficiency nuance, instruction adherence edge cases, recovery quality) are graded by an LLM judge running a fixed, disclosed model version and prompt (published in `harness/judge/`). The judge sees the rubric, the transcript, and the deliverable — never the agent's identity.
- Official runs: 10% of transcripts (random) plus 100% of disputed runs get human audit. Human grade overrides the judge. Disagreements are published as calibration data.

### 6.2 Aggregation

- Minimum **n=3 runs per task** for an official score (different seeds).
- Task score = mean of runs. Agent level score = mean of task scores, reported with 95% confidence intervals. Median also reported.
- Single-run community scores are accepted but flagged **provisional** until n=3.
- Efficiency is 15% of every rubric and is computed from tokens used, steps used, and wall-clock relative to budget. The cheapest perfect score beats an expensive perfect score, but correctness always dominates: efficiency never compensates for wrong answers.

### 6.3 What a score means

A score of 82 at Marathon/`standard` means: across 30 long tasks, three seeds each, this agent configuration averaged 82/100 against public rubrics. The CI, the task set version, and the harness hash are part of the score. A score without them is a rumor.

## 7. Gaming resistance

A benchmark that can be trained on is a leaderboard of who cheated best. Four mechanisms:

### 7.1 Parameterized instances

Tasks are templates, not fixed prompts. The instance (vendors, numbers, constraints, seeds) is drawn at run time from the parameter schema. Memorizing the task text buys nothing; the agent must do the work.

### 7.2 Versioned task sets

- Task sets use semver: `MAJOR.MINOR.PATCH`.
- MINOR: tasks added or retired (quarterly rotation). Scores remain comparable within a MAJOR version.
- MAJOR: rubric structure or harness changes. Leaderboard resets; previous eras are archived, not deleted.
- Every published score carries its task set version. Cross-version comparisons are marked as approximate.

### 7.3 The canary: held-out tasks and the generalization gap

- 20% of authored tasks are **never published**, never in the repo, never in any prompt. They run only in official evaluations.
- For each official run we publish the **generalization gap**: public-task mean minus held-out mean.
- A large positive gap (much better on public tasks than held-out) is the gaming signal. It is published on the leaderboard next to the score, in the open, with the vendor notified first and given 14 days to respond before the flag goes public.
- Deliberate training on benchmark tasks, if discovered, results in score removal and a public note. The note stays even if scores are later re-earned.

### 7.4 Run integrity

- Official runs execute on bench-org infrastructure. The agent never sees the rubric weights beyond the public anchors, never sees deterministic checks, never sees held-out tasks.
- Community runs are self-reported and **always** labeled unverified. Signed with harness hash + task set version + seed. Anyone can re-run them; the harness is open.

## 8. Leaderboards

One board with three score tiers (see `docs/plan/06-community-model.md` §3). The bench org does not run evaluations; it operates the scoreboard.

| Tier | Verification | Label |
|---|---|---|
| Checks-only | Server replays deterministic checks from the signed transcript | `checks` |
| Full | Checks + LLM judge grading (submitter-funded) | `graded` |
| Verified | Full + 2 independent reproductions within CI | `verified` |

- Tabs per profile (`bare` / `standard` / `native`), per level (Sprint / Marathon / Ultra). Default view: Marathon / `standard` — the most representative of real agent usage.
- Every row shows: agent configuration, score, 95% CI, tier, task set version, harness hash, generalization gap (time-based canary), date.
- The generalization gap is computed from task timestamps (new vs old tasks), not from secret held-out tasks.

## 9. Business model

The bench org's fixed costs are ~$1-6/month (see `docs/plan/06-community-model.md`). It never pays for agent compute.

1. **Phase 1-2 (now):** free. The benchmark needs a populated, trusted board before anyone pays.
2. **Phase 3:** vendors pay for priority verification and per-evaluation services. Pricing is public and flat per level — no pay-for-score, ever. A vendor cannot pay to suppress a generalization-gap flag.
3. **Enterprise API:** paid access to score history, CI data, and head-to-head comparisons for buyers choosing agent platforms.
4. **Sponsored task categories:** allowed, disclosed on the task and the leaderboard, never in the active set without a 1-quarter quarantine. A sponsor cannot author the rubric for their own category.
5. What the benchmark will never sell: score boosts, early access to new task quarters beyond the 1-week author window, suppression of flags, or placement.

## 10. Roadmap

- **Phase 1 (this repo):** specification frozen at v1.0. Open for comment via issues.
- **Phase 2:** standard harness (`harness/`), seed task bank (85 tasks), LLM judge prompt and calibration set, leaderboard site.
- **Phase 3:** first official monthly run, paid evaluations, enterprise API.
- **Phase 4:** Ultra level goes live (needs the persistent-memory harness and multi-day run ops).

## 11. License and governance

- Everything in this repo is MIT licensed.
- The spec is versioned; breaking changes require a MAJOR version and a 30-day comment period.
- Task proposals via PR; rubric changes via PR with rationale. The maintainer's job is to protect the benchmark's integrity, not to pick winners.
