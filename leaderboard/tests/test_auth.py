import json
import threading
import urllib.error
import urllib.request

import pytest

from leaderboard import auth
from leaderboard.api import serve
from leaderboard.ingest import ingest_submission
from leaderboard.store import Store

from conftest import TASKS_DIR


@pytest.fixture()
def server(tmp_path):
    instance = serve(tmp_path / "board.db", TASKS_DIR, 0)
    port = instance.server_address[1]
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    instance.shutdown()
    instance.server_close()


def _request(base, path, *, data=None, headers=None, method=None):
    request = urllib.request.Request(
        base + path,
        data=json.dumps(data).encode() if data is not None else None,
        method=method or ("POST" if data is not None else "GET"),
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, dict(response.headers), response.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read().decode()


def _register(base, email="runner@example.com", name="Test Runner"):
    status, headers, body = _request(
        base, "/api/auth/register", data={"email": email, "password": "test-password-1", "display_name": name}
    )
    assert status == 201
    return headers["Set-Cookie"].split(";")[0], json.loads(body)["user"]


def test_register_login_me_and_logout(server):
    cookie, user = _register(server)
    assert user["email"] == "runner@example.com" and user["has_password"] is True
    status, _, body = _request(server, "/api/auth/me", headers={"Cookie": cookie})
    assert status == 200 and json.loads(body)["user"]["id"] == user["id"]
    status, _, _ = _request(server, "/api/auth/me")
    assert status == 401  # viewing identity requires the session; the board itself stays public
    status, _, body = _request(server, "/api/auth/login", data={"email": "runner@example.com", "password": "wrong-password"})
    assert status == 401
    status, headers, _ = _request(server, "/api/auth/login", data={"email": "runner@example.com", "password": "test-password-1"})
    assert status == 200 and "lrb_session=" in headers["Set-Cookie"]
    status, _, _ = _request(server, "/api/auth/logout", data={}, headers={"Cookie": cookie})
    assert status == 200
    status, _, _ = _request(server, "/api/auth/me", headers={"Cookie": cookie})
    assert status == 401


def test_register_rejects_duplicate_and_short_password(server):
    _register(server)
    status, _, body = _request(
        server, "/api/auth/register", data={"email": "runner@example.com", "password": "test-password-1", "display_name": "Copy"}
    )
    assert status == 400 and "already exists" in body
    status, _, body = _request(
        server, "/api/auth/register", data={"email": "new@example.com", "password": "short", "display_name": "New"}
    )
    assert status == 400 and "8 characters" in body


def test_submit_requires_account_and_attributes_submitter(server, tmp_path, monkeypatch):
    from test_graded_ingest import _run_and_grade  # reuse the graded-run builder
    from longrun.cli import build_bundle

    out_dir, graded = _run_and_grade(
        tmp_path,
        {"correctness": 36, "completeness": 20, "error_recovery": 10, "instruction_adherence": 9},
    )
    payload = {"board": "community", "runs": [build_bundle(out_dir)]}
    status, _, body = _request(server, "/api/scores/submit", data=payload)
    assert status == 401 and "account" in body
    cookie, user = _register(server, email="darek@example.com", name="Darek Anderson")
    status, _, body = _request(server, "/api/auth/tokens", data={"label": "my agent"}, headers={"Cookie": cookie})
    assert status == 201
    token = json.loads(body)["token"]
    assert token.startswith("lru_")
    status, _, body = _request(server, "/api/scores/submit", data=payload, headers={"X-Upload-Token": token})
    assert status == 201
    score_id = json.loads(body)["score_ids"][0]
    status, _, body = _request(server, f"/api/scores/{score_id}")
    assert status == 200
    detail = json.loads(body)
    assert detail["submitter_name"] == "Darek Anderson"
    assert detail["submitter_user_id"] == user["id"]
    # Revoked tokens stop working immediately.
    status, _, body = _request(server, "/api/auth/tokens", headers={"Cookie": cookie})
    token_id = json.loads(body)["tokens"][0]["id"]
    status, _, _ = _request(server, f"/api/auth/tokens/{token_id}/revoke", data={}, headers={"Cookie": cookie})
    assert status == 200
    status, _, _ = _request(server, "/api/scores/submit", data=payload, headers={"X-Upload-Token": token})
    assert status == 401


def test_public_board_needs_no_login(server):
    status, _, body = _request(server, "/api/scores")
    assert status == 200 and json.loads(body)["scores"] == []
    status, _, _ = _request(server, "/")
    assert status == 200


def test_agent_instructions_pages(server):
    status, headers, body = _request(server, "/agent")
    assert status == 200 and "text/plain" in headers["Content-Type"]
    assert "longrun.cli upload" in body and "/api/tasks" in body
    status, _, body = _request(server, "/agent/sprint-data-001")
    assert status == 200
    assert "sprint-data-001" in body and "tasks/sprint/sprint-data-001" in body
    status, _, _ = _request(server, "/agent/nope-999")
    assert status == 404
    status, _, body = _request(server, "/llms.txt")
    assert status == 200 and "/agent" in body


def test_google_flow_with_stubbed_exchange(server, tmp_path, monkeypatch):
    monkeypatch.setenv("LONGRUN_GOOGLE_CLIENT_ID", "test-client")
    monkeypatch.setenv("LONGRUN_GOOGLE_CLIENT_SECRET", "test-secret")
    monkeypatch.setattr(
        auth,
        "exchange_google_code",
        lambda *, code, redirect_uri: {"sub": "google-sub-1", "email": "g@example.com", "display_name": "Google User"},
    )
    opener = urllib.request.build_opener(NoRedirect())
    request = urllib.request.Request(server + "/api/auth/google/start")
    try:
        opener.open(request, timeout=10)
        raise AssertionError("expected redirect")
    except urllib.error.HTTPError as exc:
        assert exc.code == 302
        location = exc.headers["Location"]
        state_cookie = exc.headers["Set-Cookie"].split(";")[0]
    assert "accounts.google.com" in location and "state=" in location
    state = location.rsplit("state=", 1)[1]
    request = urllib.request.Request(
        server + f"/api/auth/google/callback?code=fake-code&state={state}",
        headers={"Cookie": state_cookie},
    )
    try:
        opener.open(request, timeout=10)
        raise AssertionError("expected redirect")
    except urllib.error.HTTPError as exc:
        assert exc.code == 302
        session_cookie = exc.headers["Set-Cookie"].split(";")[0]
    status, _, body = _request(server, "/api/auth/me", headers={"Cookie": session_cookie})
    assert status == 200
    user = json.loads(body)["user"]
    assert user["email"] == "g@example.com" and user["google_linked"] is True and user["has_password"] is False
    # A state mismatch is refused.
    status, _, _ = _request(server, "/api/auth/google/callback?code=fake-code&state=wrong", headers={"Cookie": state_cookie})
    assert status == 400


def test_google_start_unconfigured(server, monkeypatch):
    monkeypatch.delenv("LONGRUN_GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("LONGRUN_GOOGLE_CLIENT_SECRET", raising=False)
    status, _, body = _request(server, "/api/auth/google/start")
    assert status == 501 and "not configured" in body


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def test_direct_ingest_stays_unattributed(tmp_path):
    store = Store(tmp_path / "board.db")
    user = auth.register_user(store, email="a@example.com", password="test-password-1", display_name="A")
    token = auth.create_upload_token(store, user_id=user["id"], label="t")["token"]
    assert auth.user_for_upload_token(store, token)["id"] == user["id"]
    assert auth.user_for_upload_token(store, "lru_bogus") is None
