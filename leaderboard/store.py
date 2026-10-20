from __future__ import annotations

import json
import math
import sqlite3
import statistics
import uuid
from pathlib import Path
from typing import Any

LEVEL_NAMES = {1: "sprint", 2: "marathon", 3: "ultra"}
TIER_RANK = {"checks": 0, "graded": 1, "verified": 2}

SCHEMA = """
CREATE TABLE IF NOT EXISTS scores (
  id TEXT PRIMARY KEY,
  agent_name TEXT NOT NULL,
  model TEXT NOT NULL,
  profile TEXT NOT NULL CHECK (profile IN ('bare','standard','native')),
  level TEXT NOT NULL CHECK (level IN ('sprint','marathon','ultra')),
  task_set TEXT NOT NULL,
  harness_hash TEXT NOT NULL,
  board TEXT NOT NULL CHECK (board IN ('official','community')),
  tier TEXT NOT NULL DEFAULT 'checks',
  status TEXT NOT NULL DEFAULT 'provisional',
  mean_score REAL NOT NULL,
  ci_low REAL NOT NULL,
  ci_high REAL NOT NULL,
  median_score REAL NOT NULL,
  n_tasks INT NOT NULL,
  n_runs INT NOT NULL,
  gen_gap REAL,
  gap_flag INT DEFAULT 0,
  provisional INT DEFAULT 0,
  created_at TEXT DEFAULT (datetime('now')),
  supersedes TEXT REFERENCES scores(id)
);
CREATE TABLE IF NOT EXISTS task_scores (
  score_id TEXT REFERENCES scores(id),
  task_id TEXT NOT NULL,
  mean_score REAL NOT NULL,
  n_runs INT NOT NULL DEFAULT 1,
  PRIMARY KEY (score_id, task_id)
);
CREATE TABLE IF NOT EXISTS run_manifests (
  id TEXT PRIMARY KEY,
  score_id TEXT REFERENCES scores(id),
  run_id TEXT NOT NULL,
  task_id TEXT NOT NULL,
  seed INT NOT NULL,
  transcript_sha256 TEXT NOT NULL,
  claimed_total REAL NOT NULL,
  replayed_total REAL NOT NULL,
  tier TEXT NOT NULL DEFAULT 'checks',
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS disputes (
  id TEXT PRIMARY KEY,
  score_id TEXT REFERENCES scores(id),
  status TEXT CHECK (status IN ('open','resolved','frivolous')),
  reason TEXT,
  resolution TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS verifications (
  id TEXT PRIMARY KEY,
  score_id TEXT REFERENCES scores(id),
  verifier TEXT NOT NULL,
  org TEXT,
  run_id TEXT NOT NULL,
  task_id TEXT NOT NULL,
  seed INT NOT NULL,
  reproduced_total REAL NOT NULL,
  within_ci INT NOT NULL,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS reputation (
  id TEXT PRIMARY KEY,
  subject TEXT NOT NULL,
  points INT NOT NULL,
  reason TEXT NOT NULL,
  created_at TEXT DEFAULT (datetime('now'))
);
"""


def aggregate(task_runs: dict[str, list[float]]) -> dict[str, Any]:
    """Aggregate per-task run totals into a board row (docs/plan/04 §1).

    The board ranks configurations by the mean of per-task mean scores, so a
    configuration cannot farm one easy task with many runs.
    """
    task_means = {task: sum(totals) / len(totals) for task, totals in task_runs.items()}
    means = list(task_means.values())
    n_tasks = len(means)
    n_runs = sum(len(totals) for totals in task_runs.values())
    mean = sum(means) / n_tasks if n_tasks else 0.0
    if n_tasks >= 2:
        sd = statistics.stdev(means)
        half = 1.96 * sd / math.sqrt(n_tasks)
    else:
        half = 0.0
    return {
        "task_means": task_means,
        "mean_score": round(mean, 4),
        "ci_low": round(mean - half, 4),
        "ci_high": round(mean + half, 4),
        "median_score": round(statistics.median(means), 4) if means else 0.0,
        "n_tasks": n_tasks,
        "n_runs": n_runs,
        "provisional": any(len(totals) < 3 for totals in task_runs.values()),
    }


