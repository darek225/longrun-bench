import json
import threading
import urllib.request

from longrun.server import RunStore, serve

from conftest import TASKS_DIR

BRIEF = (
    "Vendor comparison for a dental practice (crm):\n\n"
    "- HubSpot: $50/user/month, key features: contact management, email tracking, pipeline boards\n"
    "- Salesforce: $75/user/month, key features: deep customization, workflow automation, advanced reporting\n"
    "- Zoho CRM: $30/user/month, key features: contact management, appointment reminders, email campaigns\n\n"
    "Recommendation: For a small dental practice, Zoho CRM is the lowest cost at $30/user/month and covers "
    "contact management and appointment reminders, which are the two jobs the front desk actually needs. "
    "HubSpot at $50/user/month is the easier onboarding path. Salesforce at $75/user/month is justified only "
    "if deep customization is required. Start with Zoho CRM on a monthly contract and revisit HubSpot if "
    "staff adoption becomes the bottleneck after the first quarter of daily use in the practice.\n"
)


def test_scripted_run_over_store(tmp_path):
    store = RunStore(TASKS_DIR, tmp_path / "runs")
    script = json.loads((TASKS_DIR / "sprint-data-001" / "smoke-script.json").read_text(encoding="utf-8"))
    run_id = store.create_run(
        {
            "task_id": "sprint-data-001",
            "seed": 42,
            "params": {"region": "north", "top_n": 3},
            "adapter": {"type": "scripted", "responses": script},
            "agent": {"name": "proto-test", "model": "scripted", "profile": "standard"},
        }
    )
    status = store.wait(run_id, timeout=30)
    assert status["state"] == "done"
    assert status["steps_used"] == 3
    assert status["score_total"] > 95
    events = store.transcript(run_id)["events"]
    assert events[0]["type"] == "run_start"
    assert any(event["type"] == "deliverable" for event in events)


def test_external_run_waits_for_deliver_and_is_graded_by_server(tmp_path):
    store = RunStore(TASKS_DIR, tmp_path / "runs")
    run_id = store.create_run(
        {
            "task_id": "sprint-vendor-001",
            "seed": 3,
            "params": {"product": "crm", "business_type": "dental_practice"},
            "adapter": {"type": "external"},
            "agent": {"name": "native-product", "model": "x", "profile": "native"},
        }
    )
    assert store.status(run_id)["state"] == "running"
    running = store.status(run_id)
    # The external agent reads its brief from the status response.
    assert "dental_practice" in running["prompt"]
    assert running["params"]["product"] == "crm"
    assert running["workspace"].endswith("workspace")
    record = store.deliver(
        run_id,
        {"summary": "brief delivered", "artifact_uri": "brief.md", "artifact_content": BRIEF, "steps_used": 1},
    )
    assert record["score_total"] > 95


def test_external_deliver_by_reference_grades_the_workspace_file(tmp_path):
    """Regression (2026-10-20): delivering by artifact_uri alone must grade
    the file the agent wrote into the workspace, not an empty string."""
    import pytest

    store = RunStore(TASKS_DIR, tmp_path / "runs")
    run_id = store.create_run(
        {
            "task_id": "sprint-vendor-001",
            "seed": 3,
            "params": {"product": "crm", "business_type": "dental_practice"},
            "adapter": {"type": "external"},
            "agent": {"name": "native-product", "model": "x", "profile": "native"},
        }
    )
    workspace = tmp_path / "runs" / run_id / "workspace"
    (workspace / "brief.md").write_text(BRIEF, encoding="utf-8")
    record = store.deliver(run_id, {"summary": "written in workspace", "artifact_uri": "brief.md", "steps_used": 1})
    assert record["score_total"] > 95
    assert (workspace / "brief.md").read_text(encoding="utf-8") == BRIEF  # not clobbered

    run_id2 = store.create_run(
        {
            "task_id": "sprint-vendor-001",
            "seed": 3,
            "params": {"product": "crm", "business_type": "dental_practice"},
            "adapter": {"type": "external"},
            "agent": {"name": "native-product", "model": "x", "profile": "native"},
        }
    )
    with pytest.raises(ValueError, match="not found in workspace"):
        store.deliver(run_id2, {"summary": "nothing written", "artifact_uri": "brief.md"})
    status = store.status(run_id)
    assert status["state"] == "done" and status["steps_used"] == 1
    events = store.transcript(run_id)["events"]
    assert [event["type"] for event in events][:2] == ["run_start", "prompt"]
    assert events[-1]["type"] == "run_end"


def test_http_routes(tmp_path):
    server = serve(TASKS_DIR, tmp_path / "runs", 0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=10) as response:
            assert json.loads(response.read()) == {"ok": True}
        script = json.loads((TASKS_DIR / "sprint-code-001" / "smoke-script.json").read_text(encoding="utf-8"))
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/run",
            data=json.dumps({"task_id": "sprint-code-001", "seed": 7, "adapter": {"type": "scripted", "responses": script}}).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            assert response.status == 201
            run_id = json.loads(response.read())["run_id"]
        status = None
        for _ in range(50):
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/run/{run_id}/status", timeout=10) as response:
                status = json.loads(response.read())
            if status["state"] == "done":
                break
            threading.Event().wait(0.2)
        assert status and status["state"] == "done" and status["score_total"] > 95
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/run/{run_id}/transcript", timeout=10) as response:
            events = json.loads(response.read())["events"]
        assert events[0]["type"] == "run_start"
    finally:
        server.shutdown()
        server.server_close()
