from __future__ import annotations

import json
import random
from datetime import datetime
from pathlib import Path
from typing import Any

from . import trust
from .store import Store

# Phase 3 paid services (SPEC.md §9, DECISIONS.md #36-38, docs/plan/05 §2).
#
# The price list is public (leaderboard/prices.json) and enforced here:
# evaluation orders are created only at the flat published price, and a
# priority-verification fee passes through to the completing verifier with
# the org taking no cut. Orders are a public ledger of who paid for what
# service. Nothing in this module can create, alter, or suppress a score,
# a generalization-gap flag, or a board position: those code paths do not
# exist, by design (SPEC.md §9: "What the benchmark will never sell").

PRICES_PATH = Path(__file__).resolve().parent / "prices.json"
LEVELS = ("sprint", "marathon", "ultra")

TRANSITIONS: dict[str, set[str]] = {
    "quoted": {"invoiced", "cancelled"},
    "invoiced": {"paid", "cancelled"},
    "paid": {"fulfilled", "cancelled"},
    "fulfilled": set(),
    "cancelled": set(),
}


class OrderError(ValueError):
    pass


def price_list() -> dict[str, Any]:
    return json.loads(PRICES_PATH.read_text(encoding="utf-8"))


def create_order(
    store: Store,
    *,
    kind: str,
    requester: str,
    level: str | None = None,
    score_id: str | None = None,
    fee_usd: float | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    if kind == "evaluation":
        if level not in LEVELS:
            raise OrderError(f"evaluation requires a level in {LEVELS}, got {level!r}")
        amount = float(price_list()["evaluations"][level])
        order_id = store.create_order(
            kind=kind, requester=requester, level=level, score_id=None,
            amount_usd=amount, fee_to_verifier=False, note=note,
        )
    elif kind == "priority_verification":
        if not score_id:
            raise OrderError("priority_verification requires a score_id")
        if store.get_score(score_id) is None:
            raise KeyError(f"unknown score_id: {score_id}")
        if fee_usd is None or float(fee_usd) <= 0:
            raise OrderError("priority_verification requires a positive fee_usd (paid through to the verifier)")
        order_id = store.create_order(
            kind=kind, requester=requester, level=None, score_id=score_id,
            amount_usd=float(fee_usd), fee_to_verifier=True, note=note,
        )
    else:
        raise OrderError(f"unknown order kind: {kind!r}")
    return store.get_order(order_id)  # type: ignore[return-value]


def transition(
    store: Store,
    *,
    order_id: str,
    status: str,
    payment_ref: str | None = None,
    score_id: str | None = None,
    note: str | None = None,
    tasks_root: str | Path | None = None,
    rng: random.Random | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Move an order through its lifecycle.

    Payment is recorded, never processed: `paid` requires the operator's
    payment reference (invoice/payment id from whatever rail was used).
    Fulfillment is service-specific:
    - priority_verification draws priority jobs from the verifier pool and
      records them in the order note; the fee belongs to the verifier who
      completes a job (pass-through, plan 06 §4).
    - evaluation links the official score row the evaluation produced. The
      score itself arrives only through normal ingestion and replay; an
      order can link a score, it can never create or modify one.
    """
    order = store.get_order(order_id)
    if order is None:
        raise KeyError(f"unknown order_id: {order_id}")
    allowed = TRANSITIONS.get(order["status"], set())
    if status not in allowed:
        raise OrderError(f"order {order_id} is {order['status']}; cannot move to {status}")
    fields: dict[str, Any] = {"status": status}
    if status == "paid":
        if not payment_ref:
            raise OrderError("marking an order paid requires a payment_ref")
        fields["payment_ref"] = payment_ref
    if status == "fulfilled":
        if order["kind"] == "priority_verification":
            if tasks_root is None:
                raise OrderError("fulfilling priority_verification requires the tasks root")
            result = trust.request_verification(
                store, score_id=str(order["score_id"]), priority=True, rng=rng, now=now
            )
            job_ids = [job["id"] for job in result["jobs"]]
            fields["note"] = (
                f"priority jobs drawn: {', '.join(job_ids) if job_ids else 'none (pool shortfall)'}; "
                f"fee ${order['amount_usd']:.2f} payable to the completing verifier"
            )
        elif order["kind"] == "evaluation":
            if not score_id:
                raise OrderError("fulfilling an evaluation requires the score_id it produced")
            if store.get_score(score_id) is None:
                raise KeyError(f"unknown score_id: {score_id}")
            fields["score_id"] = score_id
    if note:
        fields["note"] = note
    store.update_order(order_id, **fields)
    return store.get_order(order_id)  # type: ignore[return-value]
