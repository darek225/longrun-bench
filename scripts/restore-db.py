#!/usr/bin/env python3
"""Restore a leaderboard DB backup from the private data repo.

Downloads the release asset + manifest, verifies the sha256 BEFORE
writing anything, then gunzips and integrity-checks the result.
Refuses to overwrite an existing database without --force.

    python3 scripts/restore-db.py [--tag backup-YYYYMMDD] [--out leaderboard.db] [--force]

Without --tag, uses the newest backup release on darek225/longrun-bench-data.
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
import tempfile
from pathlib import Path

DATA_REPO = "darek225/longrun-bench-data"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def gh_json(args: list[str]) -> object:
    result = subprocess.run(["gh", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"gh failed: {result.stderr.strip()[:300]}")
    return json.loads(result.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore a leaderboard DB backup (checksum-verified)")
    parser.add_argument("--tag", default=None, help="release tag; default: newest backup-* release")
    parser.add_argument("--out", default="leaderboard.db")
    parser.add_argument("--repo", default=DATA_REPO)
    parser.add_argument("--force", action="store_true", help="overwrite --out if it exists")
    args = parser.parse_args()

    out_path = Path(args.out)
    if out_path.exists() and not args.force:
        print(f"{out_path} exists; pass --force to overwrite", file=sys.stderr)
        return 1
    tag = args.tag
    if tag is None:
        releases = gh_json(["release", "list", "--repo", args.repo, "--json", "tagName,createdAt"])
        tags = sorted(
            (r for r in releases if str(r["tagName"]).startswith("backup-")),
            key=lambda r: r["createdAt"],
        )
        if not tags:
            print("no backup releases found", file=sys.stderr)
            return 1
        tag = str(tags[-1]["tagName"])
    print(f"restoring from {args.repo} release {tag}")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        download = subprocess.run(
            ["gh", "release", "download", tag, "--repo", args.repo, "--dir", str(tmp_dir)],
            capture_output=True, text=True,
        )
        if download.returncode != 0:
            print(f"download failed: {download.stderr.strip()[:300]}", file=sys.stderr)
            return 1
        manifests = sorted(tmp_dir.glob("*.manifest.json"))
        archives = sorted(tmp_dir.glob("*.db.gz"))
        if not manifests or not archives:
            print("release is missing its manifest or db archive", file=sys.stderr)
            return 1
        manifest = json.loads(manifests[-1].read_text(encoding="utf-8"))
        archive = tmp_dir / manifest["file"]
        if not archive.exists():
            archive = archives[-1]
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
