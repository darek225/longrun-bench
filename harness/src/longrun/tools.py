from __future__ import annotations

import ast
import html
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


class ToolError(ValueError):
    pass


def _truncate(text: str, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True


class WorkspaceTools:
    def __init__(self, workspace: str | Path, *, allowlist: list[str] | None = None):
        self.workspace = Path(workspace).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.allowlist = [item.lower() for item in (allowlist or [])]

    def execute(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        handlers = {
            "shell.exec": self._shell_exec,
            "file.read": self._file_read,
            "file.write": self._file_write,
            "file.edit": self._file_edit,
            "python.exec": self._python_exec,
            "http.fetch": self._http_fetch,
            "browser.task": self._browser_task,
            "code.nav": self._code_nav,
            "deliver": self._deliver_passthrough,
        }
        if name not in handlers:
            raise ToolError(f"unknown tool: {name}")
        return handlers[name](args)

    def resolve_path(self, raw: str) -> Path:
        path = Path(raw)
        if not path.is_absolute():
            path = self.workspace / path
        resolved = path.resolve()
        if resolved != self.workspace and self.workspace not in resolved.parents:
            raise ToolError(f"path escapes workspace: {raw}")
        return resolved

    def _shell_exec(self, args: dict[str, Any]) -> dict[str, Any]:
        command = str(args["command"])
        timeout = int(args.get("timeout", 120))
        try:
            completed = subprocess.run(
                command,
                cwd=self.workspace,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            return {
                "exit_code": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
                "timed_out": False,
            }
        except subprocess.TimeoutExpired as exc:
            return {
                "exit_code": None,
                "stdout": exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or ""),
                "stderr": exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or ""),
                "timed_out": True,
            }

    def _file_read(self, args: dict[str, Any]) -> dict[str, Any]:
        path = self.resolve_path(str(args["path"]))
        if not path.exists():
            raise ToolError(f"file does not exist: {args['path']}")
        if path.is_dir():
            raise ToolError(f"path is a directory: {args['path']}")
        max_chars = int(args.get("max_chars", 50000))
        content, truncated = _truncate(path.read_text(encoding="utf-8", errors="replace"), max_chars)
        return {"path": str(args["path"]), "content": content, "truncated": truncated}

    def _file_write(self, args: dict[str, Any]) -> dict[str, Any]:
        path = self.resolve_path(str(args["path"]))
        path.parent.mkdir(parents=True, exist_ok=True)
        content = str(args.get("content", ""))
        path.write_text(content, encoding="utf-8")
        return {"path": str(args["path"]), "bytes_written": len(content.encode("utf-8"))}

    def _file_edit(self, args: dict[str, Any]) -> dict[str, Any]:
        path = self.resolve_path(str(args["path"]))
        if not path.exists():
            raise ToolError(f"file does not exist: {args['path']}")
        old_text = str(args["old_text"])
        new_text = str(args["new_text"])
        text = path.read_text(encoding="utf-8")
        count = text.count(old_text)
        if count == 0:
            raise ToolError("old_text not found")
        if count > 1:
            raise ToolError(f"old_text found {count} times; file.edit requires exactly one match")
        path.write_text(text.replace(old_text, new_text, 1), encoding="utf-8")
        return {"path": str(args["path"]), "edited": True}

    def _python_exec(self, args: dict[str, Any]) -> dict[str, Any]:
        code = str(args["code"])
        timeout = int(args.get("timeout", 120))
        try:
            completed = subprocess.run(
                [sys.executable, "-c", code],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            return {
                "exit_code": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
                "exception": None if completed.returncode == 0 else completed.stderr.strip().splitlines()[-1] if completed.stderr.strip() else "python exited non-zero",
                "timed_out": False,
            }
        except subprocess.TimeoutExpired as exc:
            return {
                "exit_code": None,
                "stdout": exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or ""),
                "stderr": exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or ""),
                "exception": "timeout",
                "timed_out": True,
            }

    def _host_allowed(self, url: str) -> bool:
        host = (urlparse(url).hostname or "").lower()
        if not host:
            return False
        return any(host == allowed or host.endswith("." + allowed) for allowed in self.allowlist)

    def _http_fetch(self, args: dict[str, Any]) -> dict[str, Any]:
        url = str(args["url"])
        max_chars = int(args.get("max_chars", 50000))
        if not self._host_allowed(url):
            raise ToolError(f"host is not in the task allowlist: {urlparse(url).hostname}")
        request = urllib.request.Request(url, headers={"User-Agent": "LongRunBench/0.1"})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                body = response.read().decode("utf-8", errors="replace")
                text = _html_to_text(body)
                text, truncated = _truncate(text, max_chars)
                return {"status": response.status, "text_markdown": text, "final_url": response.geturl(), "truncated": truncated}
        except urllib.error.HTTPError as exc:
            return {"status": exc.code, "text_markdown": "", "final_url": url, "error": str(exc)}

    def _browser_task(self, args: dict[str, Any]) -> dict[str, Any]:
        return {
            "error": "browser.task is not implemented in the local Phase 2 harness yet",
            "goal": str(args.get("goal", "")),
            "observations": [],
            "extracted": {},
        }

    def _deliver_passthrough(self, args: dict[str, Any]) -> dict[str, Any]:
        return {"deliver": args}

    def _python_files(self, file_arg: str | None = None) -> list[Path]:
        if file_arg:
            path = self.resolve_path(file_arg)
            return [path] if path.exists() else []
        return sorted(self.workspace.rglob("*.py"))

    def _symbols_in_file(self, path: Path) -> list[dict[str, Any]]:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            return []
        symbols: list[dict[str, Any]] = []

        def visit(node: ast.AST, prefix: str = "") -> None:
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    kind = "class" if isinstance(child, ast.ClassDef) else "function"
                    name = f"{prefix}{child.name}" if prefix else child.name
                    symbols.append(
                        {
                            "name": name,
                            "kind": kind,
                            "file": str(path.relative_to(self.workspace)),
                            "line": getattr(child, "lineno", 0),
                        }
                    )
                    visit(child, prefix=f"{name}.")
                else:
                    visit(child, prefix)

        visit(tree)
        return symbols

    def _code_nav(self, args: dict[str, Any]) -> dict[str, Any]:
        op = str(args["op"])
        file_arg = str(args["file"]) if args.get("file") else None
        if op == "list_symbols":
            if not file_arg:
                raise ToolError("code.nav list_symbols requires file")
            path = self.resolve_path(file_arg)
            return {"symbols": self._symbols_in_file(path)}
        if op == "search_symbols":
            query = str(args["query"]).lower()
            matches = []
            for path in self._python_files():
                for symbol in self._symbols_in_file(path):
                    if query in symbol["name"].lower():
                        matches.append(symbol)
            return {"symbols": matches}
        if op == "find_definition":
            symbol = str(args["symbol"])
            matches = []
            for path in self._python_files(file_arg):
                for item in self._symbols_in_file(path):
                    if item["name"] == symbol or item["name"].split(".")[-1] == symbol:
                        matches.append(item)
            return {"definitions": matches}
        if op == "find_references":
            symbol = str(args["symbol"])
            references = []
            pattern = re.compile(rf"\b{re.escape(symbol)}\b")
            for path in self._python_files(file_arg):
                for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
                    if pattern.search(line):
                        references.append(
                            {
                                "file": str(path.relative_to(self.workspace)),
                                "line": line_no,
                                "text": line.strip()[:240],
                            }
                        )
            return {"references": references}
        raise ToolError(f"unknown code.nav op: {op}")


