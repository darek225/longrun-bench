import json

from audit_log import AuditLog


def test_append_and_verify(tmp_path):
    log = AuditLog(str(tmp_path / "a.log"))
    log.append("alice", "login")
    log.append("bob", "export", {"rows": 5})
    assert log.verify() is True


def test_tamper_breaks_verification(tmp_path):
    path = tmp_path / "a.log"
    log = AuditLog(str(path))
    log.append("alice", "login")
    log.append("bob", "export")
    lines = path.read_text().splitlines()
    entry = json.loads(lines[0])
    entry["actor"] = "mallory"
    lines[0] = json.dumps(entry)
    path.write_text("\n".join(lines) + "\n")
    assert log.verify() is False


def test_query_filters_by_actor(tmp_path):
    log = AuditLog(str(tmp_path / "a.log"))
    log.append("alice", "login")
    log.append("bob", "export")
    log.append("alice", "logout")
    assert len(log.query("alice")) == 2
    assert len(log.query()) == 3


def test_chain_links_entries(tmp_path):
    log = AuditLog(str(tmp_path / "a.log"))
    h1 = log.append("alice", "login")
    log.append("alice", "logout")
    entries = log.query()
    assert entries[1]["prev"] == h1
