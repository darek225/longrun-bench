from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .checks import CheckOutcome
from .driver import AdapterResponse
from .models import TaskInstance
from .scoring import compute_efficiency

PROMPT_PATH = Path(__file__).resolve().parents[2] / "judge" / "prompt.md"
JUDGED_CRITERIA = ("correctness", "completeness", "error_recovery", "instruction_adherence")


def prompt_sha256() -> str:
    """Hash of the fixed, disclosed judge prompt (SPEC.md §6.1).

    Graded submissions carry this hash; the leaderboard verifies it against
    its own copy so a graded claim is always tied to the published prompt.
    """
    return "sha256:" + hashlib.sha256(PROMPT_PATH.read_bytes()).hexdigest()


class JudgeError(ValueError):
    pass


def load_prompt_template() -> str:
    if PROMPT_PATH.exists():
        return PROMPT_PATH.read_text(encoding="utf-8")
    raise JudgeError(f"judge prompt not found at {PROMPT_PATH}")


def render_rubric_anchors(instance: TaskInstance) -> str:
    blocks: list[str] = []
    for criterion in instance.rubric:
        lines = [f"### {criterion.criterion} (max {criterion.weight:g})"]
        for score in sorted(criterion.anchors, key=lambda s: float(s), reverse=True):
            lines.append(f"- {score}: {criterion.anchors[score]}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def render_check_outcomes(outcomes: list[CheckOutcome]) -> str:
    if not outcomes:
        return "(no deterministic checks)"
    lines = []
    for outcome in outcomes:
        state = "PASS" if outcome.result.passed else "FAIL"
        caps = f" caps={outcome.caps}" if outcome.caps else ""
        lines.append(f"- {outcome.id} ({outcome.check}): {state} score={outcome.result.score:.2f} {outcome.result.detail}{caps}")
    return "\n".join(lines)


def render_transcript(events: list[dict[str, Any]], max_chars: int = 12000) -> str:
    lines: list[str] = []
    for event in events:
        kind = event.get("type")
        if kind == "tool_call":
            lines.append(f"step {event.get('step')} {event.get('tool')} -> {json.dumps(event.get('result_summary', {}), default=str)}")
        elif kind == "model_error":
            lines.append(f"step {event.get('step')} MODEL_ERROR {event.get('error')}")
        elif kind == "deliverable":
            lines.append(f"step {event.get('step')} DELIVERED {event.get('artifact_uri')}")
        elif kind == "run_end":
            lines.append(f"run_end reason={event.get('reason')} totals={json.dumps(event.get('totals', {}), default=str)}")
        elif kind in ("budget_exceeded", "nudge", "compaction", "budget_warning"):
            lines.append(f"step {event.get('step')} {kind}")
    text = "\n".join(lines)
    if len(text) > max_chars:
        head = text[: max_chars // 2]
        tail = text[-max_chars // 2 :]
        text = head + "\n... [transcript truncated for judge context] ...\n" + tail
    return text


def build_judge_prompt(
    instance: TaskInstance,
    outcomes: list[CheckOutcome],
    events: list[dict[str, Any]],
    deliverable_text: str,
) -> str:
    # Targeted replaces, not str.format: the prompt contains literal JSON
    # braces (the required output shape) that format() would misread.
    prompt = load_prompt_template()
    prompt = prompt.replace("{rubric_anchors}", render_rubric_anchors(instance))
    prompt = prompt.replace("{check_outcomes}", render_check_outcomes(outcomes))
    prompt = prompt.replace("{transcript}", render_transcript(events))
    prompt = prompt.replace("{deliverable}", deliverable_text)
    return prompt


def _extract_json(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise JudgeError("judge did not return valid JSON")


def parse_judge_output(text: str, instance: TaskInstance) -> dict[str, Any]:
    data = _extract_json(text)
    weights = {item.criterion: item.weight for item in instance.rubric}
    scores: dict[str, dict[str, Any]] = {}
    for criterion in JUDGED_CRITERIA:
        entry = data.get(criterion)
        if not isinstance(entry, dict) or "score" not in entry:
            raise JudgeError(f"judge output missing criterion: {criterion}")
        score = float(entry["score"])
        if score < 0 or score > weights.get(criterion, 0):
            raise JudgeError(f"judge score out of range for {criterion}: {score}")
        scores[criterion] = {"score": score, "evidence": str(entry.get("evidence", ""))}
    flags = data.get("flags", [])
    if not isinstance(flags, list):
        flags = []
    return {"scores": scores, "flags": [str(flag) for flag in flags]}


def combine_graded_scores(
    *,
    instance: TaskInstance,
    outcomes: list[CheckOutcome],
    judge_scores: dict[str, float],
    run_totals: dict[str, Any],
    evidence: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Combine raw judge criterion scores into a graded score.

    This is the single source of truth for graded arithmetic: the local
    `longrun grade` path and the leaderboard's graded-submission verifier
    both call it. Efficiency is the deterministic spec formula
    (docs/plan/09 §2, capped by the correctness ratio), and deterministic
    check caps are applied over the judge's scores: a failed check is a
    ceiling the judge cannot override (docs/plan/12-check-dsl.md §3).
    """
    weights = {item.criterion: item.weight for item in instance.rubric}
    evidence = evidence or {}
    criteria: dict[str, dict[str, Any]] = {}
    for criterion in JUDGED_CRITERIA:
        if criterion not in judge_scores:
            raise JudgeError(f"missing judge score for criterion: {criterion}")
        score = float(judge_scores[criterion])
        if score < 0 or score > weights.get(criterion, 0):
            raise JudgeError(f"judge score out of range for {criterion}: {score}")
        criteria[criterion] = {
            "weight": weights[criterion],
            "score": score,
            "evidence": evidence.get(criterion, ""),
            "caps_applied": [],
        }

    efficiency = compute_efficiency(
        steps_used=int(run_totals.get("steps", 0)),
        step_budget=instance.budgets.steps,
        input_tokens=int(run_totals.get("input_tokens", 0)),
        output_tokens=int(run_totals.get("output_tokens", 0)),
        wall_clock_s=float(run_totals.get("wall_clock_s", 0.0)),
        wall_clock_budget_s=instance.budgets.wall_clock_minutes * 60,
    )
    eff_weight = weights.get("efficiency", 15)
    eff_score = efficiency["clamped"] * eff_weight
    correctness = criteria["correctness"]["score"]
    if weights.get("correctness"):
        eff_score *= correctness / weights["correctness"]
    criteria["efficiency"] = {"weight": eff_weight, "score": float(eff_score), "evidence": "spec formula", "caps_applied": []}

    for outcome in outcomes:
        if outcome.result.score >= 1.0:
            continue
        for criterion, cap in outcome.caps.items():
            if criterion in criteria and cap < criteria[criterion]["score"]:
                criteria[criterion]["score"] = float(cap)
                criteria[criterion]["caps_applied"].append(
                    {"check_id": outcome.id, "cap": cap, "detail": outcome.result.detail}
                )

    return {
        "criteria": criteria,
        "total": round(sum(item["score"] for item in criteria.values()), 4),
        "efficiency": efficiency,
        "judge_scores": {criterion: float(judge_scores[criterion]) for criterion in JUDGED_CRITERIA},
    }


def grade_run(
    *,
    instance: TaskInstance,
    outcomes: list[CheckOutcome],
    events: list[dict[str, Any]],
    deliverable_text: str,
    judge: Any,
    run_totals: dict[str, Any],
) -> dict[str, Any]:
    """Grade a run with an LLM judge (docs/plan/03-judge.md).

    The judge scores the fuzzy criteria against the public rubric; the
    combination (efficiency formula, check caps, total) is
    `combine_graded_scores`, shared with the leaderboard verifier.
    """
    prompt = build_judge_prompt(instance, outcomes, events, deliverable_text)
    response = judge.complete([{"role": "user", "content": prompt}], {})
    if isinstance(response, dict):
        response = AdapterResponse.from_any(response)
    if response.error:
        raise JudgeError(f"judge call failed: {response.error}")
    parsed = parse_judge_output(response.text, instance)
    combined = combine_graded_scores(
        instance=instance,
        outcomes=outcomes,
        judge_scores={criterion: float(parsed["scores"][criterion]["score"]) for criterion in JUDGED_CRITERIA},
        run_totals=run_totals,
        evidence={criterion: parsed["scores"][criterion]["evidence"] for criterion in JUDGED_CRITERIA},
    )
    judge_tokens = int(response.usage.get("input_tokens", 0)) + int(response.usage.get("output_tokens", 0))
    run_tokens = int(run_totals.get("input_tokens", 0)) + int(run_totals.get("output_tokens", 0))
    token_share = (judge_tokens / run_tokens) if run_tokens else None
    return {
        "tier": "graded",
        "provisional": True,
        "total": combined["total"],
        "criteria": combined["criteria"],
        "judge_scores": combined["judge_scores"],
        "checks": [outcome.to_dict() for outcome in outcomes],
        "flags": parsed["flags"],
        "efficiency": combined["efficiency"],
        "judge": {
            "tokens": judge_tokens,
            "run_tokens": run_tokens,
            "token_share": token_share,
            "five_percent_rule_violated": bool(token_share is not None and token_share > 0.05),
        },
        "notes": "Graded score: LLM judge for fuzzy criteria, deterministic formula for efficiency, check caps enforced over judge scores.",
    }


class MockJudge:
    """Deterministic stand-in judge for tests and calibration plumbing.

    NOT the production judge: it scores from check outcomes and transcript
    error counts only. It exists so the grading pipeline and the calibration
    machinery can be exercised without a provider key.
    """

    def __init__(self, instance: TaskInstance, outcomes: list[CheckOutcome], events: list[dict[str, Any]], deliverable_text: str):
        self.instance = instance
        self.outcomes = outcomes
        self.events = events
        self.deliverable_text = deliverable_text

    def complete(self, history: list[dict[str, Any]], tools: dict[str, Any]) -> AdapterResponse:
        weights = {item.criterion: item.weight for item in self.instance.rubric}
        if self.outcomes:
            avg = sum(o.result.score for o in self.outcomes) / len(self.outcomes)
            passed_ratio = sum(1 for o in self.outcomes if o.result.passed) / len(self.outcomes)
        else:
            avg = 0.5
            passed_ratio = 0.5
        failures = sum(1 for e in self.events if e.get("type") == "model_error")
        failed_tools = sum(
            1 for e in self.events if e.get("type") == "tool_call" and "error" in (e.get("result_summary") or {})
        )
        delivered = any(e.get("type") == "deliverable" for e in self.events)
        if failures + failed_tools == 0:
            recovery = weights["error_recovery"]
        elif delivered:
            recovery = weights["error_recovery"] * 0.7
        else:
            recovery = weights["error_recovery"] * 0.3
        payload = {
            "correctness": {"score": round(weights["correctness"] * avg, 2), "evidence": "mock: mean check score"},
            "completeness": {"score": round(weights["completeness"] * passed_ratio, 2), "evidence": "mock: passed check ratio"},
            "error_recovery": {"score": round(recovery, 2), "evidence": f"mock: {failures + failed_tools} failures, delivered={delivered}"},
            "instruction_adherence": {
                "score": round(weights["instruction_adherence"] * (1.0 if passed_ratio == 1.0 else 0.6), 2),
                "evidence": "mock: check pass ratio",
            },
            "flags": ["empty_deliverable"] if not self.deliverable_text.strip() else [],
        }
        return AdapterResponse(text=json.dumps(payload), usage={"input_tokens": 10, "output_tokens": 10})


def run_calibration(entries: list[dict[str, Any]], judge_factory: Any) -> dict[str, Any]:
    """Agreement stats for a judge against hand-graded entries (docs/plan/03 §2).

    Each entry: {id, human_total, judge_total (precomputed) } or a full entry
    for judge_factory to grade. Target: within ±5 on 90% of entries.
    """
    results = []
    for entry in entries:
        judge_total = entry.get("judge_total")
        if judge_total is None:
            judge_total = judge_factory(entry)["total"]
        delta = float(judge_total) - float(entry["human_total"])
        results.append({"id": entry["id"], "human_total": entry["human_total"], "judge_total": judge_total, "delta": round(delta, 4), "within_5": abs(delta) <= 5})
    n = len(results) or 1
    within = sum(1 for r in results if r["within_5"])
    bias = sum(r["delta"] for r in results) / n
    return {
        "entries": results,
        "n": len(results),
        "within_5_rate": within / n,
        "mean_bias": round(bias, 4),
        "target_met": (within / n) >= 0.9 and abs(bias) <= 5,
    }
