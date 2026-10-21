#!/usr/bin/env python3
"""Back up the leaderboard database to the private data repo.

Same pattern as the Dowser backups (Darek, 2026-10-20): the snapshot is
a GitHub RELEASE ASSET on the private repo darek225/longrun-bench-data
(2 GB/file cap, no git size limits), with a manifest recording sha256,
size, and per-table row counts (counts only: the manifest never carries
account emails or hashes). Restore with scripts/restore-db.py, which
verifies the checksum before touching anything.

The snapshot uses SQLite's backup API, so it is consistent even while
the leaderboard server is running. Usage:

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
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

DATA_REPO = "darek225/longrun-bench-data"
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Back up the leaderboard DB to the private data repo")
    parser.add_argument("--db", default="leaderboard.db", help="path to the live SQLite db")
    parser.add_argument("--local-only", action="store_true", help="write the snapshot + manifest, skip the GitHub upload")
    parser.add_argument("--repo", default=DATA_REPO)
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
    tag = f"backup-{stamp[:8]}"
    notes = (
        f"Leaderboard DB backup {stamp}\n\n"
        f"file: {manifest['file']}\nsha256: {manifest['sha256']}\nbytes: {manifest['bytes']}\n"
        f"rows: {json.dumps(counts, sort_keys=True)}\n"
    )
    create = subprocess.run(
        ["gh", "release", "create", tag, "--repo", args.repo, "--title", f"DB backup {stamp[:8]}", "--notes", notes],
        capture_output=True, text=True,
    )
    if create.returncode != 0 and "already exists" not in (create.stderr + create.stdout):
        print(f"release create failed: {create.stderr.strip()[:300]}", file=sys.stderr)
        return 1
    upload = subprocess.run(
        ["gh", "release", "upload", tag, str(gz_path), str(manifest_path), "--repo", args.repo, "--clobber"],
        capture_output=True, text=True,
    )
    if upload.returncode != 0:
        print(f"upload failed: {upload.stderr.strip()[:300]}", file=sys.stderr)
        return 1
    print(f"uploaded to {args.repo} release {tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
