from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Callable

from .driver import TOOL_SCHEMAS, AdapterResponse
from .pricing import price_for

Transport = Callable[[str, str, dict[str, str], dict[str, Any], float], tuple[int, dict[str, Any]]]

TOOL_DESCRIPTIONS: dict[str, str] = {
    "shell.exec": "Run a shell command in the workspace. Timeout 120s.",
    "file.read": "Read a file inside the workspace.",
    "file.write": "Write a file inside the workspace.",
    "file.edit": "Replace an exact-match string in a file (must match exactly once).",
    "python.exec": "Run Python 3 code in the workspace.",
    "http.fetch": "GET a URL and return its text. Only allowlisted hosts work.",
    "browser.task": "Text-mode browser task for multi-page navigation.",
    "code.nav": "Semantic code navigation: find_definition, find_references, list_symbols, search_symbols.",
    "deliver": "End the run and submit your final deliverable. Call this when the task is complete.",
}

_TYPE_MAP = {str: "string", int: "integer", float: "number", bool: "boolean", dict: "object", list: "array"}


def tool_definitions() -> list[dict[str, Any]]:
    definitions = []
    for name, schema in TOOL_SCHEMAS.items():
        properties: dict[str, Any] = {}
        for arg, typ in {**schema.get("optional", {}), **schema.get("required", {})}.items():
            properties[arg] = {"type": _TYPE_MAP.get(typ, "string")}
        if name == "code.nav":
            properties["op"] = {"type": "string", "enum": ["find_definition", "find_references", "list_symbols", "search_symbols"]}
        definitions.append(
            {
                "name": name,
                "description": TOOL_DESCRIPTIONS.get(name, name),
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": list(schema.get("required", {}).keys()),
                },
            }
        )
    return definitions


def urllib_transport(method: str, url: str, headers: dict[str, str], body: dict[str, Any], timeout: float) -> tuple[int, dict[str, Any]]:
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            payload = {"error": {"message": str(exc)}}
        return exc.code, payload


def _post_with_backoff(transport: Transport, url: str, headers: dict[str, str], body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """429s back off exponentially (max ~5 min total) per docs/plan/10 §5."""
    status, payload = 0, {}
    for attempt in range(4):
        status, payload = transport("POST", url, headers, body, 120.0)
        if status != 429:
            return status, payload
        if attempt < 3:
            time.sleep(min(2 ** attempt * 5, 60))
    return status, payload


def _error_message(payload: dict[str, Any], status: int) -> str:
    error = payload.get("error")
    if isinstance(error, dict) and error.get("message"):
        return f"provider HTTP {status}: {error['message']}"
    if isinstance(error, str):
        return f"provider HTTP {status}: {error}"
    return f"provider HTTP {status}: {json.dumps(payload)[:300]}"


def _split_history(history: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    system = ""
    rest = []
    for entry in history:
        if entry.get("role") == "system" and not system:
            system = str(entry.get("content", ""))
        else:
            rest.append(entry)
    return system, rest


class OpenAICompatAdapter:
    """Any OpenAI-style endpoint: OpenAI, DeepSeek, xAI, Together, local servers."""

    name = "openai_compat"

    def __init__(
        self,
        model: str,
        *,
        model_spec: str | None = None,
        base_url: str = "https://api.openai.com/v1",
        api_key_env: str | None = "OPENAI_API_KEY",
        context_window: int = 128000,
        transport: Transport | None = None,
        max_tokens: int = 4096,
    ):
        self.model = model
        self.model_spec = model_spec or model
        self.base_url = base_url.rstrip("/")
        self.api_key_env = api_key_env
        self.context_window = context_window
        self.transport = transport or urllib_transport
        self.max_tokens = max_tokens

    def price_per_mtok(self) -> tuple[float, float] | None:
        return price_for(self.model_spec)

    def count_tokens(self, messages: list[dict[str, Any]]) -> int:
        return len(json.dumps(messages, default=str)) // 4

    def _render(self, history: list[dict[str, Any]]) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        pending_ids: list[str] = []
        counter = 0
        for entry in history:
            role = entry.get("role")
            if role in ("system", "user"):
                messages.append({"role": role, "content": str(entry.get("content", ""))})
            elif role == "assistant" and "tool_call" in entry:
                counter += 1
                call_id = f"call_{counter}"
                pending_ids.append(call_id)
                call = entry["tool_call"]
                messages.append(
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": call_id,
                                "type": "function",
                                "function": {"name": call["name"], "arguments": json.dumps(call.get("args", {}))},
                            }
                        ],
                    }
                )
            elif role == "assistant":
                messages.append({"role": "assistant", "content": str(entry.get("content", ""))})
            elif role == "tool":
                call_id = pending_ids.pop(0) if pending_ids else f"call_{counter}"
                messages.append({"role": "tool", "tool_call_id": call_id, "content": str(entry.get("content", ""))})
        return messages

    def _tools(self) -> list[dict[str, Any]]:
        return [
            {"type": "function", "function": {"name": d["name"], "description": d["description"], "parameters": d["parameters"]}}
            for d in tool_definitions()
        ]

    def complete(self, history: list[dict[str, Any]], tools: dict[str, Any]) -> AdapterResponse:
        headers: dict[str, str] = {}
        if self.api_key_env:
            key = os.environ.get(self.api_key_env)
            if not key:
                return AdapterResponse(error=f"missing API key: environment variable {self.api_key_env} is not set")
            headers["Authorization"] = f"Bearer {key}"
        body = {
            "model": self.model,
            "messages": self._render(history),
            "tools": self._tools(),
            "tool_choice": "auto",
            "max_tokens": self.max_tokens,
        }
        try:
            status, payload = _post_with_backoff(self.transport, f"{self.base_url}/chat/completions", headers, body)
        except Exception as exc:
            return AdapterResponse(error=f"provider request failed: {exc}")
        if status == 429:
            return AdapterResponse(error="rate_limited: provider still 429 after backoff")
        if status >= 400:
            return AdapterResponse(error=_error_message(payload, status))
        try:
            message = payload["choices"][0]["message"]
        except (KeyError, IndexError, TypeError):
            return AdapterResponse(error=f"unexpected provider response: {json.dumps(payload)[:300]}")
        calls = []
        for raw_call in message.get("tool_calls") or []:
            function = raw_call.get("function", {})
            raw_args = function.get("arguments", "{}")
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
            except json.JSONDecodeError:
                args = {"_malformed_arguments": raw_args}
            calls.append({"name": function.get("name", ""), "args": args})
        usage = payload.get("usage", {})
        return AdapterResponse(
            text=str(message.get("content") or ""),
            tool_calls=calls,
            usage={
                "input_tokens": int(usage.get("prompt_tokens", 0)),
                "output_tokens": int(usage.get("completion_tokens", 0)),
            },
        )


