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
