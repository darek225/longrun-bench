from __future__ import annotations

import argparse
import json
import shutil
import threading
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .adapters import make_adapter
from .cli import _copy_fixtures, _finish_run
from .driver import Driver, ScriptedAdapter, TranscriptWriter, _hash_text
from .manifest import load_manifest, render_instance
from .models import Budgets
from .tools import WorkspaceTools


@dataclass
class RunEntry:
    run_id: str
    mode: str
    state: str = "running"  # running | done | failed
    task_dir: Path | None = None
    instance: Any = None
    agent: dict[str, Any] = field(default_factory=dict)
    out_dir: Path | None = None
    workspace: Path | None = None
    result: Any = None
    error: str | None = None
    thread: threading.Thread | None = None


class RunStore:
    """In-memory run registry behind the harness protocol (docs/plan/01-harness.md §5).

    Modes:
    - scripted/model: the server runs the driver itself in a thread.
    - external: the server creates the run and waits for POST /run/{id}/deliver
      (the native/bare protocol path). The delivered artifact is graded by the
      server with the standard checks; vendor-reported scores are ignored.
    """

    def __init__(self, tasks_root: str | Path, runs_root: str | Path):
        self.tasks_root = Path(tasks_root)
        self.runs_root = Path(runs_root)
        self.runs_root.mkdir(parents=True, exist_ok=True)
        self._runs: dict[str, RunEntry] = {}
        self._lock = threading.Lock()
        self._task_index: dict[str, Path] | None = None

    # -- task resolution -------------------------------------------------
    def _index_tasks(self) -> dict[str, Path]:
        if self._task_index is None:
            index: dict[str, Path] = {}
            for manifest_path in self.tasks_root.rglob("manifest.json"):
                try:
                    data = json.loads(manifest_path.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if "id" in data:
                    index[str(data["id"])] = manifest_path.parent
            self._task_index = index
        return self._task_index

    def _resolve_task_dir(self, payload: dict[str, Any]) -> Path:
        if payload.get("task_dir"):
            return Path(str(payload["task_dir"]))
        task_id = payload.get("task_id")
        if task_id:
            index = self._index_tasks()
            if str(task_id) in index:
                return index[str(task_id)]
            raise ValueError(f"unknown task_id: {task_id}")
        raise ValueError("run request requires task_id or task_dir")

    # -- run lifecycle ---------------------------------------------------
    def create_run(self, payload: dict[str, Any]) -> str:
        merged: dict[str, Any] = {}
        if isinstance(payload.get("task_instance"), dict):
            merged.update(payload["task_instance"])
        merged.update({key: value for key, value in payload.items() if key != "task_instance"})
        task_dir = self._resolve_task_dir(merged)
        manifest = load_manifest(task_dir)
        instance = render_instance(manifest, seed=int(merged.get("seed", 42)), overrides=dict(merged.get("params", {})))
        if isinstance(merged.get("budgets"), dict):
            budgets = merged["budgets"]
            instance.budgets = Budgets(
                steps=int(budgets.get("steps", instance.budgets.steps)),
                wall_clock_minutes=int(budgets.get("wall_clock_minutes", instance.budgets.wall_clock_minutes)),
            )
        adapter_spec = dict(merged.get("adapter", {}))
        mode = str(adapter_spec.get("type", "external"))
        agent = dict(merged.get("agent", {})) or {"name": "protocol-client", "model": "unknown", "profile": "standard"}
        run_id = str(uuid.uuid4())
        out_dir = self.runs_root / run_id
        workspace = out_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        _copy_fixtures(task_dir, workspace)
        entry = RunEntry(
            run_id=run_id,
            mode=mode,
            task_dir=task_dir,
            instance=instance,
            agent=agent,
            out_dir=out_dir,
            workspace=workspace,
        )
        with self._lock:
            self._runs[run_id] = entry
        if mode in ("scripted", "model"):
            thread = threading.Thread(target=self._execute, args=(entry, adapter_spec), daemon=True)
            entry.thread = thread
            thread.start()
        elif mode == "external":
            writer = TranscriptWriter(out_dir / "transcript.jsonl")
            writer.log(
                "run_start",
                run_id=run_id,
                agent=agent,
                task={"id": instance.task_id, "instance_seed": instance.seed, "task_set": instance.task_set_version},
                harness={"version": "0.1.0", "hash": "sha256:local-dev"},
                budgets=instance.budgets.to_dict(),
            )
            writer.log("prompt", step=0, text_hash=_hash_text(instance.prompt))
        else:
            entry.state = "failed"
            entry.error = f"unknown adapter type: {mode}"
        return run_id

    def _execute(self, entry: RunEntry, adapter_spec: dict[str, Any]) -> None:
        try:
            if entry.mode == "scripted":
                responses = adapter_spec.get("responses")
                if not isinstance(responses, list):
                    raise ValueError("scripted adapter requires a responses list")
                adapter: Any = ScriptedAdapter(responses)
            else:
                adapter = make_adapter(str(adapter_spec.get("model", "")), base_url=adapter_spec.get("base_url"))
            tools = WorkspaceTools(entry.workspace, allowlist=entry.instance.network_allowlist)
            driver = Driver(tools, entry.out_dir / "transcript.jsonl")
            result = driver.run(entry.instance, adapter, agent=entry.agent)
            entry.result = result
            _finish_run(entry.out_dir, entry.workspace, entry.instance, result, entry.agent)
            entry.state = "done" if result.end_reason in ("deliverable", "budget", "error") else "failed"
        except Exception as exc:
            entry.state = "failed"
            entry.error = str(exc)

    def deliver(self, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        entry = self._get(run_id)
        if entry.mode != "external":
            raise ValueError("deliver is only valid for external-mode runs")
        if entry.state != "running":
            raise ValueError(f"run is not awaiting a deliverable (state={entry.state})")
        artifact_uri = str(payload.get("artifact_uri", "deliverable.md"))
        content = str(payload.get("artifact_content", ""))
        tools = WorkspaceTools(entry.workspace, allowlist=entry.instance.network_allowlist)
        artifact_path = tools.resolve_path(artifact_uri)
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(content, encoding="utf-8")
        steps_used = int(payload.get("steps_used", 1))
        totals = {
            "steps": steps_used,
            "wall_clock_s": float(payload.get("wall_clock_s", 0.0)),
            "input_tokens": int(payload.get("input_tokens", 0)),
            "output_tokens": int(payload.get("output_tokens", 0)),
        }
        writer = TranscriptWriter(entry.out_dir / "transcript.jsonl")
        writer.events = self._read_events(entry)
        artifact_hash = _hash_text(content)
        writer.log("deliverable", step=steps_used, artifact_hash=artifact_hash, artifact_uri=artifact_uri)
        writer.log("run_end", step=steps_used, reason="deliverable", totals=totals)
        result = SimpleNamespace(
            run_id=run_id,
            end_reason="deliverable",
            totals=totals,
            deliverable={
                "summary": str(payload.get("summary", "")),
                "artifact_uri": artifact_uri,
                "artifact_path": str(artifact_path),
                "artifact_hash": artifact_hash,
                "notes": str(payload.get("notes", "")),
            },
        )
        entry.result = result
        record = _finish_run(entry.out_dir, entry.workspace, entry.instance, result, entry.agent)
        entry.state = "done"
        return record

    # -- reads -------------------------------------------------------------
    def _get(self, run_id: str) -> RunEntry:
        with self._lock:
            entry = self._runs.get(run_id)
        if entry is None:
            raise KeyError(f"unknown run_id: {run_id}")
        return entry

    def _read_events(self, entry: RunEntry) -> list[dict[str, Any]]:
        path = (entry.out_dir or self.runs_root) / "transcript.jsonl"
        if not path.exists():
            return []
        events = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # tolerate a partially written final line
        return events

    def status(self, run_id: str) -> dict[str, Any]:
        entry = self._get(run_id)
        events = self._read_events(entry)
        steps_used = 0
        for event in events:
            if isinstance(event.get("step"), int):
                steps_used = max(steps_used, int(event["step"]))
        status: dict[str, Any] = {"run_id": run_id, "state": entry.state, "steps_used": steps_used, "mode": entry.mode}
        if entry.error:
            status["error"] = entry.error
        if entry.result is not None:
            status["end_reason"] = getattr(entry.result, "end_reason", None)
            score_path = (entry.out_dir or self.runs_root) / "score.json"
            if score_path.exists():
                score = json.loads(score_path.read_text(encoding="utf-8"))
                status["score_total"] = score.get("total")
                status["tier"] = score.get("tier")
        return status

    def transcript(self, run_id: str) -> dict[str, Any]:
        entry = self._get(run_id)
        return {"run_id": run_id, "events": self._read_events(entry)}

    def wait(self, run_id: str, timeout: float | None = None) -> dict[str, Any]:
        entry = self._get(run_id)
        if entry.thread is not None:
            entry.thread.join(timeout)
        return self.status(run_id)


def make_handler(store: RunStore) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # keep test output clean
            pass

        def _send(self, code: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", 0))
            if length == 0:
                return {}
            return json.loads(self.rfile.read(length).decode("utf-8"))

        def do_GET(self) -> None:
            parts = [part for part in self.path.split("/") if part]
            try:
                if parts == ["health"]:
                    self._send(200, {"ok": True})
                elif len(parts) == 3 and parts[0] == "run" and parts[2] == "status":
                    self._send(200, store.status(parts[1]))
                elif len(parts) == 3 and parts[0] == "run" and parts[2] == "transcript":
                    self._send(200, store.transcript(parts[1]))
                else:
                    self._send(404, {"error": f"no route: {self.path}"})
            except KeyError as exc:
                self._send(404, {"error": str(exc)})

        def do_POST(self) -> None:
            parts = [part for part in self.path.split("/") if part]
            try:
                if parts == ["run"]:
                    run_id = store.create_run(self._body())
                    self._send(201, {"run_id": run_id})
                elif len(parts) == 3 and parts[0] == "run" and parts[2] == "deliver":
                    record = store.deliver(parts[1], self._body())
                    self._send(200, record)
                else:
                    self._send(404, {"error": f"no route: {self.path}"})
            except KeyError as exc:
                self._send(404, {"error": str(exc)})
            except (ValueError, json.JSONDecodeError) as exc:
                self._send(400, {"error": str(exc)})

    return Handler


def serve(tasks_root: str | Path, runs_root: str | Path, port: int) -> ThreadingHTTPServer:
    store = RunStore(tasks_root, runs_root)
    return ThreadingHTTPServer(("127.0.0.1", port), make_handler(store))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="longrun-server", description="LongRun Bench harness protocol server")
    parser.add_argument("--tasks-root", default="tasks")
    parser.add_argument("--runs-root", default="runs")
    parser.add_argument("--port", type=int, default=8790)
    args = parser.parse_args(argv)
    server = serve(args.tasks_root, args.runs_root, args.port)
    print(f"longrun protocol server on http://127.0.0.1:{args.port} (tasks: {args.tasks_root}, runs: {args.runs_root})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
