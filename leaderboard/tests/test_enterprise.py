import json
import threading
import urllib.error
import urllib.request

import pytest

from leaderboard import enterprise
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


def test_key_lifecycle_and_hash_only_storage(board):
    store, _score_id = board
    issued = enterprise.create_api_key(store, label="buyer-co")
    assert issued["key"].startswith("lrk_")
    record = enterprise.authenticate(store, issued["key"])
    assert record is not None and record["label"] == "buyer-co"
    # The stored record never contains the key itself, only its hash.
    stored = store.api_key_by_hash(enterprise.hash_key(issued["key"]))
    assert stored is not None and issued["key"] not in json.dumps(stored)
    assert enterprise.authenticate(store, "lrk_wrong") is None
    assert enterprise.authenticate(store, None) is None
    assert store.revoke_api_key(issued["id"]) is True
    assert enterprise.authenticate(store, issued["key"]) is None
    assert store.revoke_api_key(issued["id"]) is False  # already revoked


def test_history_includes_superseded_rows(board, data_bundle):
    store, first_id = board
    # A second submission for the same configuration supersedes the first on
    # the public board; enterprise history keeps both.
    result = ingest_submission({"board": "community", "runs": [data_bundle]}, store=store, tasks_root=TASKS_DIR)
    second_id = result["score_ids"][0]
    assert second_id != first_id
    assert len(store.latest_scores()) == 1
    history = enterprise.history(store, agent_name="scripted-smoke-agent")
    assert history["count"] == 2
    assert {row["id"] for row in history["scores"]} == {first_id, second_id}


def test_compare_head_to_head(board, data_bundle):
    store, first_id = board
    result = ingest_submission({"board": "official", "runs": [data_bundle]}, store=store, tasks_root=TASKS_DIR)
    other_id = result["score_ids"][0]
    comparison = enterprise.compare(store, left_id=first_id, right_id=other_id)
    assert comparison["mean_delta"] == 0.0
    assert comparison["ci_overlap"] is True
    assert comparison["shared_tasks"] == ["sprint-data-001"]
    assert comparison["per_task"][0]["delta"] == 0.0
    assert comparison["approximate"] is False


def test_compare_refuses_cross_profile_and_level(tmp_path):
    store = Store(tmp_path / "board.db")
    base = dict(agent_name="a", model="m", task_set="0.1.0", harness_hash="h", board="community", tier="checks")
    sprint_id = store.insert_score_group(profile="standard", level="sprint", task_runs={"t1": [90.0]}, manifests=[], **base)
    marathon_id = store.insert_score_group(profile="standard", level="marathon", task_runs={"t1": [90.0]}, manifests=[], **base)
    bare_id = store.insert_score_group(profile="bare", level="sprint", task_runs={"t1": [90.0]}, manifests=[], **base)
    with pytest.raises(enterprise.EnterpriseError):
        enterprise.compare(store, left_id=sprint_id, right_id=marathon_id)
    with pytest.raises(enterprise.EnterpriseError):
        enterprise.compare(store, left_id=sprint_id, right_id=bare_id)


def test_enterprise_http_requires_key(board):
    from leaderboard.api import serve

    store, score_id = board
    issued = enterprise.create_api_key(store, label="buyer-co")
    server = serve(store.db_path, TASKS_DIR, 0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/enterprise/history", timeout=10)
        assert excinfo.value.code == 401
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/enterprise/history?agent_name=scripted-smoke-agent",
            headers={"X-API-Key": issued["key"]},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read())
        assert payload["count"] == 1 and payload["scores"][0]["id"] == score_id
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/enterprise/compare?left={score_id}&right={score_id}",
            headers={"X-API-Key": issued["key"]},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            comparison = json.loads(response.read())
        assert comparison["mean_delta"] == 0.0
    finally:
        server.shutdown()
        server.server_close()
