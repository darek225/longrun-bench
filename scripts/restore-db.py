#!/usr/bin/env python3
"""Restore a leaderboard DB backup from OCI Object Storage.

Downloads the archive + manifest from the private bucket
`longrun-bench-backups`, verifies the sha256 BEFORE writing anything,
then gunzips and integrity-checks the result. Refuses to overwrite an
existing database without --force.

    python3 scripts/restore-db.py [--name leaderboard-YYYYMMDD-HHMMSS.db.gz] [--out leaderboard.db] [--force]

Without --name, restores the newest backup in the bucket. Auth is the
operator's OCI config (~/.oci/config, default profile): restores run
from an operator machine, never from the leaderboard instance itself.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

BUCKET = "longrun-bench-backups"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def newest_archive_name(object_names: list[str]) -> str | None:
    """Archive names embed a UTC stamp, so the max name is the newest."""
    archives = [n for n in object_names if n.startswith("leaderboard-") and n.endswith(".db.gz")]
    return max(archives) if archives else None


def operator_client():
    import oci

    config = oci.config.from_file()
    return oci.object_storage.ObjectStorageClient(config)


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore a leaderboard DB backup (checksum-verified)")
    parser.add_argument("--name", default=None, help="archive object name; default: newest in the bucket")
    parser.add_argument("--out", default="leaderboard.db")
    parser.add_argument("--force", action="store_true", help="overwrite --out if it exists")
    args = parser.parse_args()

    out_path = Path(args.out)
    if out_path.exists() and not args.force:
        print(f"{out_path} exists; pass --force to overwrite", file=sys.stderr)
        return 1
    client = operator_client()
    namespace = client.get_namespace().data
    name = args.name
    if name is None:
        listing = client.list_objects(namespace, BUCKET)
        name = newest_archive_name([obj.name for obj in listing.data.objects])
        if name is None:
            print("no backups found in the bucket", file=sys.stderr)
            return 1
    manifest_name = name[: -len(".db.gz")] + ".manifest.json"
    print(f"restoring from OCI bucket {BUCKET}: {name}")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for object_name in (name, manifest_name):
            response = client.get_object(namespace, BUCKET, object_name)
            (tmp_dir / object_name).write_bytes(response.data.content)
        manifest = json.loads((tmp_dir / manifest_name).read_text(encoding="utf-8"))
        archive = tmp_dir / manifest["file"]
        if not archive.exists():
            archive = tmp_dir / name
        actual = sha256_file(archive)
        if actual != manifest["sha256"]:
            print(f"CHECKSUM MISMATCH: manifest {manifest['sha256']}, downloaded {actual}. Refusing to restore.", file=sys.stderr)
            return 1
        raw_path = tmp_dir / "restored.db"
        with gzip.open(archive, "rb") as src, raw_path.open("wb") as dst:
            shutil.copyfileobj(src, dst)
        conn = sqlite3.connect(raw_path)
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        counts = {
            row[0]: conn.execute(f"SELECT COUNT(*) FROM {row[0]}").fetchone()[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
        }
        conn.close()
        if integrity != "ok":
            print(f"restored db failed integrity check: {integrity}", file=sys.stderr)
            return 1
        shutil.copyfile(raw_path, out_path)
    print(f"restored {out_path} (sha256 verified, integrity ok, rows: {counts})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
