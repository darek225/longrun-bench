import random

import pytest

from leaderboard import orders, trust
from leaderboard.ingest import ingest_submission
from leaderboard.store import Store
from longrun.cli import build_bundle, main

from conftest import TASKS_DIR


@pytest.fixture()
def data_bundle(tmp_path):
    task_dir = TASKS_DIR / "sprint" / "sprint-data-001"
    out_dir = tmp_path / "out-data"
    code = main([
        "run-scripted", str(task_dir), "--seed", "42", "--param", "region=north", "--param", "top_n=3",
        "--script", str(task_dir / "smoke-script.json"), "--out", str(out_dir),
    ])
    assert code == 0
    return build_bundle(out_dir)


@pytest.fixture()
def board(tmp_path, data_bundle):
    store = Store(tmp_path / "board.db")
    result = ingest_submission({"board": "community", "runs": [data_bundle]}, store=store, tasks_root=TASKS_DIR)
    return store, result["score_ids"][0]


def test_price_list_is_public_and_flat():
    prices = orders.price_list()
    levels = {key: value for key, value in prices["evaluations"].items() if key in orders.LEVELS}
    assert levels == {"sprint": 2500, "marathon": 2500, "ultra": 2500}
    assert "suppression of a generalization-gap flag" in prices["never_for_sale"]


def test_evaluation_order_uses_published_price(board):
    store, _score_id = board
    order = orders.create_order(store, kind="evaluation", requester="vendor-x", level="marathon")
    assert order["amount_usd"] == 2500.0 and order["status"] == "quoted"
    with pytest.raises(orders.OrderError):
        orders.create_order(store, kind="evaluation", requester="vendor-x", level="weekly")


def test_order_lifecycle_and_payment_ref(board):
    store, score_id = board
    order = orders.create_order(store, kind="evaluation", requester="vendor-x", level="sprint")
    with pytest.raises(orders.OrderError):
        orders.transition(store, order_id=order["id"], status="paid", payment_ref="inv-1")  # must invoice first
    orders.transition(store, order_id=order["id"], status="invoiced")
    with pytest.raises(orders.OrderError):
        orders.transition(store, order_id=order["id"], status="paid")  # payment requires a reference
    paid = orders.transition(store, order_id=order["id"], status="paid", payment_ref="inv-2026-001")
    assert paid["payment_ref"] == "inv-2026-001"
    with pytest.raises(orders.OrderError):
        orders.transition(store, order_id=order["id"], status="fulfilled")  # needs the score it produced
    done = orders.transition(store, order_id=order["id"], status="fulfilled", score_id=score_id)
    assert done["status"] == "fulfilled" and done["score_id"] == score_id
    with pytest.raises(orders.OrderError):
        orders.transition(store, order_id=order["id"], status="cancelled")  # fulfilled is terminal


def test_priority_verification_passes_fee_through_and_draws_jobs(board):
    store, score_id = board
    store.award_reputation(subject="v-alpha", points=15, reason="task_authorship")
    store.award_reputation(subject="v-beta", points=15, reason="task_authorship")
    trust.opt_in_verifier(store, user_id="v-alpha", org="org-a")
    trust.opt_in_verifier(store, user_id="v-beta", org="org-b")
    order = orders.create_order(store, kind="priority_verification", requester="vendor-x", score_id=score_id, fee_usd=150)
    assert order["fee_to_verifier"] == 1 and order["amount_usd"] == 150.0
    with pytest.raises(orders.OrderError):
        orders.create_order(store, kind="priority_verification", requester="vendor-x", score_id=score_id, fee_usd=0)
    orders.transition(store, order_id=order["id"], status="invoiced")
    orders.transition(store, order_id=order["id"], status="paid", payment_ref="wire-9")
    done = orders.transition(store, order_id=order["id"], status="fulfilled", tasks_root=TASKS_DIR, rng=random.Random(4))
    assert done["status"] == "fulfilled"
    jobs = [job for job in store.list_jobs(score_id=score_id) if job["priority"]]
    assert len(jobs) == 2
    assert "payable to the completing verifier" in (done["note"] or "")


def test_orders_never_touch_scores(board):
    store, score_id = board
    before = store.get_score(score_id)
    order = orders.create_order(store, kind="priority_verification", requester="vendor-x", score_id=score_id, fee_usd=75)
    orders.transition(store, order_id=order["id"], status="invoiced")
    orders.transition(store, order_id=order["id"], status="paid", payment_ref="inv-2")
    orders.transition(store, order_id=order["id"], status="cancelled")
    after = store.get_score(score_id)
    for field in ("mean_score", "ci_low", "ci_high", "gen_gap", "gap_flag", "status", "tier"):
        assert after[field] == before[field]