class AnthropicAdapter:
    name = "anthropic"

    def __init__(
        self,
        model: str,
        *,
        model_spec: str | None = None,
        api_key_env: str = "ANTHROPIC_API_KEY",
        context_window: int = 200000,
        transport: Transport | None = None,
        max_tokens: int = 4096,
    ):
        self.model = model
        self.model_spec = model_spec or f"anthropic/{model}"
        self.api_key_env = api_key_env
        self.context_window = context_window
        self.transport = transport or urllib_transport
        self.max_tokens = max_tokens

    def price_per_mtok(self) -> tuple[float, float] | None:
        return price_for(self.model_spec)

    def count_tokens(self, messages: list[dict[str, Any]]) -> int:
        return len(json.dumps(messages, default=str)) // 4

    def _render(self, history: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
        system, rest = _split_history(history)
        raw: list[dict[str, Any]] = []
        counter = 0
        for entry in rest:
            role = entry.get("role")
            if role == "user":
                raw.append({"role": "user", "content": [{"type": "text", "text": str(entry.get("content", ""))}]})
            elif role == "assistant" and "tool_call" in entry:
                counter += 1
                call = entry["tool_call"]
                raw.append(
                    {
                        "role": "assistant",
                        "content": [
                            {"type": "tool_use", "id": f"toolu_{counter}", "name": call["name"], "input": call.get("args", {})}
                        ],
                    }
                )
            elif role == "assistant":
                raw.append({"role": "assistant", "content": [{"type": "text", "text": str(entry.get("content", ""))}]})
            elif role == "tool":
                raw.append(
                    {
                        "role": "user",
                        "content": [
                            {"type": "tool_result", "tool_use_id": f"toolu_{counter}", "content": str(entry.get("content", ""))}
                        ],
                    }
                )
        merged: list[dict[str, Any]] = []
        for message in raw:
            if merged and merged[-1]["role"] == message["role"]:
                merged[-1]["content"].extend(message["content"])
            else:
                merged.append({"role": message["role"], "content": list(message["content"])})
        if merged and merged[0]["role"] == "assistant":
            merged.insert(0, {"role": "user", "content": [{"type": "text", "text": "Begin."}]})
        return system, merged

    def complete(self, history: list[dict[str, Any]], tools: dict[str, Any]) -> AdapterResponse:
        key = os.environ.get(self.api_key_env)
        if not key:
            return AdapterResponse(error=f"missing API key: environment variable {self.api_key_env} is not set")
        system, messages = self._render(history)
        body = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system,
            "messages": messages,
            "tools": [
                {"name": d["name"], "description": d["description"], "input_schema": d["parameters"]}
                for d in tool_definitions()
            ],
        }
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
        try:
            status, payload = _post_with_backoff(self.transport, "https://api.anthropic.com/v1/messages", headers, body)
        except Exception as exc:
            return AdapterResponse(error=f"provider request failed: {exc}")
        if status == 429:
            return AdapterResponse(error="rate_limited: provider still 429 after backoff")
        if status >= 400:
            return AdapterResponse(error=_error_message(payload, status))
        text_parts: list[str] = []
        calls: list[dict[str, Any]] = []
        for block in payload.get("content", []):
            if block.get("type") == "text":
                text_parts.append(str(block.get("text", "")))
            elif block.get("type") == "tool_use":
                calls.append({"name": str(block.get("name", "")), "args": dict(block.get("input", {}))})
        usage = payload.get("usage", {})
        return AdapterResponse(
            text="".join(text_parts),
            tool_calls=calls,
            refusal=payload.get("stop_reason") == "refusal",
            usage={
                "input_tokens": int(usage.get("input_tokens", 0)),
                "output_tokens": int(usage.get("output_tokens", 0)),
            },
        )