class Store:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # -- scores ------------------------------------------------------------
    def insert_score_group(
        self,
        *,
        agent_name: str,
        model: str,
        profile: str,
        level: str,
        task_set: str,
        harness_hash: str,
        board: str,
        tier: str,
        task_runs: dict[str, list[float]],
        manifests: list[dict[str, Any]],
        gen_gap: float | None = None,
    ) -> str:
        agg = aggregate(task_runs)
        score_id = str(uuid.uuid4())
        previous = self.conn.execute(
            "SELECT id FROM scores WHERE agent_name=? AND model=? AND profile=? AND level=? AND task_set=? AND board=? "
            "AND id NOT IN (SELECT supersedes FROM scores WHERE supersedes IS NOT NULL) ORDER BY created_at DESC LIMIT 1",
            (agent_name, model, profile, level, task_set, board),
        ).fetchone()
        self.conn.execute(
            "INSERT INTO scores (id, agent_name, model, profile, level, task_set, harness_hash, board, tier, status, "
            "mean_score, ci_low, ci_high, median_score, n_tasks, n_runs, gen_gap, gap_flag, provisional, supersedes) "
            "VALUES (?,?,?,?,?,?,?,?,?,'provisional',?,?,?,?,?,?,?, ?,?,?)",
            (
                score_id, agent_name, model, profile, level, task_set, harness_hash, board, tier,
                agg["mean_score"], agg["ci_low"], agg["ci_high"], agg["median_score"], agg["n_tasks"], agg["n_runs"],
                gen_gap, 1 if (gen_gap is not None and abs(gen_gap) >= 10) else 0,
                1 if agg["provisional"] else 0,
                previous["id"] if previous else None,
            ),
        )
        for task_id, mean_score in agg["task_means"].items():
            self.conn.execute(
                "INSERT INTO task_scores (score_id, task_id, mean_score, n_runs) VALUES (?,?,?,?)",
                (score_id, task_id, round(mean_score, 4), len(task_runs[task_id])),
            )
        for manifest in manifests:
            self.conn.execute(
                "INSERT INTO run_manifests (id, score_id, run_id, task_id, seed, transcript_sha256, claimed_total, replayed_total, tier) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    str(uuid.uuid4()), score_id, manifest["run_id"], manifest["task_id"], int(manifest["seed"]),
                    manifest["transcript_sha256"], float(manifest["claimed_total"]), float(manifest["replayed_total"]),
                    manifest.get("tier", "checks"),
                ),
            )
        self.conn.commit()
        return score_id

    def latest_scores(self, *, profile: str | None = None, level: str | None = None, board: str | None = None) -> list[dict[str, Any]]:
        query = (
            "SELECT * FROM scores WHERE id NOT IN (SELECT supersedes FROM scores WHERE supersedes IS NOT NULL)"
        )
        params: list[Any] = []
        if profile:
            query += " AND profile=?"
            params.append(profile)
        if level:
            query += " AND level=?"
            params.append(level)
        if board:
            query += " AND board=?"
            params.append(board)
        query += " ORDER BY mean_score DESC"
        return [dict(row) for row in self.conn.execute(query, params).fetchall()]

    def get_score(self, score_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM scores WHERE id=?", (score_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["task_scores"] = [dict(r) for r in self.conn.execute("SELECT * FROM task_scores WHERE score_id=? ORDER BY task_id", (score_id,)).fetchall()]
        result["run_manifests"] = [dict(r) for r in self.conn.execute("SELECT * FROM run_manifests WHERE score_id=? ORDER BY task_id", (score_id,)).fetchall()]
        result["verifications"] = [dict(r) for r in self.conn.execute("SELECT * FROM verifications WHERE score_id=? ORDER BY created_at", (score_id,)).fetchall()]
        result["disputes"] = [dict(r) for r in self.conn.execute("SELECT * FROM disputes WHERE score_id=? ORDER BY created_at", (score_id,)).fetchall()]
        return result

    def set_status(self, score_id: str, status: str) -> None:
        self.conn.execute("UPDATE scores SET status=? WHERE id=?", (status, score_id))
        self.conn.commit()

    def set_tier(self, score_id: str, tier: str) -> None:
        self.conn.execute("UPDATE scores SET tier=? WHERE id=?", (tier, score_id))
        self.conn.commit()

    # -- verifications -------------------------------------------------------
    def record_verification(self, *, score_id: str, verifier: str, org: str | None, run_id: str, task_id: str, seed: int, reproduced_total: float) -> dict[str, Any]:
        score = self.get_score(score_id)
        if score is None:
            raise KeyError(f"unknown score_id: {score_id}")
        within = score["ci_low"] <= reproduced_total <= score["ci_high"]
        self.conn.execute(
            "INSERT INTO verifications (id, score_id, verifier, org, run_id, task_id, seed, reproduced_total, within_ci) VALUES (?,?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), score_id, verifier, org, run_id, task_id, int(seed), float(reproduced_total), 1 if within else 0),
        )
        self.conn.commit()
        return {"within_ci": within}

    def verification_counts(self, score_id: str) -> dict[str, int]:
        rows = self.conn.execute("SELECT within_ci, COUNT(*) AS n FROM verifications WHERE score_id=? GROUP BY within_ci", (score_id,)).fetchall()
        counts = {"within": 0, "outside": 0}
        for row in rows:
            counts["within" if row["within_ci"] else "outside"] = int(row["n"])
        return counts

    # -- disputes --------------------------------------------------------------
    def create_dispute(self, *, score_id: str, reason: str) -> str:
        dispute_id = str(uuid.uuid4())
        self.conn.execute(
            "INSERT INTO disputes (id, score_id, status, reason) VALUES (?,?, 'open', ?)",
            (dispute_id, score_id, reason),
        )
        self.conn.commit()
        return dispute_id

    def list_disputes(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM disputes ORDER BY created_at DESC").fetchall()]

    def resolve_dispute(self, dispute_id: str, *, status: str, resolution: str) -> None:
        self.conn.execute("UPDATE disputes SET status=?, resolution=? WHERE id=?", (status, resolution, dispute_id))
        self.conn.commit()

    # -- reputation --------------------------------------------------------------
    def award_reputation(self, *, subject: str, points: int, reason: str) -> None:
        self.conn.execute(
            "INSERT INTO reputation (id, subject, points, reason) VALUES (?,?,?,?)",
            (str(uuid.uuid4()), subject, int(points), reason),
        )
        self.conn.commit()

    def reputation_board(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT subject, SUM(points) AS points FROM reputation GROUP BY subject ORDER BY points DESC"
        ).fetchall()
        return [dict(r) for r in rows]
