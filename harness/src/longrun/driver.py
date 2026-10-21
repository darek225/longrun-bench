from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from . import __version__
from .models import TaskInstance
from .tools import ToolError, WorkspaceTools, summarize_result

SYSTEM_PROMPT_TEMPLATE = """You are being evaluated on a long multi-step task. Rules:
- You have {steps} tool calls and {minutes} minutes. One tool call = one step.
- Your deliverable is graded against a rubric: correctness (40), completeness (25), efficiency (15), error recovery (10), instruction adherence (10).
- Network access is limited to: {allowlist}. Other hosts will fail.
- When finished, call deliver with your final artifact. Partial work is graded; do not stall.
- Do not attempt to access the grading system, the rubric weights, or the task manifest.
"""

TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "shell.exec": {"required": {"command": str}, "optional": {"timeout": int}},
    "file.read": {"required": {"path": str}, "optional": {"max_chars": int}},
    "file.write": {"required": {"path": str, "content": str}, "optional": {}},
    "file.edit": {"required": {"path": str, "old_text": str, "new_text": str}, "optional": {}},
    "python.exec": {"required": {"code": str}, "optional": {"timeout": int}},
    "http.fetch": {"required": {"url": str}, "optional": {"max_chars": int}},
    "browser.task": {"required": {"goal": str}, "optional": {"max_steps": int}},
    "code.nav": {"required": {"op": str}, "optional": {"symbol": str, "file": str, "query": str}},
    "deliver": {"required": {"summary": str, "artifact_uri": str}, "optional": {"notes": str}},
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _hash_json(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _hash_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _type_matches(value: Any, expected: type) -> bool:
    if expected is int:
        return isinstance(value, int) and not isinstance(value, bool)
    if expected is str:
        return isinstance(value, str)
    if expected is dict:
        return isinstance(value, dict)
    if expected is list:
        return isinstance(value, list)
    return isinstance(value, expected)


def validate_tool_call(call: dict[str, Any]) -> str | None:
    name = call.get("name")
    args = call.get("args")
    if not isinstance(name, str) or not name:
        return "tool call requires a string name"
    if name not in TOOL_SCHEMAS:
        return f"unknown tool: {name}"
    if not isinstance(args, dict):
        return f"{name} requires args to be an object"
    schema = TOOL_SCHEMAS[name]
    for key, expected in schema["required"].items():
        if key not in args:
            return f"{name} missing required arg: {key}"
        if not _type_matches(args[key], expected):
            return f"{name} arg {key} must be {expected.__name__}"
    for key, expected in schema["optional"].items():
        if key in args and not _type_matches(args[key], expected):
            return f"{name} arg {key} must be {expected.__name__}"
    if name == "code.nav":
        op = args.get("op")
        if op not in {"find_definition", "find_references", "list_symbols", "search_symbols"}:
            return f"code.nav unknown op: {op}"
        if op in {"find_definition", "find_references"} and "symbol" not in args:
            return f"code.nav {op} requires symbol"
        if op == "list_symbols" and "file" not in args:
            return "code.nav list_symbols requires file"
        if op == "search_symbols" and "query" not in args:
            return "code.nav search_symbols requires query"
    return None


@dataclass
class AdapterResponse:
    text: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    refusal: bool = False
    usage: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_any(cls, value: Any) -> "AdapterResponse":
        if isinstance(value, cls):
            return value
        if isinstance(value, dict):
            return cls(
                text=str(value.get("text", "")),
                tool_calls=list(value.get("tool_calls", [])),
                error=value.get("error"),
                refusal=bool(value.get("refusal", False)),
                usage=dict(value.get("usage", {})),
            )
        return cls(error=f"adapter returned unsupported response type: {type(value).__name__}")


class Adapter(Protocol):
    context_window: int

    def complete(self, history: list[dict[str, Any]], tools: dict[str, Any]) -> AdapterResponse | dict[str, Any]:
        ...


class ScriptedAdapter:
    """Deterministic adapter used by conformance tests and smoke runs."""

    context_window = 128000

    def __init__(self, responses: list[dict[str, Any]]):
        self._responses = list(responses)
        self.calls = 0

    def complete(self, history: list[dict[str, Any]], tools: dict[str, Any]) -> AdapterResponse:
        self.calls += 1
        if not self._responses:
            return AdapterResponse(error="script exhausted")
        return AdapterResponse.from_any(self._responses.pop(0))


# Ultra memory file (docs/plan/15-final-mile.md §8): the harness creates it
# empty at run start and persists it across sessions. The agent structures it
# freely; this skeleton is a suggestion, not a requirement.
MEMORY_TEMPLATE = """# Memory — {task_id} — session 1

## Goals
- [ ] ...

## State
<!-- What is done, what is in progress. Updated every session. -->

## Open questions
<!-- Things the agent still needs to figure out. -->

## Session log
<!-- Append-only: date, what was attempted, outcome. -->
"""


def seed_ultra_memory(workspace: str | Path, task_id: str) -> Path | None:
    """Create the Ultra memory file if the workspace does not have one yet.

    Never overwrites: an existing memory.md is the agent's own state.
    """
    path = Path(workspace) / "memory.md"
    if path.exists():
        return None
    path.write_text(MEMORY_TEMPLATE.format(task_id=task_id), encoding="utf-8")
    return path


@dataclass
class RunResult:
    run_id: str
    end_reason: str
    events: list[dict[str, Any]]
    deliverable: dict[str, Any] | None
    totals: dict[str, Any]
    transcript_path: Path


class TranscriptWriter:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.events: list[dict[str, Any]] = []
        if self.path.exists():
            # Resumed Ultra session (docs/plan/09 §4): the transcript is one
            # record across sessions, so earlier events are part of this run.
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    self.events.append(json.loads(line))

    def log(self, event_type: str, **fields: Any) -> dict[str, Any]:
        event = {"t": _utc_now(), "type": event_type, **fields}
        self.events.append(event)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True, default=str) + "\n")
        return event


