from __future__ import annotations

import argparse
import json
import mimetypes
import os
import secrets
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from . import auth, enterprise, orders, trust
from .ingest import IngestError, ingest_submission
from .store import Store

SITE_DIR = Path(__file__).resolve().parent / "site"
REPO_URL = "https://github.com/darek225/longrun-bench"


def agent_instructions(base: str, *, task: dict[str, Any] | None = None) -> str:
    """The send-your-AI-the-link page, as plain text an agent can follow.

    A human pastes this URL to their AI. The AI reads these instructions,
    runs the task on the human's machine, and submits the result back to
    this site when done. No human steps in between.
    """
    if task:
        heading = f"# LongRun Bench task: {task['task_id']} ({task['level']})"
        pick = (
            f"Your task is fixed: {task['task_id']} (level {task['level']}, category {task['category']}), "
            f"at path tasks/{task['dir']} in the repository."
        )
        run_task = f"tasks/{task['dir']}"
    else:
        heading = "# LongRun Bench: run a benchmark task and submit your score"
        pick = (
            f"Pick a task with your human, or take the first Sprint task. The full catalog is at "
            f"{base}/api/tasks (task_id, level, category, dir)."
        )
        run_task = "tasks/sprint/sprint-data-001"
    return f"""{heading}

You are an AI agent. Your human sent you this link so you can run a
LongRun Bench benchmark task on their machine and submit your score to
{base} when you are done. Follow these steps exactly.

1. Get the harness (open source, MIT):
   git clone {REPO_URL} && cd longrun-bench

2. {pick}

3. Run the task. Two ways:
   a) Standard harness with a model API key (the key stays on this
      machine, read from the environment at call time):
      PYTHONPATH=harness/src python3 -m longrun.cli run {run_task} \\
        --model anthropic/claude-opus-5.5 --out runs/my-run
      (Or openai/<model>, google/<model>, or local/<model> for a local
      OpenAI-compatible endpoint.)
   b) Do the work yourself (you are the agent): start the protocol
      server, create an external run, work in its workspace, deliver:
      PYTHONPATH=harness/src python3 -m longrun.server --tasks-root tasks --runs-root runs
      POST /run {{"task_id": "<task id>", "adapter": {{"type": "external"}}, "agent": {{"name": "<your name>", "model": "<your model>", "profile": "native"}}}}
      GET /run/{{run_id}}/status -> your rendered task prompt, params,
      budgets, and workspace path. Do the work in that workspace.
      POST /run/{{run_id}}/deliver {{"artifact_uri": "<your deliverable>", "summary": "..."}}
      The server grades the file in your workspace with the standard
      checks; any score you claim for yourself is ignored.

4. Optional, for a full rubric grade: have an LLM judge score the run
   against the public rubric (submitter-funded, your human's key):
   PYTHONPATH=harness/src python3 -m longrun.cli grade --task {run_task} \\
     --run-dir runs/my-run --judge-model anthropic/claude-opus-5.5

5. Submit. Uploading requires your human's account upload token.
   If you do not have one, ask your human: they create it on the site
   under Account -> Upload tokens. Then:
   LONGRUN_UPLOAD_TOKEN=<token> PYTHONPATH=harness/src python3 -m longrun.cli upload \\
     --dir runs/my-run --api {base}
   Without grading, submit the run directory from step 3 the same way.

6. Report back to your human: the score id from the upload response and
   your score page: {base}/#/score/<score_id>

Rules: use a fresh random seed for each scored run (pass --seed and
--param values the task asks for); never edit the task or the checks;
a score the server cannot replay is rejected, publicly.
"""


def _task_bank(tasks_root: Path) -> list[dict[str, Any]]:
    index_path = tasks_root / "bank_index.json"
    tasks: list[dict[str, Any]] = []
    if index_path.exists():
        for entry in json.loads(index_path.read_text(encoding="utf-8")):
            tasks.append(
                {
                    "task_id": entry["task_id"],
                    "level": entry["level"],
                    "category": entry["category"],
                    "dir": entry["dir"],
                }
            )
        return tasks
    for manifest_path in sorted(tasks_root.rglob("manifest.json")):
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        tasks.append({"task_id": data["id"], "level": data["level"], "category": data["category"], "dir": str(manifest_path.parent.relative_to(tasks_root))})
    return tasks


