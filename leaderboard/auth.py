"""Accounts for the LongRun Bench site.

Product rule (Darek, 2026-10-20): anyone can view the board without
logging in; uploading your own benchmarks requires an account. Accounts
are email + password or Google sign-in. An agent submitting on your
behalf (the send-your-AI-the-link flow) authenticates with a personal
upload token instead of your password: tokens are shown once at
creation, stored only as sha256 hashes, and revocable.

Stdlib only, like the rest of the reference implementation. Passwords
use PBKDF2-HMAC-SHA256 with per-user salts. Sessions are random tokens
in HttpOnly cookies, stored hashed, 30-day expiry.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

from .store import Store

PBKDF2_ITERATIONS = 200_000
SESSION_DAYS = 30
UPLOAD_TOKEN_PREFIX = "lru_"
SESSION_COOKIE = "lrb_session"
GOOGLE_STATE_COOKIE = "lrb_oauth_state"


class AuthError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        _, iterations, salt_hex, digest_hex = stored.split("$")
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate.hex(), digest_hex)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _user_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "email": row["email"],
        "display_name": row["display_name"],
        "has_password": bool(row["password_hash"]),
        "google_linked": bool(row["google_sub"]),
        "created_at": row["created_at"],
    }


def register_user(store: Store, *, email: str, password: str, display_name: str) -> dict[str, Any]:
    email = email.strip().lower()
    display_name = display_name.strip()
    if "@" not in email or len(email) < 3:
        raise AuthError("a valid email is required")
    if len(password) < 8:
        raise AuthError("password must be at least 8 characters")
    if not display_name:
        raise AuthError("a display name is required")
    user_id = secrets.token_hex(8)
    try:
        store.conn.execute(
            "INSERT INTO users (id, email, display_name, password_hash) VALUES (?, ?, ?, ?)",
            (user_id, email, display_name, hash_password(password)),
        )
        store.conn.commit()
    except sqlite3.IntegrityError:
        raise AuthError(f"an account with email {email} already exists")
    return get_user(store, user_id)


def get_user(store: Store, user_id: str) -> dict[str, Any]:
    row = store.conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise AuthError(f"unknown user: {user_id}")
    return _user_dict(row)


def authenticate_password(store: Store, *, email: str, password: str) -> dict[str, Any] | None:
    row = store.conn.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()
    if row is None or not verify_password(password, row["password_hash"]):
        return None
    return _user_dict(row)


def upsert_google_user(store: Store, *, sub: str, email: str, display_name: str) -> dict[str, Any]:
    email = email.strip().lower()
    row = store.conn.execute("SELECT * FROM users WHERE google_sub = ?", (sub,)).fetchone()
    if row is None:
        row = store.conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if row is not None:
        store.conn.execute("UPDATE users SET google_sub = ? WHERE id = ?", (sub, row["id"]))
        store.conn.commit()
        return get_user(store, row["id"])
    user_id = secrets.token_hex(8)
    store.conn.execute(
        "INSERT INTO users (id, email, display_name, google_sub) VALUES (?, ?, ?, ?)",
        (user_id, email, display_name.strip() or email, sub),
    )
    store.conn.commit()
    return get_user(store, user_id)


# -- sessions -------------------------------------------------------------


def create_session(store: Store, user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    expires = (_now() + timedelta(days=SESSION_DAYS)).isoformat()
    store.conn.execute(
        "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
        (_token_hash(token), user_id, expires),
    )
    store.conn.commit()
    return token


def user_for_session(store: Store, token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    row = store.conn.execute(
        "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash = ? AND s.expires_at > ?",
        (_token_hash(token), _now().isoformat()),
    ).fetchone()
    return _user_dict(row) if row else None


def delete_session(store: Store, token: str | None) -> None:
    if token:
        store.conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))
        store.conn.commit()


# -- upload tokens ----------------------------------------------------------


def create_upload_token(store: Store, *, user_id: str, label: str) -> dict[str, Any]:
    token = UPLOAD_TOKEN_PREFIX + secrets.token_urlsafe(32)
    token_id = secrets.token_hex(8)
    store.conn.execute(
        "INSERT INTO upload_tokens (id, user_id, token_hash, label) VALUES (?, ?, ?, ?)",
        (token_id, user_id, _token_hash(token), label.strip() or "upload token"),
    )
    store.conn.commit()
    # The plaintext token is returned exactly once, here.
    return {"id": token_id, "label": label.strip() or "upload token", "token": token}


def user_for_upload_token(store: Store, token: str | None) -> dict[str, Any] | None:
    if not token or not token.startswith(UPLOAD_TOKEN_PREFIX):
        return None
    row = store.conn.execute(
        "SELECT u.* FROM upload_tokens t JOIN users u ON u.id = t.user_id WHERE t.token_hash = ? AND t.revoked_at IS NULL",
        (_token_hash(token),),
    ).fetchone()
    return _user_dict(row) if row else None


def list_upload_tokens(store: Store, user_id: str) -> list[dict[str, Any]]:
    rows = store.conn.execute(
        "SELECT id, label, created_at, revoked_at FROM upload_tokens WHERE user_id = ? ORDER BY created_at",
        (user_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def revoke_upload_token(store: Store, *, user_id: str, token_id: str) -> bool:
    cursor = store.conn.execute(
        "UPDATE upload_tokens SET revoked_at = datetime('now') WHERE id = ? AND user_id = ? AND revoked_at IS NULL",
        (token_id, user_id),
    )
    store.conn.commit()
    return cursor.rowcount == 1


# -- Site settings (admin bootstrap) ---------------------------------------
#
# Production has no write path into the host (no SSH route; the cloud
# console cannot edit files), so deployment config that cannot live in
# the public repo is stored in the DB and set through one endpoint.
# The first authenticated write claims the admin role; after that only
# the admin can change settings. Values are never returned by the API,
# only which keys are set.

SETTING_KEYS = ("google_client_id", "google_client_secret", "mail_api_key", "mail_from")
ADMIN_SETTING_KEY = "site_admin_user_id"


def settings_status(store: Store) -> dict[str, bool]:
    return {key: bool(store.get_setting(key)) for key in SETTING_KEYS}


def update_settings(store: Store, *, user: dict[str, Any], values: dict[str, Any]) -> dict[str, bool]:
    unknown = set(values) - set(SETTING_KEYS)
    if unknown:
        raise AuthError(f"unknown setting keys: {', '.join(sorted(unknown))}")
    admin_id = store.get_setting(ADMIN_SETTING_KEY)
    if admin_id is None:
        store.set_setting(ADMIN_SETTING_KEY, user["id"])
    elif admin_id != user["id"]:
        raise AuthError("only the site admin can change settings")
    for key, value in values.items():
        if not isinstance(value, str) or not value.strip():
            raise AuthError(f"setting {key} must be a non-empty string")
        store.set_setting(key, value.strip())
    return settings_status(store)


# -- Google sign-in ---------------------------------------------------------

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


def google_credentials(store: Store | None = None) -> tuple[str, str] | None:
    """Client id/secret: DB settings first (set via the admin bootstrap),
    env fallback for deployments that predate the settings table."""
    client_id = store.get_setting("google_client_id") if store else None
    client_secret = store.get_setting("google_client_secret") if store else None
    client_id = client_id or os.environ.get("LONGRUN_GOOGLE_CLIENT_ID")
    client_secret = client_secret or os.environ.get("LONGRUN_GOOGLE_CLIENT_SECRET")
    if client_id and client_secret:
        return client_id, client_secret
    return None


def google_configured(store: Store | None = None) -> bool:
    return google_credentials(store) is not None


def google_auth_url(store: Store | None = None, *, redirect_uri: str, state: str) -> str:
    credentials = google_credentials(store)
    if credentials is None:
        raise AuthError("google sign-in is not configured")
    params = {
        "client_id": credentials[0],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    return GOOGLE_AUTH_URL + "?" + urllib.parse.urlencode(params)


def exchange_google_code(store: Store | None = None, *, code: str, redirect_uri: str) -> dict[str, Any]:
    """Trade an authorization code for the user's Google identity.

    Kept as one small function so tests can stub it: the network exchange
    is the only part of the flow that cannot run offline.
    """
    credentials = google_credentials(store)
    if credentials is None:
        raise AuthError("google sign-in is not configured")
    data = urllib.parse.urlencode(
        {
            "code": code,
            "client_id": credentials[0],
            "client_secret": credentials[1],
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
    ).encode("utf-8")
    request = urllib.request.Request(GOOGLE_TOKEN_URL, data=data, method="POST")
    with urllib.request.urlopen(request, timeout=30) as response:
        tokens = json.loads(response.read().decode("utf-8"))
    access_token = tokens.get("access_token")
    if not access_token:
        raise AuthError("google did not return an access token")
    info_request = urllib.request.Request(GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"})
    with urllib.request.urlopen(info_request, timeout=30) as response:
        info = json.loads(response.read().decode("utf-8"))
    if not info.get("sub") or not info.get("email"):
        raise AuthError("google userinfo is missing sub/email")
    return {"sub": str(info["sub"]), "email": str(info["email"]), "display_name": str(info.get("name") or info["email"])}


# -- Password reset ---------------------------------------------------------
#
# A reset token is random, single-use, and valid for 60 minutes; only
# its sha256 hash is stored. Requesting a reset answers the same way
# whether or not the email exists, so the endpoint cannot be used to
# enumerate accounts. A successful reset revokes all of the user's
# sessions (upload tokens survive: they are the agent's credential and
# are revocable separately from the account page).

RESET_TOKEN_MINUTES = 60


def create_password_reset(store: Store, *, email: str) -> tuple[dict[str, Any], str] | None:
    """(user, plaintext token) for an existing account, else None."""
    row = store.conn.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()
    if row is None:
        return None
    token = secrets.token_urlsafe(32)
    expires = (_now() + timedelta(minutes=RESET_TOKEN_MINUTES)).isoformat()
    store.conn.execute(
        "INSERT INTO password_resets (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
        (_token_hash(token), row["id"], expires),
    )
    store.conn.commit()
    return _user_dict(row), token


def reset_password(store: Store, *, token: str, new_password: str) -> dict[str, Any]:
    if len(new_password) < 8:
        raise AuthError("password must be at least 8 characters")
    row = store.conn.execute(
        "SELECT pr.user_id AS user_id FROM password_resets pr "
        "WHERE pr.token_hash = ? AND pr.used_at IS NULL AND pr.expires_at > ?",
        (_token_hash(token), _now().isoformat()),
    ).fetchone()
    if row is None:
        raise AuthError("this reset link is invalid or has expired")
    user_id = row["user_id"]
    store.conn.execute("UPDATE password_resets SET used_at = datetime('now') WHERE token_hash = ?", (_token_hash(token),))
    store.conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(new_password), user_id))
    store.conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    store.conn.commit()
    return get_user(store, user_id)