class Driver:
    def __init__(self, tools: WorkspaceTools, transcript_path: str | Path, *, harness_version: str = __version__):
        self.tools = tools
        self.transcript = TranscriptWriter(transcript_path)
        self.harness_version = harness_version

    def run(
        self,
        instance: TaskInstance,
        adapter: Adapter,
        *,
        agent: dict[str, Any],
        run_id: str | None = None,
        initial_steps: int = 0,
        initial_input_tokens: int = 0,
        initial_output_tokens: int = 0,
        initial_wall_clock_s: float = 0.0,
        session_number: int | None = None,
        session_step_cap: int | None = None,
    ) -> RunResult:
        # Session mode (Ultra, docs/plan/09 §4): run_id and the cumulative
        # counters carry over from the snapshot; budgets are enforced on the
        # cumulative totals, and session_step_cap pauses instead of ending.
        run_id = run_id or str(uuid.uuid4())
        start = time.monotonic()
        steps = int(initial_steps)
        session_steps = 0
        input_tokens = int(initial_input_tokens)
        output_tokens = int(initial_output_tokens)
        consecutive_errors = 0
        text_only_streak = 0
        turns = 0
        warned = False
        deliverable: dict[str, Any] | None = None
        end_reason = "error"

        allowlist = ", ".join(instance.network_allowlist) if instance.network_allowlist else "none"
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            steps=instance.budgets.steps,
            minutes=instance.budgets.wall_clock_minutes,
            allowlist=allowlist,
        )
        history: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": instance.prompt},
        ]
        resumed = session_number is not None and session_number > 1
        if not resumed:
            self.transcript.log(
                "run_start",
                run_id=run_id,
                agent=agent,
                task={"id": instance.task_id, "instance_seed": instance.seed, "task_set": instance.task_set_version},
                harness={"version": self.harness_version, "hash": "sha256:local-dev"},
                budgets=instance.budgets.to_dict(),
            )
            self.transcript.log("prompt", step=0, text_hash=_hash_text(instance.prompt))
        if session_number is not None:
            self.transcript.log(
                "session_resume" if resumed else "session_start",
                session=session_number,
                step=steps,
                steps_before=steps if resumed else 0,
            )
        if instance.level == 3:
            seeded = seed_ultra_memory(self.tools.workspace, instance.task_id)
            if seeded is not None:
                self.transcript.log("memory_seeded", path="memory.md", task_id=instance.task_id)

        remaining_steps = instance.budgets.steps - steps
        allowance = remaining_steps if session_step_cap is None else min(remaining_steps, session_step_cap)
        max_turns = max(1, allowance) * 3 + 12
        while True:
            elapsed = time.monotonic() - start
            if session_step_cap is not None and session_steps >= session_step_cap and steps < instance.budgets.steps:
                self.transcript.log("session_pause", step=steps, session=session_number)
                end_reason = "session_pause"
                break
            if steps >= instance.budgets.steps or (initial_wall_clock_s + elapsed) >= instance.budgets.wall_clock_minutes * 60:
                self.transcript.log("budget_exceeded", step=steps)
                end_reason = "budget"
                break
            if turns >= max_turns:
                self.transcript.log("model_error", step=steps, error="driver turn limit exceeded")
                end_reason = "error"
                break
            turns += 1

            try:
                response = AdapterResponse.from_any(adapter.complete(history, TOOL_SCHEMAS))
            except Exception as exc:  # adapter/provider failures are run data, not harness crashes.
                response = AdapterResponse(error=str(exc))

            input_tokens += int(response.usage.get("input_tokens", 0))
            output_tokens += int(response.usage.get("output_tokens", 0))

            if response.error:
                consecutive_errors += 1
                self.transcript.log("model_error", step=steps, error=str(response.error)[:500])
                if consecutive_errors >= 3:
                    end_reason = "error"
                    break
                history.append({"role": "user", "content": f"Model error: {response.error}. Continue with a tool call or deliver."})
                continue
            consecutive_errors = 0

            if response.refusal:
                self.transcript.log("model_error", step=steps, error="model refused the task")
                end_reason = "error"
                break

            if not response.tool_calls:
                if not response.text.strip():
                    consecutive_errors += 1
                    self.transcript.log("model_error", step=steps, error="empty model response")
                    if consecutive_errors >= 3:
                        end_reason = "error"
                        break
                    history.append({"role": "user", "content": "Empty response. Call a tool or call deliver."})
                    continue
                text_only_streak += 1
                history.append({"role": "assistant", "content": response.text})
                if text_only_streak >= 3:
                    self.transcript.log("nudge", step=steps, reason="text_only_streak")
                    history.append({"role": "user", "content": "You have not called a tool in 3 turns. Call a tool or call deliver."})
                    text_only_streak = 0
                continue
            text_only_streak = 0

            should_end = False
            for call in response.tool_calls:
                steps += 1
                session_steps += 1
                name = str(call.get("name", ""))
                args = call.get("args", {}) if isinstance(call.get("args", {}), dict) else {}
                # Record the call itself so provider adapters can render a valid
                # conversation (tool results must follow their tool call).
                history.append({"role": "assistant", "tool_call": {"name": name, "args": args}})

                if not warned and steps >= int(instance.budgets.steps * 0.8):
                    warned = True
                    self.transcript.log("budget_warning", step=steps, steps_left=instance.budgets.steps - steps)

                validation_error = validate_tool_call(call)
                if validation_error:
                    result = {"error": f"invalid tool call: {validation_error}", "hint": "Check the argument names and types, then retry."}
                    self.transcript.log(
                        "tool_call",
                        step=steps,
                        tool=name or "unknown",
                        args_hash=_hash_json(args),
                        result_summary=summarize_result(name or "unknown", result),
                        duration_ms=0,
                    )
                    history.append({"role": "tool", "name": name, "content": json.dumps(result, default=str)})
                elif name == "deliver":
                    artifact_uri = str(args["artifact_uri"])
                    try:
                        artifact_path = self.tools.resolve_path(artifact_uri)
                    except ToolError as exc:
                        artifact_path = None
                        result = {"error": str(exc), "hint": "Deliver an artifact inside the workspace."}
                        self.transcript.log("tool_call", step=steps, tool="deliver", args_hash=_hash_json(args), result_summary=summarize_result("deliver", result), duration_ms=0)
                        history.append({"role": "tool", "name": "deliver", "content": json.dumps(result, default=str)})
                    if artifact_path is not None:
                        if not artifact_path.exists():
                            result = {"error": f"deliverable artifact does not exist: {artifact_uri}", "hint": "Write the artifact before calling deliver."}
                            self.transcript.log("tool_call", step=steps, tool="deliver", args_hash=_hash_json(args), result_summary=summarize_result("deliver", result), duration_ms=0)
                            history.append({"role": "tool", "name": "deliver", "content": json.dumps(result, default=str)})
                        else:
                            artifact_hash = _hash_text(artifact_path.read_text(encoding="utf-8", errors="replace"))
                            deliverable = {
                                "summary": str(args["summary"]),
                                "artifact_uri": artifact_uri,
                                "artifact_path": str(artifact_path),
                                "artifact_hash": artifact_hash,
                                "notes": str(args.get("notes", "")),
                            }
                            self.transcript.log("deliverable", step=steps, artifact_hash=artifact_hash, artifact_uri=artifact_uri)
                            end_reason = "deliverable"
                            should_end = True
                            break
                else:
                    started = time.monotonic()
                    try:
                        result = self.tools.execute(name, args)
                    except Exception as exc:
                        result = {"error": str(exc)}
                    duration_ms = int((time.monotonic() - started) * 1000)
                    self.transcript.log(
                        "tool_call",
                        step=steps,
                        tool=name,
                        args_hash=_hash_json(args),
                        result_summary=summarize_result(name, result),
                        duration_ms=duration_ms,
                    )
                    history.append({"role": "tool", "name": name, "content": json.dumps(result, default=str)[:20000]})

                if steps >= instance.budgets.steps:
                    self.transcript.log("budget_exceeded", step=steps)
                    end_reason = "budget"
                    should_end = True
                    break
                if session_step_cap is not None and session_steps >= session_step_cap:
                    self.transcript.log("session_pause", step=steps, session=session_number)
                    end_reason = "session_pause"
                    should_end = True
                    break

            history = self._maybe_compact(history, adapter)
            if should_end:
                break

        totals = {
            "steps": steps,
            "wall_clock_s": round(initial_wall_clock_s + (time.monotonic() - start), 4),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }
        if session_number is not None:
            totals["session"] = session_number
            totals["session_steps"] = session_steps
        self.transcript.log("run_end", step=steps, reason=end_reason, totals=totals)
        return RunResult(
            run_id=run_id,
            end_reason=end_reason,
            events=self.transcript.events,
            deliverable=deliverable,
            totals=totals,
            transcript_path=self.transcript.path,
        )

    def _maybe_compact(self, history: list[dict[str, Any]], adapter: Adapter) -> list[dict[str, Any]]:
        context_window = int(getattr(adapter, "context_window", 128000))
        estimated_tokens = sum(len(str(item.get("content", ""))) for item in history) // 4
        if estimated_tokens <= int(context_window * 0.8) or len(history) <= 24:
            return history
        keep_head = history[:2]
        keep_tail = history[-20:]
        middle = history[2:-20]
        tool_names = [str(item.get("name", "message")) for item in middle if item.get("role") == "tool"]
        summary = {
            "role": "user",
            "content": "[COMPACTED SUMMARY] Earlier tool history was compacted. Tool calls in compacted region: " + ", ".join(tool_names[:80]),
        }
        self.transcript.log("compaction", step=0, compacted_messages=len(middle))
        return keep_head + [summary] + keep_tail
