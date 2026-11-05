"""Outbound mail for the leaderboard: password-reset links.

Sending uses the mails.dev hosted API from the assistant-operated
mailbox; the API key and From address are site settings (see
auth.update_settings), never repo content. Stdlib only, like the rest
of the reference implementation. `send_email` is the single network
function so tests can stub it.
"""
from __future__ import annotations

import json
import urllib.request
from typing import Any

from .store import Store

MAILS_API_SEND_URL = "https://api.mails.dev/v1/send"


class MailError(RuntimeError):
    pass


def mail_configured(store: Store) -> bool:
    return bool(store.get_setting("mail_api_key") and store.get_setting("mail_from"))


def send_email(store: Store, *, to: str, subject: str, text: str) -> dict[str, Any]:
    api_key = store.get_setting("mail_api_key")
    sender = store.get_setting("mail_from")
    if not api_key or not sender:
        raise MailError("mail is not configured on this deployment (set mail_api_key and mail_from)")
    payload = json.dumps({"from": sender, "to": to, "subject": subject, "text": text}).encode("utf-8")
    request = urllib.request.Request(
        MAILS_API_SEND_URL,
        data=payload,
        method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read().decode("utf-8")
    return json.loads(body) if body else {}


def send_password_reset_email(store: Store, *, to: str, reset_url: str) -> None:
    send_email(
        store,
        to=to,
        subject="Reset your LongRun Bench password",
        text=(
            "Someone (probably you) asked to reset the password for this "
            "LongRun Bench account.\n\n"
            f"Reset it here: {reset_url}\n\n"
            "The link works once and expires in 60 minutes. If you did "
            "not ask for this, ignore this email; your password is "
            "unchanged.\n"
        ),
    )
