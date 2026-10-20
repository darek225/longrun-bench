import json

import pytest

from longrun.adapters import AnthropicAdapter, GoogleAIAdapter, OpenAICompatAdapter, make_adapter
from longrun.driver import AdapterResponse

HISTORY = [
    {"role": "system", "content": "You are being evaluated."},
    {"role": "user", "content": "Do the task."},
    {"role": "assistant", "tool_call": {"name": "file.write", "args": {"path": "a.txt", "content": "hi"}}},
    {"role": "tool", "name": "file.write", "content": "{\"path\": \"a.txt\", \"bytes_written\": 2}"},
    {"role": "assistant", "content": "Wrote the file."},
]


def _openai_fake(captured):
    def transport(method, url, headers, body, timeout):
        captured.update({"url": url, "headers": headers, "body": body})
        return 200, {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {"id": "x", "type": "function", "function": {"name": "file.read", "arguments": "{\"path\": \"a.txt\"}"}}
                        ],
                    }
                }
            ],
            "usage": {"prompt_tokens": 100, "completion_tokens": 25},
        }

    return transport


def test_openai_adapter_renders_history_and_parses_calls(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    captured: dict = {}
    adapter = OpenAICompatAdapter("gpt-test", transport=_openai_fake(captured))
    response = adapter.complete(HISTORY, {})
    assert isinstance(response, AdapterResponse)
    assert response.tool_calls == [{"name": "file.read", "args": {"path": "a.txt"}}]
    assert response.usage == {"input_tokens": 100, "output_tokens": 25}
    messages = captured["body"]["messages"]
    assert messages[0]["role"] == "system"
    tool_call_msg = next(m for m in messages if m.get("tool_calls"))
    tool_msg = next(m for m in messages if m["role"] == "tool")
    assert tool_msg["tool_call_id"] == tool_call_msg["tool_calls"][0]["id"]
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["body"]["tools"][0]["type"] == "function"


def test_openai_adapter_missing_key_errors(monkeypatch):
    monkeypatch.delenv("LONGRUN_NOPE_KEY", raising=False)
    adapter = OpenAICompatAdapter("gpt-test", api_key_env="LONGRUN_NOPE_KEY", transport=_openai_fake({}))
    response = adapter.complete(HISTORY, {})
    assert response.error and "LONGRUN_NOPE_KEY" in response.error


def test_openai_adapter_malformed_arguments_become_invalid_args(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def transport(method, url, headers, body, timeout):
        return 200, {
            "choices": [{"message": {"content": "", "tool_calls": [
                {"id": "x", "type": "function", "function": {"name": "file.read", "arguments": "{not json"}}
            ]}}],
            "usage": {},
        }

    adapter = OpenAICompatAdapter("gpt-test", transport=transport)
    response = adapter.complete(HISTORY, {})
    assert "_malformed_arguments" in response.tool_calls[0]["args"]


def test_anthropic_adapter_roundtrip(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    captured: dict = {}

    def transport(method, url, headers, body, timeout):
        captured.update({"url": url, "headers": headers, "body": body})
        return 200, {
            "content": [
                {"type": "text", "text": "Reading it now."},
                {"type": "tool_use", "id": "t1", "name": "file.read", "input": {"path": "a.txt"}},
            ],
            "usage": {"input_tokens": 90, "output_tokens": 12},
        }

    adapter = AnthropicAdapter("claude-test", transport=transport)
    response = adapter.complete(HISTORY, {})
    assert response.text == "Reading it now."
    assert response.tool_calls == [{"name": "file.read", "args": {"path": "a.txt"}}]
    assert response.usage == {"input_tokens": 90, "output_tokens": 12}
    assert captured["body"]["system"] == "You are being evaluated."
    assert captured["headers"]["x-api-key"] == "test-key"
    roles = [m["role"] for m in captured["body"]["messages"]]
    assert roles == ["user", "assistant", "user", "assistant"]  # strict alternation after merging
    tool_result_msg = captured["body"]["messages"][2]
    assert tool_result_msg["content"][0]["type"] == "tool_result"


def test_anthropic_refusal_maps_to_refusal(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    def transport(method, url, headers, body, timeout):
        return 200, {"content": [], "stop_reason": "refusal", "usage": {}}

    adapter = AnthropicAdapter("claude-test", transport=transport)
    assert adapter.complete(HISTORY, {}).refusal is True


def test_google_adapter_parses_function_call(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    captured: dict = {}

    def transport(method, url, headers, body, timeout):
        captured.update({"url": url, "body": body})
        return 200, {
            "candidates": [{"content": {"parts": [{"functionCall": {"name": "file.read", "args": {"path": "a.txt"}}}]}}],
            "usageMetadata": {"promptTokenCount": 50, "candidatesTokenCount": 5},
        }

    adapter = GoogleAIAdapter("gemini-test", transport=transport)
    response = adapter.complete(HISTORY, {})
    assert response.tool_calls == [{"name": "file.read", "args": {"path": "a.txt"}}]
    assert response.usage == {"input_tokens": 50, "output_tokens": 5}
    assert "generativelanguage.googleapis.com" in captured["url"]
    assert captured["body"]["systemInstruction"]["parts"][0]["text"] == "You are being evaluated."


def test_make_adapter_factory():
    assert isinstance(make_adapter("anthropic/claude-x"), AnthropicAdapter)
    assert isinstance(make_adapter("google/gemini-x"), GoogleAIAdapter)
    local = make_adapter("local/llama-x")
    assert isinstance(local, OpenAICompatAdapter)
    assert local.base_url == "http://localhost:8080/v1" and local.api_key_env is None
    compat = make_adapter("openai_compat/model-x", base_url="http://example.test/v1")
    assert compat.base_url == "http://example.test/v1"
    with pytest.raises(ValueError):
        make_adapter("openai_compat/model-x")
    with pytest.raises(ValueError):
        make_adapter("bogus/model-x")


def test_adapter_error_payload_surfaces(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def transport(method, url, headers, body, timeout):
        return 500, {"error": {"message": "server exploded"}}

    adapter = OpenAICompatAdapter("gpt-test", transport=transport)
    response = adapter.complete(HISTORY, {})
    assert response.error and "server exploded" in response.error
