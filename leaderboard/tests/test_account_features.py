"""Account features (docs/ACCOUNT_FEATURES_SPEC.md): DB site settings
with an admin bootstrap, Google credentials from settings, and the
forgot/reset-password flow. HTTP-level, same fixtures as test_auth."""
import json
import threading
import urllib.error
import urllib.request

import pytest

from leaderboard import auth, mailer
from leaderboard.api import serve
from leaderboard.store import Store

from conftest import TASKS_DIR

from test_auth import _register, _request


@pytest.fixture()
def server(tmp_path):
    instance = serve(tmp_path / "board.db", TASKS_DIR, 0)
    port = instance.server_address[1]
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    instance.shutdown()
    instance.server_close()


@pytest.fixture()
def db_store(tmp_path):
    return Store(tmp_path / "unit.db")


def test_settings_bootstrap_claims_admin_and_hides_values(server):
    cookie, user = _register(server)
    status, _, body = _request(server, "/api/admin/settings", headers={"Cookie": cookie})
    assert status == 200
    assert json.loads(body)["settings"] == {
        "google_client_id": False,
        "google_client_secret": False,
        "mail_api_key": False,
        "mail_from": False,
    }
    status, _, body = _request(
        server,
        "/api/admin/settings",
        data={"settings": {"google_client_id": "cid-123", "mail_from": "bot@mails.dev"}},
        headers={"Cookie": cookie},
    )
    assert status == 200
    status_body = json.loads(body)["settings"]
    assert status_body["google_client_id"] is True and status_body["mail_from"] is True
    assert "cid-123" not in body  # values are never echoed

    _, other = _register(server, email="other@example.com", name="Other")
    other_cookie = _request(
        server, "/api/auth/login", data={"email": "other@example.com", "password": "test-password-1"}
    )[1]["Set-Cookie"].split(";")[0]
    status, _, body = _request(
        server,
        "/api/admin/settings",
        data={"settings": {"google_client_id": "hijack"}},
        headers={"Cookie": other_cookie},
    )
    assert status == 400 and "admin" in body


def test_settings_reject_unknown_keys_and_anonymous(server):
    cookie, _ = _register(server)
    status, _, _ = _request(
        server, "/api/admin/settings", data={"settings": {"drop_tables": "x"}}, headers={"Cookie": cookie}
    )
    assert status == 400
    status, _, _ = _request(server, "/api/admin/settings", data={"settings": {"mail_from": "a@b.c"}})
    assert status == 401


def test_settings_writable_with_upload_token(server):
    cookie, _ = _register(server)
    status, _, body = _request(server, "/api/auth/tokens", data={"label": "agent"}, headers={"Cookie": cookie})
    assert status == 201
    token = json.loads(body)["token"]
    status, _, body = _request(
        server,
        "/api/admin/settings",
        data={"settings": {"mail_api_key": "mk_test"}},
        headers={"X-Upload-Token": token},
    )
    assert status == 200 and json.loads(body)["settings"]["mail_api_key"] is True
    assert "mk_test" not in body


