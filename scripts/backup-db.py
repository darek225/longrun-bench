#!/usr/bin/env python3
"""Back up the leaderboard database to OCI Object Storage.

The snapshot (SQLite backup API: consistent while the server runs) is
gzipped with a manifest recording sha256, size, and per-table row
counts (counts only: the manifest never carries account emails or
hashes), then uploaded to the private bucket `longrun-bench-backups`
in Darek's Oracle tenancy. Restore with scripts/restore-db.py, which
verifies the checksum before touching anything.

Auth is the instance's own identity (instance principal): the backup
service runs on the leaderboard instance, whose dynamic group may
`manage objects` in that one bucket (manage, not use: in OCI,
creating a NEW object requires OBJECT_CREATE, which only the manage
verb grants; use covers read + overwrite only). No portable
credential exists, so nothing can expire or leak. (History: backups
originally went to
GitHub release assets via the gh CLI; that pipeline silently died
when an instance was provisioned without gh or a credential, and a
token would only have added an expiry cliff of the same kind.)

Usage:

    python3 scripts/backup-db.py [--db leaderboard.db] [--local-only]

Local artifacts land in backups/ (gitignored: a board DB contains
password hashes and must never be committed to the code repo).
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

BUCKET = "longrun-bench-backups"
REPO_ROOT = Path(__file__).resolve().parents[1]
BACKUP_DIR = REPO_ROOT / "backups"


def snapshot(db_path: Path, out_path: Path) -> dict:
    """Consistent snapshot + integrity check + row counts."""
    source = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    dest = sqlite3.connect(out_path)
    try:
        source.backup(dest)
    finally:
        dest.close()
        source.close()
    check = sqlite3.connect(out_path)
    try:
        integrity = check.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise SystemExit(f"snapshot failed integrity check: {integrity}")
        tables = [
            row[0]
            for row in check.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        ]
        counts = {t: check.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}
    finally:
        check.close()
    return counts


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def upload_to_bucket(client, namespace: str, gz_path: Path, manifest_path: Path) -> None:
    """Upload archive + manifest under their file names. `client` is an
    oci.object_storage.ObjectStorageClient (real or a test double)."""
    for path in (gz_path, manifest_path):
        client.put_object(namespace, BUCKET, path.name, path.read_bytes())


def instance_principal_client():
    """Object Storage client authenticated as this instance itself."""
    import oci
    from oci.auth.signers import InstancePrincipalsSecurityTokenSigner

    signer = InstancePrincipalsSecurityTokenSigner()
    return oci.object_storage.ObjectStorageClient(config={}, signer=signer)


def main() -> int:
    parser = argparse.ArgumentParser(description="Back up the leaderboard DB to OCI Object Storage")
    parser.add_argument("--db", default="leaderboard.db", help="path to the live SQLite db")
    parser.add_argument("--local-only", action="store_true", help="write the snapshot + manifest, skip the upload")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"no database at {db_path}", file=sys.stderr)
        return 1
    BACKUP_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    raw_path = BACKUP_DIR / f"leaderboard-{stamp}.db"
    counts = snapshot(db_path, raw_path)
    gz_path = Path(str(raw_path) + ".gz")
    with raw_path.open("rb") as src, gzip.open(gz_path, "wb", compresslevel=9) as dst:
        shutil.copyfileobj(src, dst)
    raw_path.unlink()
    manifest = {
        "file": gz_path.name,
        "sha256": sha256_file(gz_path),
        "bytes": gz_path.stat().st_size,
        "source_db": str(db_path),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "row_counts": counts,
    }
    manifest_path = BACKUP_DIR / f"leaderboard-{stamp}.manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(f"snapshot: {gz_path} ({manifest['bytes']} bytes, sha256 {manifest['sha256'][:16]}...)")
    print(f"rows: {counts}")

    if args.local_only:
        print("local only; skipping upload")
        return 0
    client = instance_principal_client()
    namespace = client.get_namespace().data
    upload_to_bucket(client, namespace, gz_path, manifest_path)
    print(f"uploaded to OCI bucket {BUCKET}: {gz_path.name}, {manifest_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
