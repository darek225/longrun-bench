# 03 — The LLM Judge: Prompt, Calibration, Cost

## Decisions

- **Judge model:** a fixed, disclosed model version, pinned per task-set MAJOR version. Changing the judge is a MAJOR version bump (it changes scores).
- **Judge sees:** the public rubric anchors, the transcript (tool calls + results, thinking redacted), the deliverable, and the deterministic check outcomes. Never the agent's identity, vendor, or profile.
- **Judge does not see:** other agents' scores, the leaderboard, or any prior grades for the same task (no anchoring).
- **Human override:** human audit grade always wins over the judge. Disagreements are logged as calibration data and published quarterly.
- **Judge cost budget:** grading must cost under 5% of the run's own compute cost. If it doesn't, the rubric is too fuzzy; simplify the task.

## 1. The judge prompt (v1)

```
You are grading a long multi-step agent run against a rubric. Be strict, be concrete, cite evidence.

RUBRIC:
{rubric_anchors}

DETERMINISTIC CHECK OUTCOMES (scored in code, not by you):
{check_outcomes}
A failed check caps the corresponding criterion: do not award above the anchor
that describes the failure, even if the rest looks good.

TRANSCRIPT (tool calls and results):
{transcript}

DELIVERABLE:
{deliverable}

INSTRUCTIONS:
1. Score each criterion 0 to its max weight. Quote the transcript line or
   deliverable passage that justifies each score.
2. Correctness: verify 2-3 factual claims yourself by reasoning about the
   sources cited. If a claim has no source and is not common knowledge,
   treat it as unverified, not as true.
3. Efficiency: steps_used / step_budget and tokens_used. Under 50% of budget
   with full marks elsewhere is excellent; over 90% is poor.
4. Error recovery: count distinct failures in the transcript. For each, did
   the agent diagnose the cause (not just retry blindly) and adapt?
5. Instruction adherence: list every explicit constraint in the task brief.
   Check each one. One violation is minor; a pattern is major.
6. Output ONLY valid JSON:
   {"correctness": {"score": n, "evidence": "..."}, ...,
    "total": n, "flags": ["possible_fabrication", ...]}
7. Flags (optional): "possible_fabrication", "prompt_injection_attempt",
   "refused_task", "empty_deliverable". Flag, do not punish; the audit
   decides.
```

## 2. Calibration methodology

Before the judge grades official runs:

1. **Calibration set:** 30 transcripts (10 per level) hand-graded by 2 humans. Disagreements resolved by discussion; the resolved grade is ground truth.
2. **Judge trial:** the judge grades the calibration set. Target: within ±5 points of human total on 90% of transcripts, and no systematic bias by criterion (checked per-criterion).
3. **Bias checks:** the same transcript re-graded with agent identity swapped (where identity leaked into the transcript, e.g. self-references). Score delta must be < 3 points.
4. **Recalibration:** every quarter, 20 new transcripts added to the calibration set. If the judge drifts (>10% outside ±5), the judge prompt is revised (MINOR version) or the model is replaced (MAJOR version).
5. All calibration data is public in `harness/judge/calibration/`. Anyone can reproduce the judge's accuracy claim.

## 3. Human audit

- **Random sample:** 10% of official transcripts per month, stratified by level and profile.
- **Targeted:** 100% of runs flagged by the judge, 100% of vendor disputes, all top-3 leaderboard rows monthly.
- Auditors are contractors with domain checklists per category, never the task authors (separation of duties).
- Audit cost target: under $15 per transcript. At 10% of ~500 official runs/month = 50 audits = ~$750/month.

## 4. Disputes

- Vendors may dispute an official score within 14 days. Dispute = human re-grade of all 3 runs for the disputed tasks, auditor blinded to vendor identity.
- Re-grade result is final and published with the original, side by side. The dispute itself is public record.
- Frivolous disputes (3+ with no score change in a year) incur the audit cost.

## 5. Cost model

- Judge grading: ~1/20th the tokens of the run itself (transcript + deliverable in, JSON out). At current API prices this is cents per run.
- The 5% rule (§0 decisions) is enforced in code: if judge tokens exceed 5% of run tokens, the run is flagged for rubric review, not punished.
