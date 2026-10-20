import json
import random
import threading
import urllib.request
from datetime import datetime, timezone

import pytest

from leaderboard import trust
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


def _fund_and_opt_in(store, user_id, org, points=15):
    store.award_reputation(subject=user_id, points=points, reason="task_authorship")
    return trust.opt_in_verifier(store, user_id=user_id, org=org)


def test_opt_in_requires_reputation_stake(tmp_path):
    store = Store(tmp_path / "board.db")
    with pytest.raises(trust.TrustError):
        trust.opt_in_verifier(store, user_id="nobody", org="org-x")
    store.award_reputation(subject="nobody", points=10, reason="task_authorship")
    result = trust.opt_in_verifier(store, user_id="nobody", org="org-x")
    assert result["opted_in"] is True


def test_lottery_draw_excludes_submitter_org(board):
    store, score_id = board
    _fund_and_opt_in(store, "v-alpha", "org-a")
    _fund_and_opt_in(store, "v-beta", "org-b")
    _fund_and_opt_in(store, "v-gamma", "org-a")
    result = trust.request_verification(store, score_id=score_id, submitter_org="org-a", rng=random.Random(7))
    drawn = {job["verifier"] for job in result["jobs"]}
    assert drawn == {"v-beta"}  # org-a members excluded; only one eligible remains
    assert result["pool_shortfall"] == 1
    assert result["reproduce"] == [{"task_id": "sprint-data-001", "seed": 42}]
    job = result["jobs"][0]
    assert job["due_at"] > job["assigned_at"]


def test_two_within_ci_reproductions_verify_the_score(board, data_bundle):
    store, score_id = board
    _fund_and_opt_in(store, "v-alpha", "org-a")
    _fund_and_opt_in(store, "v-beta", "org-b")
    result = trust.request_verification(store, score_id=score_id, rng=random.Random(3))
    assert len(result["jobs"]) == 2
    first = trust.submit_verification_job(store, job_id=result["jobs"][0]["id"], bundles=[data_bundle], tasks_root=TASKS_DIR)
    assert first["within_ci"] is True
    assert first["reputation_awarded"] == 5
    assert first["score_status"] == "provisional"
    second = trust.submit_verification_job(store, job_id=result["jobs"][1]["id"], bundles=[data_bundle], tasks_root=TASKS_DIR)
    assert second["score_status"] == "verified"
    score = store.get_score(score_id)
    assert score["status"] == "verified" and score["tier"] == "verified"
    verifier = result["jobs"][0]["verifier"]
    assert store.reputation_balance(verifier) == 20  # 15 stake-earning + 5 reward


def test_reproduction_must_cover_the_scores_runs(board):
    store, score_id = board
    _fund_and_opt_in(store, "v-alpha", "org-a")
    result = trust.request_verification(store, score_id=score_id, rng=random.Random(1))
    with pytest.raises(trust.TrustError):
        trust.submit_verification_job(store, job_id=result["jobs"][0]["id"], bundles=[], tasks_root=TASKS_DIR)


def test_two_outside_ci_marks_disputed(board):
    store, score_id = board
    for verifier in ("v-alpha", "v-beta"):
        store.record_verification(
            score_id=score_id, verifier=verifier, org="org", run_id="r",
            task_id="sprint-data-001", seed=42, reproduced_total=10.0,
        )
    assert trust.apply_verification_outcome(store, score_id=score_id) == "disputed"
    assert store.get_score(score_id)["status"] == "disputed"


def test_expired_job_docks_and_redraws(board):
    store, score_id = board
    _fund_and_opt_in(store, "v-alpha", "org-a")
    _fund_and_opt_in(store, "v-beta", "org-b")
    _fund_and_opt_in(store, "v-gamma", "org-c")
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    result = trust.request_verification(store, score_id=score_id, rng=random.Random(5), now=start)
    assert len(result["jobs"]) == 2
    expired_verifiers = {job["verifier"] for job in result["jobs"]}
    sweep = trust.expire_jobs(store, now=datetime(2026, 1, 20, tzinfo=timezone.utc), rng=random.Random(9))
    assert len(sweep["expired"]) == 2
    for verifier in expired_verifiers:
        assert store.reputation_balance(verifier) == 13  # 15 - 2 dock
    assert len(sweep["redrawn"]) == 2  # one replacement per expired job
    assert sweep["redrawn"][0]["verifier"] not in expired_verifiers  # first redraw takes the undrawn pool member


def test_dispute_stake_priority_and_resolution(board):
    store, score_id = board
    _fund_and_opt_in(store, "v-alpha", "org-a")
    _fund_and_opt_in(store, "v-beta", "org-b")
    store.award_reputation(subject="filer", points=15, reason="calibration")
    filed = trust.file_dispute(store, score_id=score_id, filer="filer", reason="score looks inflated", rng=random.Random(2))
    assert store.reputation_balance("filer") == 10  # 5 staked
    assert len(filed["verification"]["jobs"]) == 2
    assert all(job["priority"] == 1 for job in filed["verification"]["jobs"])
    resolved = trust.resolve_dispute(store, dispute_id=filed["dispute_id"], outcome="upheld", resolution="Panel: reproduction failed twice.")
    assert resolved["status"] == "resolved"
    assert store.reputation_balance("filer") == 15  # stake refunded on upheld
    assert store.get_score(score_id)["status"] == "disputed"
    dispute = store.get_dispute(filed["dispute_id"])
    assert dispute["outcome"] == "upheld" and "Panel" in dispute["resolution"]


def test_dispute_rejected_forfeits_stake(board):
    store, score_id = board
    store.award_reputation(subject="filer", points=8, reason="bug_report")
    store.award_reputation(subject="filer", points=7, reason="task_authorship")
    filed = trust.file_dispute(store, score_id=score_id, filer="filer", reason="hunch", rng=random.Random(2))
    trust.resolve_dispute(store, dispute_id=filed["dispute_id"], outcome="rejected", resolution="Both reproductions landed inside the CI.")
    assert store.reputation_balance("filer") == 10  # 15 - 5 forfeited


def test_dispute_requires_stake(board):
    store, score_id = board
    with pytest.raises(trust.TrustError):
        trust.file_dispute(store, score_id=score_id, filer="broke", reason="hunch")


def test_trust_endpoints_over_http(board, data_bundle):
    from leaderboard.api import serve

    store, score_id = board
    server = serve(store.db_path, TASKS_DIR, 0)
    # serve() builds its own Store on the same file; fund through the API instead.
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def post(path, payload, expect=201):
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}{path}",
            data=json.dumps(payload).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            assert response.status == expect
            return json.loads(response.read())

    try:
        post("/api/reputation/award", {"subject": "v-http", "points": 12, "reason": "task_authorship"})
        opted = post("/api/verifiers/opt-in", {"verifier": "v-http", "org": "org-http"})
        assert opted["opted_in"] is True
        drawn = post(f"/api/scores/{score_id}/request-verification", {})
        assert drawn["pool_shortfall"] == 1  # one eligible verifier, two slots
        assert drawn["jobs"][0]["verifier"] == "v-http"
        job_id = drawn["jobs"][0]["id"]
        submitted = post(f"/api/verification-jobs/{job_id}/submit", {"runs": [data_bundle]})
        assert submitted["within_ci"] is True
    finally:
        server.shutdown()
        server.server_close()
