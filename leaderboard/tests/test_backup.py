import gzip
import importlib.util
import shutil
import sqlite3
from pathlib import Path

from leaderboard.store import Store

REPO = Path(__file__).resolve().parents[2]


def _load_script(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), REPO / "scripts" / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


backup_db = _load_script("backup-db.py")
restore_db = _load_script("restore-db.py")


def test_snapshot_round_trip_and_checksum(tmp_path):
    db_path = tmp_path / "board.db"
    store = Store(db_path)
    store.conn.execute(
        "INSERT INTO users (id, email, display_name, password_hash) VALUES ('u1', 'a@example.com', 'A', 'hash')"
    )
    store.conn.commit()
    snap_path = tmp_path / "snap.db"
    counts = backup_db.snapshot(db_path, snap_path)
    assert counts["users"] == 1
    gz_path = tmp_path / "snap.db.gz"
    with snap_path.open("rb") as src, gzip.open(gz_path, "wb") as dst:
        shutil.copyfileobj(src, dst)
    digest = backup_db.sha256_file(gz_path)
    assert restore_db.sha256_file(gz_path) == digest
    # The restored copy is a working database with the row in it.
    out_path = tmp_path / "restored.db"
    with gzip.open(gz_path, "rb") as src, out_path.open("wb") as dst:
        shutil.copyfileobj(src, dst)
    conn = sqlite3.connect(out_path)
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert conn.execute("SELECT email FROM users").fetchone()[0] == "a@example.com"
    conn.close()
    # A tampered archive fails the checksum gate restore relies on.
    tampered = tmp_path / "tampered.db.gz"
    data = bytearray(gz_path.read_bytes())
    data[-5] ^= 0xFF
    tampered.write_bytes(bytes(data))
    assert restore_db.sha256_file(tampered) != digest
    assert backup_db.BUCKET == "longrun-bench-backups"
    assert restore_db.BUCKET == backup_db.BUCKET


def test_upload_to_bucket_sends_archive_and_manifest(tmp_path):
    gz_path = tmp_path / "leaderboard-20261107-010203.db.gz"
    gz_path.write_bytes(b"archive-bytes")
    manifest_path = tmp_path / "leaderboard-20261107-010203.manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")
    calls = []

    class FakeClient:
        def put_object(self, namespace, bucket, name, body):
            calls.append((namespace, bucket, name, body))

    backup_db.upload_to_bucket(FakeClient(), "ns1", gz_path, manifest_path)
    assert calls == [
        ("ns1", "longrun-bench-backups", gz_path.name, b"archive-bytes"),
        ("ns1", "longrun-bench-backups", manifest_path.name, b"{}"),
    ]


def test_newest_archive_name_picks_max_stamp():
    names = [
        "leaderboard-20261022-002507.db.gz",
        "leaderboard-20261107-010203.db.gz",
        "leaderboard-20261107-010203.manifest.json",
        "unrelated.txt",
    ]
    assert restore_db.newest_archive_name(names) == "leaderboard-20261107-010203.db.gz"
    assert restore_db.newest_archive_name([]) is None