def test_google_credentials_from_db_settings(db_store, monkeypatch):
    monkeypatch.delenv("LONGRUN_GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("LONGRUN_GOOGLE_CLIENT_SECRET", raising=False)
    assert auth.google_configured(db_store) is False
    db_store.set_setting("google_client_id", "db-client")
    assert auth.google_configured(db_store) is False  # both halves required
    db_store.set_setting("google_client_secret", "db-secret")
    assert auth.google_configured(db_store) is True
    url = auth.google_auth_url(db_store, redirect_uri="http://x/cb", state="s1")
    assert "client_id=db-client" in url


def test_google_flow_with_db_settings(server, tmp_path, monkeypatch):
    monkeypatch.delenv("LONGRUN_GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("LONGRUN_GOOGLE_CLIENT_SECRET", raising=False)
    cookie, _ = _register(server)
    status, _, _ = _request(
        server,
        "/api/admin/settings",
        data={"settings": {"google_client_id": "db-cid", "google_client_secret": "db-secret"}},
        headers={"Cookie": cookie},
    )
    assert status == 200
    monkeypatch.setattr(
        auth,
        "exchange_google_code",
        lambda store=None, *, code, redirect_uri: {"sub": "sub-db", "email": "db@example.com", "display_name": "DB User"},
    )

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None

    opener = urllib.request.build_opener(NoRedirect())
    try:
        opener.open(urllib.request.Request(server + "/api/auth/google/start"), timeout=10)
        raise AssertionError("expected redirect")
    except urllib.error.HTTPError as exc:
        assert exc.code == 302
        location = exc.headers["Location"]
        state_cookie = exc.headers["Set-Cookie"].split(";")[0]
    assert "client_id=db-cid" in location
    state = location.rsplit("state=", 1)[1]
    try:
        opener.open(
            urllib.request.Request(
                server + f"/api/auth/google/callback?code=fake&state={state}", headers={"Cookie": state_cookie}
            ),
            timeout=10,
        )
        raise AssertionError("expected redirect")
    except urllib.error.HTTPError as exc:
        assert exc.code == 302
        session_cookie = exc.headers["Set-Cookie"].split(";")[0]
    status, _, body = _request(server, "/api/auth/me", headers={"Cookie": session_cookie})
    assert status == 200 and json.loads(body)["user"]["email"] == "db@example.com"


def test_config_endpoint_reflects_state(server):
    status, _, body = _request(server, "/api/auth/config")
    assert status == 200
    assert json.loads(body) == {"google_enabled": False, "password_reset_enabled": False}
    cookie, _ = _register(server)
    _request(
        server,
        "/api/admin/settings",
        data={
            "settings": {
                "google_client_id": "c",
                "google_client_secret": "s",
                "mail_api_key": "k",
                "mail_from": "bot@mails.dev",
            }
        },
        headers={"Cookie": cookie},
    )
    status, _, body = _request(server, "/api/auth/config")
    assert json.loads(body) == {"google_enabled": True, "password_reset_enabled": True}


def _capture_mail(monkeypatch):
    sent = []
    monkeypatch.setattr(
        mailer,
        "send_password_reset_email",
        lambda store, *, to, reset_url: sent.append({"to": to, "reset_url": reset_url}),
    )
    return sent


def test_forgot_password_generic_and_sends_one_email(server, monkeypatch):
    sent = _capture_mail(monkeypatch)
    _register(server)
    status_known, _, body_known = _request(server, "/api/auth/forgot-password", data={"email": "runner@example.com"})
    status_unknown, _, body_unknown = _request(server, "/api/auth/forgot-password", data={"email": "ghost@example.com"})
    assert status_known == status_unknown == 200
    assert json.loads(body_known) == json.loads(body_unknown) == {"ok": True}
    assert len(sent) == 1
    assert sent[0]["to"] == "runner@example.com"
    assert "/#/reset-password?token=" in sent[0]["reset_url"]


def test_reset_password_round_trip(server, monkeypatch):
    sent = _capture_mail(monkeypatch)
    old_cookie, _ = _register(server)
    _request(server, "/api/auth/forgot-password", data={"email": "runner@example.com"})
    token = sent[0]["reset_url"].rsplit("token=", 1)[1]

    status, _, _ = _request(
        server, "/api/auth/reset-password", data={"token": token, "password": "short"}
    )
    assert status == 400  # too short; token not consumed by a failed attempt

    status, headers, body = _request(
        server, "/api/auth/reset-password", data={"token": token, "password": "brand-new-password"}
    )
    assert status == 200
    new_cookie = headers["Set-Cookie"].split(";")[0]

    # Old sessions are revoked; the reset response signs the user in.
    status, _, _ = _request(server, "/api/auth/me", headers={"Cookie": old_cookie})
    assert status == 401
    status, _, body = _request(server, "/api/auth/me", headers={"Cookie": new_cookie})
    assert status == 200

    # New password works, old one does not, token cannot be reused.
    status, _, _ = _request(
        server, "/api/auth/login", data={"email": "runner@example.com", "password": "test-password-1"}
    )
    assert status == 401
    status, _, _ = _request(
        server, "/api/auth/login", data={"email": "runner@example.com", "password": "brand-new-password"}
    )
    assert status == 200
    status, _, _ = _request(
        server, "/api/auth/reset-password", data={"token": token, "password": "another-password"}
    )
    assert status == 400


def test_reset_token_expiry_and_unknown_token(db_store):
    user = auth.register_user(db_store, email="exp@example.com", password="test-password-1", display_name="Exp")
    created = auth.create_password_reset(db_store, email="exp@example.com")
    assert created is not None
    _, token = created
    db_store.conn.execute("UPDATE password_resets SET expires_at = '2000-01-01T00:00:00+00:00'")
    db_store.conn.commit()
    with pytest.raises(auth.AuthError):
        auth.reset_password(db_store, token=token, new_password="brand-new-password")
    with pytest.raises(auth.AuthError):
        auth.reset_password(db_store, token="not-a-token", new_password="brand-new-password")
    assert auth.create_password_reset(db_store, email="ghost@example.com") is None
    assert user["email"] == "exp@example.com"