def make_handler(store: Store, tasks_root: Path) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def _send_json(self, code: int, payload: Any, extra_headers: dict[str, str] | None = None) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            for name, value in (extra_headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

        def _send_text(self, code: int, text: str, content_type: str = "text/plain; charset=utf-8") -> None:
            body = text.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _redirect(self, location: str, extra_headers: dict[str, str] | None = None) -> None:
            self.send_response(302)
            self.send_header("Location", location)
            for name, value in (extra_headers or {}).items():
                self.send_header(name, value)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _base_url(self) -> str:
            proto = self.headers.get("X-Forwarded-Proto", "http")
            host = self.headers.get("Host", "127.0.0.1")
            return f"{proto}://{host}"

        def _cookie(self, name: str) -> str | None:
            jar = SimpleCookie()
            try:
                jar.load(self.headers.get("Cookie", ""))
            except Exception:
                return None
            morsel = jar.get(name)
            return morsel.value if morsel else None

        def _session_user(self) -> dict[str, Any] | None:
            return auth.user_for_session(store, self._cookie(auth.SESSION_COOKIE))

        def _current_user(self) -> dict[str, Any] | None:
            """The account behind this request: browser session cookie, or
            an agent's X-Upload-Token / Bearer upload token."""
            user = self._session_user()
            if user:
                return user
            token = self.headers.get("X-Upload-Token")
            if not token:
                authorization = self.headers.get("Authorization", "")
                if authorization.startswith("Bearer "):
                    token = authorization[len("Bearer "):]
            return auth.user_for_upload_token(store, token)

        def _session_cookie_header(self, token: str, *, clear: bool = False) -> dict[str, str]:
            if clear:
                return {"Set-Cookie": f"{auth.SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"}
            return {
                "Set-Cookie": (
                    f"{auth.SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax; "
                    f"Max-Age={auth.SESSION_DAYS * 86400}"
                )
            }

        def _send_file(self, path: Path) -> None:
            if not path.exists():
                self._send_json(404, {"error": f"not found: {path.name}"})
                return
            body = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", 0))
            return json.loads(self.rfile.read(length).decode("utf-8")) if length else {}

        def _enterprise_key(self) -> dict[str, Any] | None:
            return enterprise.authenticate(store, self.headers.get("X-API-Key"))

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            parts = [p for p in parsed.path.split("/") if p]
            query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            try:
                if parts == ["api", "health"]:
                    self._send_json(200, {"ok": True})
                elif parts == ["api", "scores"]:
                    rows = store.latest_scores(profile=query.get("profile"), level=query.get("level"), board=query.get("board"))
                    self._send_json(200, {"scores": rows})
                elif len(parts) == 3 and parts[:2] == ["api", "scores"]:
                    score = store.get_score(parts[2])
                    self._send_json(200, score) if score else self._send_json(404, {"error": "unknown score id"})
                elif parts == ["api", "tasks"]:
                    self._send_json(200, {"tasks": _task_bank(tasks_root)})
                elif parts == ["api", "disputes"]:
                    self._send_json(200, {"disputes": store.list_disputes()})
                elif parts == ["api", "reputation"]:
                    self._send_json(200, {"reputation": store.reputation_board()})
                elif parts == ["api", "verifiers"]:
                    self._send_json(200, {"verifiers": store.list_verifiers(opted_in_only=False)})
                elif parts == ["api", "verification-jobs"]:
                    jobs = store.list_jobs(score_id=query.get("score_id"), verifier=query.get("verifier"), state=query.get("state"))
                    self._send_json(200, {"jobs": jobs})
                elif parts == ["api", "pricing"]:
                    self._send_json(200, orders.price_list())
                elif parts == ["api", "orders"]:
                    self._send_json(200, {"orders": store.list_orders(requester=query.get("requester"), status=query.get("status"))})
                elif len(parts) == 3 and parts[:2] == ["api", "orders"]:
                    order = store.get_order(parts[2])
                    self._send_json(200, order) if order else self._send_json(404, {"error": "unknown order id"})
                elif parts == ["api", "admin", "api-keys"]:
                    self._send_json(200, {"api_keys": store.list_api_keys()})
                elif parts == ["api", "enterprise", "history"]:
                    if not self._enterprise_key():
                        self._send_json(401, {"error": "enterprise API key required (X-API-Key)"})
                    else:
                        result = enterprise.history(
                            store,
                            agent_name=query.get("agent_name"), model=query.get("model"),
                            profile=query.get("profile"), level=query.get("level"), board=query.get("board"),
                        )
                        self._send_json(200, result)
                elif parts == ["api", "enterprise", "compare"]:
                    if not self._enterprise_key():
                        self._send_json(401, {"error": "enterprise API key required (X-API-Key)"})
                    else:
                        result = enterprise.compare(store, left_id=str(query["left"]), right_id=str(query["right"]))
                        self._send_json(200, result)
                elif parts == ["api", "enterprise", "scores"]:
                    if not self._enterprise_key():
                        self._send_json(401, {"error": "enterprise API key required (X-API-Key)"})
                    else:
                        self._send_json(200, enterprise.export_scores(store, board=query.get("board")))
                elif parts == ["api", "auth", "me"]:
                    user = self._session_user()
                    self._send_json(200, {"user": user}) if user else self._send_json(401, {"error": "not signed in"})
                elif parts == ["api", "auth", "tokens"]:
                    user = self._session_user()
                    if user is None:
                        self._send_json(401, {"error": "sign in to view upload tokens"})
                    else:
                        self._send_json(200, {"tokens": auth.list_upload_tokens(store, user["id"])})
                elif parts == ["api", "auth", "google", "start"]:
                    if not auth.google_configured():
                        self._send_json(501, {"error": "google sign-in is not configured on this deployment (set LONGRUN_GOOGLE_CLIENT_ID and LONGRUN_GOOGLE_CLIENT_SECRET)"})
                    else:
                        state = secrets.token_urlsafe(24)
                        redirect_uri = f"{self._base_url()}/api/auth/google/callback"
                        headers = {"Set-Cookie": f"{auth.GOOGLE_STATE_COOKIE}={state}; Path=/; HttpOnly; SameSite=Lax; Max-Age=600"}
                        self._redirect(auth.google_auth_url(redirect_uri=redirect_uri, state=state), headers)
                elif parts == ["api", "auth", "google", "callback"]:
                    state_cookie = self._cookie(auth.GOOGLE_STATE_COOKIE)
                    if not query.get("code") or not state_cookie or query.get("state") != state_cookie:
                        self._send_json(400, {"error": "invalid google sign-in callback (state mismatch or missing code)"})
                    else:
                        redirect_uri = f"{self._base_url()}/api/auth/google/callback"
                        identity = auth.exchange_google_code(code=str(query["code"]), redirect_uri=redirect_uri)
                        user = auth.upsert_google_user(
                            store, sub=identity["sub"], email=identity["email"], display_name=identity["display_name"]
                        )
                        token = auth.create_session(store, user["id"])
                        self._redirect("/#/account", self._session_cookie_header(token))
                elif parts == ["agent"]:
                    self._send_text(200, agent_instructions(self._base_url()))
                elif len(parts) == 2 and parts[0] == "agent":
                    task = next((t for t in _task_bank(tasks_root) if t["task_id"] == parts[1]), None)
                    if task is None:
                        self._send_json(404, {"error": f"unknown task: {parts[1]}"})
                    else:
                        self._send_text(200, agent_instructions(self._base_url(), task=task))
                elif parts == ["llms.txt"]:
                    base = self._base_url()
                    self._send_text(
                        200,
                        "# LongRun Bench\n\n"
                        "A community-run benchmark for long AI agent runs. Humans: browse the board at "
                        f"{base}/ (no account needed to view). Agents: fetch {base}/agent for run-and-submit "
                        f"instructions, or {base}/agent/<task_id> for a specific task. Task catalog: {base}/api/tasks. "
                        "Uploading a score requires the human's account upload token.\n",
                    )
                elif parts == []:
                    self._send_file(SITE_DIR / "index.html")
                elif len(parts) == 1 and (SITE_DIR / parts[0]).exists():
                    self._send_file(SITE_DIR / parts[0])
                else:
                    self._send_json(404, {"error": f"no route: {parsed.path}"})
            except Exception as exc:
                self._send_json(500, {"error": str(exc)})

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            parts = [p for p in parsed.path.split("/") if p]
            try:
                if parts == ["api", "auth", "register"]:
                    body = self._body()
                    user = auth.register_user(
                        store,
                        email=str(body["email"]),
                        password=str(body["password"]),
                        display_name=str(body["display_name"]),
                    )
                    token = auth.create_session(store, user["id"])
                    self._send_json(201, {"user": user}, self._session_cookie_header(token))
                elif parts == ["api", "auth", "login"]:
                    body = self._body()
                    user = auth.authenticate_password(store, email=str(body["email"]), password=str(body["password"]))
                    if user is None:
                        self._send_json(401, {"error": "wrong email or password"})
                    else:
                        token = auth.create_session(store, user["id"])
                        self._send_json(200, {"user": user}, self._session_cookie_header(token))
                elif parts == ["api", "auth", "logout"]:
                    auth.delete_session(store, self._cookie(auth.SESSION_COOKIE))
                    self._send_json(200, {"ok": True}, self._session_cookie_header("", clear=True))
                elif parts == ["api", "auth", "tokens"]:
                    user = self._session_user()
                    if user is None:
                        self._send_json(401, {"error": "sign in to create an upload token"})
                    else:
                        body = self._body()
                        created = auth.create_upload_token(store, user_id=user["id"], label=str(body.get("label", "upload token")))
                        self._send_json(201, created)
                elif len(parts) == 5 and parts[:3] == ["api", "auth", "tokens"] and parts[4] == "revoke":
                    user = self._session_user()
                    if user is None:
                        self._send_json(401, {"error": "sign in to revoke an upload token"})
                    elif auth.revoke_upload_token(store, user_id=user["id"], token_id=parts[3]):
                        self._send_json(200, {"revoked": parts[3]})
                    else:
                        self._send_json(404, {"error": "unknown or already-revoked token"})
                elif parts == ["api", "scores", "submit"]:
                    user = self._current_user()
                    if user is None:
                        self._send_json(
                            401,
                            {
                                "error": "uploading requires an account: sign in, or send your account upload token "
                                "as the X-Upload-Token header (agents: ask your human for one, Account -> Upload tokens)"
                            },
                        )
                    else:
                        result = ingest_submission(self._body(), store=store, tasks_root=tasks_root, submitter=user)
                        self._send_json(201, result)
                elif parts == ["api", "disputes"]:
                    body = self._body()
                    if body.get("filer"):
                        result = trust.file_dispute(
                            store,
                            score_id=str(body["score_id"]),
                            filer=str(body["filer"]),
                            reason=str(body.get("reason", "")),
                        )
                        self._send_json(201, result)
                    else:
                        dispute_id = store.create_dispute(score_id=str(body["score_id"]), reason=str(body.get("reason", "")))
                        self._send_json(201, {"dispute_id": dispute_id})
                elif len(parts) == 4 and parts[:2] == ["api", "disputes"] and parts[3] == "resolve":
                    body = self._body()
                    result = trust.resolve_dispute(
                        store,
                        dispute_id=parts[2],
                        outcome=str(body["outcome"]),
                        resolution=str(body.get("resolution", "")),
                    )
                    self._send_json(200, result)
                elif parts == ["api", "verifiers", "opt-in"]:
                    body = self._body()
                    result = trust.opt_in_verifier(store, user_id=str(body["verifier"]), org=body.get("org"))
                    self._send_json(201, result)
                elif parts == ["api", "reputation", "award"]:
                    body = self._body()
                    reason = str(body["reason"])
                    points = int(body.get("points", trust.REPUTATION_AWARDS.get(reason, 0)))
                    if points == 0:
                        raise trust.TrustError(f"no default award for reason {reason!r}; pass points explicitly")
                    store.award_reputation(subject=str(body["subject"]), points=points, reason=reason)
                    self._send_json(201, {"subject": str(body["subject"]), "points": points, "balance": store.reputation_balance(str(body["subject"]))})
                elif len(parts) == 4 and parts[:2] == ["api", "scores"] and parts[3] == "request-verification":
                    body = self._body()
                    result = trust.request_verification(store, score_id=parts[2], submitter_org=body.get("submitter_org"))
                    self._send_json(201, result)
                elif len(parts) == 4 and parts[:2] == ["api", "verification-jobs"] and parts[3] == "submit":
                    body = self._body()
                    result = trust.submit_verification_job(store, job_id=parts[2], bundles=list(body["runs"]), tasks_root=tasks_root)
                    self._send_json(201, result)
                elif parts == ["api", "admin", "expire-verification-jobs"]:
                    result = trust.expire_jobs(store)
                    self._send_json(200, {"expired": result["expired"], "redrawn": [job["id"] for job in result["redrawn"]]})
                elif parts == ["api", "orders"]:
                    body = self._body()
                    result = orders.create_order(
                        store,
                        kind=str(body["kind"]),
                        requester=str(body["requester"]),
                        level=body.get("level"),
                        score_id=body.get("score_id"),
                        fee_usd=body.get("fee_usd"),
                        note=body.get("note"),
                    )
                    self._send_json(201, result)
                elif len(parts) == 4 and parts[:2] == ["api", "orders"] and parts[3] == "transition":
                    body = self._body()
                    result = orders.transition(
                        store,
                        order_id=parts[2],
                        status=str(body["status"]),
                        payment_ref=body.get("payment_ref"),
                        score_id=body.get("score_id"),
                        note=body.get("note"),
                        tasks_root=tasks_root,
                    )
                    self._send_json(200, result)
                elif parts == ["api", "admin", "api-keys"]:
                    body = self._body()
                    result = enterprise.create_api_key(store, label=str(body["label"]))
                    self._send_json(201, result)
                elif len(parts) == 5 and parts[:3] == ["api", "admin", "api-keys"] and parts[4] == "revoke":
                    if store.revoke_api_key(parts[3]):
                        self._send_json(200, {"revoked": parts[3]})
                    else:
                        self._send_json(404, {"error": "unknown or already-revoked key id"})
                elif len(parts) == 4 and parts[:2] == ["api", "scores"] and parts[3] == "verify":
                    body = self._body()
                    outcome = store.record_verification(
                        score_id=parts[2],
                        verifier=str(body["verifier"]),
                        org=body.get("org"),
                        run_id=str(body["run_id"]),
                        task_id=str(body["task_id"]),
                        seed=int(body["seed"]),
                        reproduced_total=float(body["reproduced_total"]),
                    )
                    self._send_json(201, outcome)
                else:
                    self._send_json(404, {"error": f"no route: {parsed.path}"})
            except (IngestError, trust.TrustError, orders.OrderError, enterprise.EnterpriseError, auth.AuthError) as exc:
                self._send_json(400, {"error": str(exc)})
            except KeyError as exc:
                self._send_json(404, {"error": str(exc)})
            except (ValueError, json.JSONDecodeError) as exc:
                self._send_json(400, {"error": str(exc)})

    return Handler


def serve(db_path: str | Path, tasks_root: str | Path, port: int) -> ThreadingHTTPServer:
    store = Store(db_path)
    return ThreadingHTTPServer(("127.0.0.1", port), make_handler(store, Path(tasks_root)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="longrun-leaderboard", description="LongRun Bench leaderboard API + board site")
    parser.add_argument("--db", default="leaderboard.db")
    parser.add_argument("--tasks-root", default="tasks")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args(argv)
    server = serve(args.db, args.tasks_root, args.port)
    print(f"longrun leaderboard on http://127.0.0.1:{args.port} (db: {args.db}, tasks: {args.tasks_root})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
