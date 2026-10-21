import json
import threading
import urllib.request

import pytest

from leaderboard.ingest import IngestError, ingest_submission
from leaderboard.store import Store
from longrun.cli import build_bundle, main


def _run_bundle(tmp_path, task, script_args):
    task_dir = tmp_path / "tasks" / task
    out_dir = tmp_path / ("out-" + task)
    code = main(["run-scripted", str(task_dir), *script_args, "--script", str(task_dir / "smoke-script.json"), "--out", str(out_dir)])
    assert code == 0
    return build_bundle(out_dir)


@pytest.fixture()
def bundles(tmp_path):
    # Run against the real task bank read-only: point run-scripted at the repo tasks.
    from conftest import TASKS_DIR

    def make(task, script_args):
        task_dir = TASKS_DIR / task
        out_dir = tmp_path / ("out-" + task_dir.name)
        code = main(["run-scripted", str(task_dir), *script_args, "--script", str(task_dir / "smoke-script.json"), "--out", str(out_dir)])
        assert code == 0
        return build_bundle(out_dir)

    return {
        "data": make("sprint/sprint-data-001", ["--seed", "42", "--param", "region=north", "--param", "top_n=3"]),
        "vendor": make("sprint/sprint-vendor-001", ["--seed", "42", "--param", "product=crm", "--param", "business_type=dental_practice"]),
    }


def test_ingest_groups_runs_into_one_board_row(tmp_path, bundles):
    from conftest import TASKS_DIR

    store = Store(tmp_path / "board.db")
    result = ingest_submission({"board": "community", "runs": [bundles["data"], bundles["vendor"]]}, store=store, tasks_root=TASKS_DIR)
    assert result["runs_verified"] == 2
    assert len(result["score_ids"]) == 1
    rows = store.latest_scores(profile="standard", level="sprint", board="community")
    assert len(rows) == 1
    row = rows[0]
    assert row["agent_name"] == "scripted-smoke-agent"
    assert row["n_tasks"] == 2 and row["n_runs"] == 2
    assert row["mean_score"] > 95
    assert row["provisional"] == 1  # fewer than 3 runs per task
    detail = store.get_score(row["id"])
    assert len(detail["task_scores"]) == 2
    assert len(detail["run_manifests"]) == 2
    assert all(m["claimed_total"] == m["replayed_total"] for m in detail["run_manifests"])


def test_ingest_rejects_tampered_claim(tmp_path, bundles):
    from conftest import TASKS_DIR

    store = Store(tmp_path / "board.db")
    bundle = json.loads(json.dumps(bundles["data"]))
    bundle["submission"]["score_claim"]["total"] = 100.0
    with pytest.raises(IngestError):
        ingest_submission({"runs": [bundle]}, store=store, tasks_root=TASKS_DIR)


def test_ingest_rejects_garbage_deliverable_replay(tmp_path, bundles):
    from conftest import TASKS_DIR

    store = Store(tmp_path / "board.db")
    bundle = json.loads(json.dumps(bundles["data"]))
    bundle["workspace_files"]["report.md"] = "Wrong answer, no figures at all.\n"
    with pytest.raises(IngestError) as excinfo:
        ingest_submission({"runs": [bundle]}, store=store, tasks_root=TASKS_DIR)
    assert "mismatch" in str(excinfo.value)


def test_verification_recording_uses_ci(tmp_path, bundles):
    from conftest import TASKS_DIR

    store = Store(tmp_path / "board.db")
    result = ingest_submission({"runs": [bundles["data"]]}, store=store, tasks_root=TASKS_DIR)
    score_id = result["score_ids"][0]
    row = store.get_score(score_id)
    outcome = store.record_verification(
        score_id=score_id, verifier="other-agent", org="other-org", run_id="r2",
        task_id="sprint-data-001", seed=42, reproduced_total=row["mean_score"],
    )
    assert outcome["within_ci"] is True
    outcome2 = store.record_verification(
        score_id=score_id, verifier="third-agent", org="third-org", run_id="r3",
        task_id="sprint-data-001", seed=42, reproduced_total=10.0,
    )
    assert outcome2["within_ci"] is False
    assert store.verification_counts(score_id) == {"within": 1, "outside": 1}


def test_http_api_and_site(tmp_path, bundles):
    from conftest import TASKS_DIR
    from leaderboard.api import serve

    server = serve(tmp_path / "board.db", TASKS_DIR, 0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=10) as response:
            html = response.read().decode()
        assert "LongRun Bench" in html
        # Uploading requires an account (Darek, 2026-10-20): register and
        # submit with the account's upload token. Viewing stays public.
        register_req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/auth/register",
            data=json.dumps({"email": "runner@example.com", "password": "test-password-1", "display_name": "Test Runner"}).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(register_req, timeout=10) as response:
            assert response.status == 201
            session_cookie = response.headers["Set-Cookie"].split(";")[0]
        token_req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/auth/tokens",
            data=json.dumps({"label": "test"}).encode(),
            method="POST",
            headers={"Content-Type": "application/json", "Cookie": session_cookie},
        )
        with urllib.request.urlopen(token_req, timeout=10) as response:
            upload_token = json.loads(response.read())["token"]
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/scores/submit",
            data=json.dumps({"board": "community", "runs": [bundles["data"]]}).encode(),
            method="POST",
            headers={"Content-Type": "application/json", "X-Upload-Token": upload_token},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            assert response.status == 201
            score_id = json.loads(response.read())["score_ids"][0]
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/scores?profile=standard&level=sprint&board=community", timeout=10) as response:
            rows = json.loads(response.read())["scores"]
        assert len(rows) == 1 and rows[0]["id"] == score_id
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/scores/{score_id}", timeout=10) as response:
            detail = json.loads(response.read())
        assert detail["task_scores"][0]["task_id"] == "sprint-data-001"
        assert detail["submitter_name"] == "Test Runner"
        dispute_req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/disputes",
            data=json.dumps({"score_id": score_id, "reason": "spot check"}).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(dispute_req, timeout=10) as response:
            assert response.status == 201
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/disputes", timeout=10) as response:
            disputes = json.loads(response.read())["disputes"]
        assert len(disputes) == 1 and disputes[0]["status"] == "open"
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/tasks", timeout=10) as response:
            tasks = json.loads(response.read())["tasks"]
        assert len(tasks) == 85
    finally:
        server.shutdown()
        server.server_close()
