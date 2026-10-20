import pytest

from longrun.tools import ToolError, WorkspaceTools


def test_file_roundtrip_and_edit_rules(tmp_path):
    tools = WorkspaceTools(tmp_path)
    tools.execute("file.write", {"path": "a.txt", "content": "hello world"})
    assert tools.execute("file.read", {"path": "a.txt"})["content"] == "hello world"
    tools.execute("file.edit", {"path": "a.txt", "old_text": "world", "new_text": "bench"})
    assert tools.execute("file.read", {"path": "a.txt"})["content"] == "hello bench"
    with pytest.raises(ToolError):
        tools.execute("file.edit", {"path": "a.txt", "old_text": "missing", "new_text": "x"})


def test_edit_rejects_multiple_matches(tmp_path):
    tools = WorkspaceTools(tmp_path)
    tools.execute("file.write", {"path": "a.txt", "content": "x x"})
    with pytest.raises(ToolError):
        tools.execute("file.edit", {"path": "a.txt", "old_text": "x", "new_text": "y"})


def test_path_traversal_rejected(tmp_path):
    tools = WorkspaceTools(tmp_path)
    with pytest.raises(ToolError):
        tools.execute("file.read", {"path": "../outside.txt"})
    with pytest.raises(ToolError):
        tools.execute("file.write", {"path": "/etc/longrun-evil", "content": "x"})


def test_shell_and_python_exec(tmp_path):
    tools = WorkspaceTools(tmp_path)
    result = tools.execute("shell.exec", {"command": "echo hello"})
    assert result["exit_code"] == 0 and "hello" in result["stdout"]
    result = tools.execute("python.exec", {"code": "print(6 * 7)"})
    assert result["exit_code"] == 0 and "42" in result["stdout"]


def test_http_fetch_allowlist_enforced_without_network(tmp_path):
    tools = WorkspaceTools(tmp_path, allowlist=["docs.python.org"])
    with pytest.raises(ToolError):
        tools.execute("http.fetch", {"url": "https://example.com/secret"})


def test_code_nav_on_python_workspace(tmp_path):
    tools = WorkspaceTools(tmp_path)
    tools.execute(
        "file.write",
        {
            "path": "mod.py",
            "content": "def alpha(x):\n    return x + 1\n\n\nclass Beta:\n    def run(self):\n        return alpha(1)\n",
        },
    )
    symbols = tools.execute("code.nav", {"op": "list_symbols", "file": "mod.py"})["symbols"]
    names = {item["name"] for item in symbols}
    assert {"alpha", "Beta", "Beta.run"} <= names
    defs = tools.execute("code.nav", {"op": "find_definition", "symbol": "alpha"})["definitions"]
    assert defs and defs[0]["file"] == "mod.py"
    refs = tools.execute("code.nav", {"op": "find_references", "symbol": "alpha"})["references"]
    assert len(refs) >= 2
    found = tools.execute("code.nav", {"op": "search_symbols", "query": "run"})["symbols"]
    assert any(item["name"] == "Beta.run" for item in found)