class GoogleAIAdapter:
    name = "google"

    def __init__(
        self,
        model: str,
        *,
        model_spec: str | None = None,
        api_key_env: str = "GOOGLE_API_KEY",
        context_window: int = 128000,
        transport: Transport | None = None,
    ):
        self.model = model
        self.model_spec = model_spec or f"google/{model}"
        self.api_key_env = api_key_env
        self.context_window = context_window
        self.transport = transport or urllib_transport

    def price_per_mtok(self) -> tuple[float, float] | None:
        return price_for(self.model_spec)

    def count_tokens(self, messages: list[dict[str, Any]]) -> int:
        return len(json.dumps(messages, default=str)) // 4

    def _render(self, history: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
        system, rest = _split_history(history)
        contents: list[dict[str, Any]] = []
        for entry in rest:
            role = entry.get("role")
            if role == "user":
                contents.append({"role": "user", "parts": [{"text": str(entry.get("content", ""))}]})
            elif role == "assistant" and "tool_call" in entry:
                call = entry["tool_call"]
                contents.append({"role": "model", "parts": [{"functionCall": {"name": call["name"], "args": call.get("args", {})}}]})
            elif role == "assistant":
                contents.append({"role": "model", "parts": [{"text": str(entry.get("content", ""))}]})
            elif role == "tool":
                raw = str(entry.get("content", ""))
                try:
                    response_value: Any = json.loads(raw)
                except json.JSONDecodeError:
                    response_value = {"result": raw}
                contents.append(
                    {"role": "user", "parts": [{"functionResponse": {"name": str(entry.get("name", "tool")), "response": response_value}}]}
                )
        return system, contents

    def complete(self, history: list[dict[str, Any]], tools: dict[str, Any]) -> AdapterResponse:
        key = os.environ.get(self.api_key_env)
        if not key:
            return AdapterResponse(error=f"missing API key: environment variable {self.api_key_env} is not set")
        system, contents = self._render(history)
        body: dict[str, Any] = {
            "contents": contents,
            "tools": [{"functionDeclarations": [
                {"name": d["name"], "description": d["description"], "parameters": d["parameters"]}
                for d in tool_definitions()
            ]}],
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        try:
            status, payload = _post_with_backoff(self.transport, url, {"x-goog-api-key": key}, body)
        except Exception as exc:
            return AdapterResponse(error=f"provider request failed: {exc}")
        if status == 429:
            return AdapterResponse(error="rate_limited: provider still 429 after backoff")
        if status >= 400:
            return AdapterResponse(error=_error_message(payload, status))
        text_parts: list[str] = []
        calls: list[dict[str, Any]] = []
        try:
            parts = payload["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError, TypeError):
            return AdapterResponse(error=f"unexpected provider response: {json.dumps(payload)[:300]}")
        for part in parts:
            if "text" in part:
                text_parts.append(str(part["text"]))
            elif "functionCall" in part:
                call = part["functionCall"]
                calls.append({"name": str(call.get("name", "")), "args": dict(call.get("args", {}))})
        usage = payload.get("usageMetadata", {})
        return AdapterResponse(
            text="".join(text_parts),
            tool_calls=calls,
            usage={
                "input_tokens": int(usage.get("promptTokenCount", 0)),
                "output_tokens": int(usage.get("candidatesTokenCount", 0)),
            },
        )


def make_adapter(model_spec: str, *, base_url: str | None = None, transport: Transport | None = None) -> Any:
    """Build an adapter from a `provider/model` spec (docs/plan/10-runner-flow.md §3)."""
    if "/" in model_spec:
        provider, model = model_spec.split("/", 1)
    else:
        provider, model = "openai_compat", model_spec
    if provider == "anthropic":
        return AnthropicAdapter(model, model_spec=model_spec, transport=transport)
    if provider == "google":
        return GoogleAIAdapter(model, model_spec=model_spec, transport=transport)
    if provider == "openai":
        return OpenAICompatAdapter(model, model_spec=model_spec, transport=transport)
    if provider == "local":
        return OpenAICompatAdapter(
            model,
            model_spec=model_spec,
            base_url=base_url or "http://localhost:8080/v1",
            api_key_env=None,
            transport=transport,
        )
    if provider == "openai_compat":
        resolved_base = base_url or os.environ.get("LONGRUN_BASE_URL")
        if not resolved_base:
            raise ValueError("openai_compat requires --base-url or LONGRUN_BASE_URL")
        return OpenAICompatAdapter(model, model_spec=model_spec, base_url=resolved_base, transport=transport)
    raise ValueError(f"unknown provider in model spec: {model_spec!r} (expected anthropic/, google/, openai/, openai_compat/, local/)")
