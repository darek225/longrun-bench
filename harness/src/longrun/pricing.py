from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_PRICING_PATH = Path(__file__).resolve().parents[2] / "pricing.json"
TOKENS_PER_STEP_ESTIMATE = 4000  # spec constant, docs/plan/09-remaining-details.md §2


def load_pricing(path: str | Path | None = None) -> dict[str, Any]:
    pricing_path = Path(path) if path else DEFAULT_PRICING_PATH
    if not pricing_path.exists():
        return {"updated": None, "providers": {}}
    return json.loads(pricing_path.read_text(encoding="utf-8"))


def price_for(model: str, pricing: dict[str, Any] | None = None) -> tuple[float, float] | None:
    table = pricing if pricing is not None else load_pricing()
    entry = table.get("providers", {}).get(model)
    if not entry:
        return None
    return float(entry["input_per_mtok"]), float(entry["output_per_mtok"])


def estimate_cost_range(
    *,
    model: str,
    step_budget: int,
    pricing: dict[str, Any] | None = None,
    price_override: tuple[float, float] | None = None,
) -> dict[str, Any] | None:
    """Pre-run estimate per docs/plan/10-runner-flow.md §4.

    Assumes the empirical 4000 tokens/step, split 3:1 input:output.
    Low end = 25% of budget consumed, high end = 100%.
    """
    prices = price_override or price_for(model, pricing)
    if prices is None:
        return None
    price_in, price_out = prices
    total_tokens = step_budget * TOKENS_PER_STEP_ESTIMATE
    input_tokens = total_tokens * 0.75
    output_tokens = total_tokens * 0.25

    def cost(fraction: float) -> float:
        return (input_tokens * fraction * price_in + output_tokens * fraction * price_out) / 1_000_000

    return {"model": model, "low_usd": round(cost(0.25), 4), "high_usd": round(cost(1.0), 4)}


def actual_cost(
    *,
    model: str,
    input_tokens: int,
    output_tokens: int,
    pricing: dict[str, Any] | None = None,
    price_override: tuple[float, float] | None = None,
) -> float | None:
    prices = price_override or price_for(model, pricing)
    if prices is None:
        return None
    price_in, price_out = prices
    return round((input_tokens * price_in + output_tokens * price_out) / 1_000_000, 6)
