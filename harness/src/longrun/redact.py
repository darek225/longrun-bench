from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

# Key-shaped strings that must never reach a transcript or an upload,
# per docs/plan/10-runner-flow.md §2. Redaction is declared in the
# submission manifest; the raw key never enters these code paths at all
# (adapters read it from the environment at call time only).
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("private_key_block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----")),
    ("openai_style_key", re.compile(r"sk-[A-Za-z0-9_-]{16,}")),
    ("xai_key", re.compile(r"xai-[A-Za-z0-9_-]{16,}")),
    ("google_api_key", re.compile(r"AIza[A-Za-z0-9_-]{20,}")),
    ("github_token", re.compile(r"(?:ghp|gho|github_pat)_[A-Za-z0-9_]{20,}")),
    ("aws_access_key", re.compile(r"AKIA[A-Z0-9]{16}")),
    ("bearer_token", re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]{16,}", re.IGNORECASE)),
    ("anthropic_key", re.compile(r"sk-ant-[A-Za-z0-9_-]{16,}")),
]

REDACTED = "[REDACTED]"


def redact_text(text: str) -> tuple[str, int]:
    count = 0
    out = text
    for _, pattern in _PATTERNS:
        out, n = pattern.subn(REDACTED, out)
        count += n
    return out, count


def redact_value(value: Any) -> tuple[Any, int]:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        total = 0
        items = []
        for item in value:
            new_item, n = redact_value(item)
            items.append(new_item)
            total += n
        return items, total
    if isinstance(value, dict):
        total = 0
        out = {}
        for key, item in value.items():
            new_item, n = redact_value(item)
            out[key] = new_item
            total += n
        return out, total
    return value, 0


def redact_transcript_file(source: str | Path, dest: str | Path) -> dict[str, Any]:
    """Write a redacted copy of a JSONL transcript; returns the redaction manifest."""
    source_path = Path(source)
    dest_path = Path(dest)
    total = 0
    lines_out: list[str] = []
    for line in source_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        redacted, n = redact_value(event)
        total += n
        lines_out.append(json.dumps(redacted, sort_keys=True, default=str))
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_text("\n".join(lines_out) + "\n", encoding="utf-8")
    return {"source": str(source_path), "dest": str(dest_path), "redactions": total, "patterns": [name for name, _ in _PATTERNS]}
