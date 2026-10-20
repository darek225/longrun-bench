from __future__ import annotations

from typing import Any

from .checks import CheckOutcome
from .models import TaskInstance


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def compute_efficiency(
    *,
    steps_used: int,
    step_budget: int,
    input_tokens: int,
    output_tokens: int,
    wall_clock_s: float,
    wall_clock_budget_s: float,
) -> dict[str, float]:
    steps_ratio = steps_used / step_budget if step_budget else 1.0
    budget_tokens = step_budget * 4000 if step_budget else 1
    tokens_ratio = (input_tokens + output_tokens) / budget_tokens if budget_tokens else 1.0
    time_ratio = wall_clock_s / wall_clock_budget_s if wall_clock_budget_s else 1.0
    raw = 1.0 - (0.5 * steps_ratio + 0.3 * tokens_ratio + 0.2 * time_ratio)
    return {
        "steps_ratio": steps_ratio,
        "tokens_ratio": tokens_ratio,
        "time_ratio": time_ratio,
        "raw": raw,
        "clamped": _clamp(raw),
    }


def score_checks_only(
    instance: TaskInstance,
    outcomes: list[CheckOutcome],
    *,
    steps_used: int,
    input_tokens: int = 0,
    output_tokens: int = 0,
    wall_clock_s: float = 0.0,
    deliverable_present: bool = True,
) -> dict[str, Any]:
    criteria: dict[str, dict[str, Any]] = {}
    for item in instance.rubric:
        criteria[item.criterion] = {
            "weight": item.weight,
            "score": float(item.weight),
            "caps_applied": [],
        }

    for outcome in outcomes:
        if outcome.result.score >= 1.0:
            continue
        for criterion, cap in outcome.caps.items():
            if criterion not in criteria:
                continue
            if cap < criteria[criterion]["score"]:
                criteria[criterion]["score"] = float(cap)
                criteria[criterion]["caps_applied"].append(
                    {"check_id": outcome.id, "cap": cap, "detail": outcome.result.detail}
                )

    if not deliverable_present:
        for criterion in ("correctness", "completeness"):
            if criterion in criteria:
                criteria[criterion]["score"] = 0.0
                criteria[criterion]["caps_applied"].append(
                    {"check_id": "deliverable", "cap": 0.0, "detail": "no deliverable produced"}
                )

    efficiency = compute_efficiency(
        steps_used=steps_used,
        step_budget=instance.budgets.steps,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        wall_clock_s=wall_clock_s,
        wall_clock_budget_s=instance.budgets.wall_clock_minutes * 60,
    )
    if "efficiency" in criteria:
        weight = float(criteria["efficiency"]["weight"])
        eff_score = efficiency["clamped"] * weight
        correctness = criteria.get("correctness")
        if correctness and float(correctness["weight"]) > 0:
            eff_score *= float(correctness["score"]) / float(correctness["weight"])
        criteria["efficiency"]["score"] = min(float(criteria["efficiency"]["score"]), float(eff_score))
        criteria["efficiency"]["efficiency"] = efficiency

    total = sum(float(item["score"]) for item in criteria.values())
    return {
        "tier": "checks",
        "provisional": True,
        "total": round(total, 4),
        "criteria": criteria,
        "checks": [outcome.to_dict() for outcome in outcomes],
        "efficiency": efficiency,
        "notes": "Checks-only provisional score. No LLM judge or human audit has graded this run.",
    }