def _html_to_text(body: str) -> str:
    without_scripts = re.sub(r"<(script|style)[\s\S]*?</\1>", " ", body, flags=re.IGNORECASE)
    with_breaks = re.sub(r"<(br|/p|/div|/li|/h[1-6])\b[^>]*>", "\n", without_scripts, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", with_breaks)
    text = html.unescape(text)
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def summarize_result(name: str, result: dict[str, Any]) -> dict[str, Any]:
    if "error" in result and result.get("error"):
        return {"error": str(result["error"])[:240]}
    if name in {"shell.exec", "python.exec"}:
        stdout = str(result.get("stdout", ""))
        stderr = str(result.get("stderr", ""))
        return {"exit_code": result.get("exit_code"), "chars": len(stdout) + len(stderr), "timed_out": bool(result.get("timed_out"))}
    if name == "file.read":
        return {"chars": len(str(result.get("content", ""))), "truncated": bool(result.get("truncated"))}
    if name == "file.write":
        return {"bytes_written": result.get("bytes_written", 0)}
    if name == "file.edit":
        return {"edited": bool(result.get("edited"))}
    if name == "http.fetch":
        return {"status": result.get("status"), "chars": len(str(result.get("text_markdown", "")))}
    if name == "code.nav":
        for key in ("symbols", "definitions", "references"):
            if key in result:
                return {key: len(result[key])}
    return {"keys": sorted(result.keys()), "chars": len(json.dumps(result, default=str))}
