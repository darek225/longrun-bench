from __future__ import annotations

import argparse
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from . import trust
from .ingest import IngestError, ingest_submission
from .store import Store

SITE_DIR = Path(__file__).resolve().parent / "site"


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

        def _send_json(self, code: int, payload: Any) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

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
                if parts == ["api", "scores", "submit"]:
                    result = ingest_submission(self._body(), store=store, tasks_root=tasks_root)
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
            except (IngestError, trust.TrustError) as exc:
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
