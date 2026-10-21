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
    assert backup_db.DATA_REPO == "darek225/longrun-bench-data"
    assert restore_db.DATA_REPO == backup_db.DATA_REPO
