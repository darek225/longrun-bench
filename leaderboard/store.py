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
CREATE TABLE IF NOT EXISTS verifiers (
  user_id TEXT PRIMARY KEY,
  reputation INT DEFAULT 0,
  opted_in INT DEFAULT 0,
  org TEXT
);
CREATE TABLE IF NOT EXISTS verification_jobs (
  id TEXT PRIMARY KEY,
  score_id TEXT REFERENCES scores(id),
  verifier TEXT REFERENCES verifiers(user_id),
  state TEXT CHECK (state IN ('assigned','submitted','expired')) DEFAULT 'assigned',
  priority INT DEFAULT 0,
  assigned_at TEXT DEFAULT (datetime('now')),
  due_at TEXT
);
CREATE TABLE IF NOT EXISTS api_keys (
  id TEXT PRIMARY KEY,
  key_hash TEXT NOT NULL UNIQUE,     -- sha256 of the key; the key itself is never stored
  label TEXT NOT NULL,
  scope TEXT NOT NULL DEFAULT 'enterprise',
  created_at TEXT DEFAULT (datetime('now')),
  revoked_at TEXT
);
CREATE TABLE IF NOT EXISTS orders (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL CHECK (kind IN ('evaluation','priority_verification')),
  requester TEXT NOT NULL,
  level TEXT,                        -- evaluation: sprint|marathon|ultra
  score_id TEXT REFERENCES scores(id),
  amount_usd REAL NOT NULL,
  fee_to_verifier INT DEFAULT 0,     -- priority verification: the fee passes through to the verifier
  status TEXT NOT NULL DEFAULT 'quoted' CHECK (status IN ('quoted','invoiced','paid','fulfilled','cancelled')),
  payment_ref TEXT,
  note TEXT,
  created_at TEXT DEFAULT (datetime('now')),
  updated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL,
  password_hash TEXT,              -- NULL for Google-only accounts
  google_sub TEXT UNIQUE,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY,     -- sha256 of the cookie token; the token itself is never stored
  user_id TEXT NOT NULL REFERENCES users(id),
  expires_at TEXT NOT NULL,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS upload_tokens (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id),
  token_hash TEXT NOT NULL UNIQUE, -- sha256 of the token; the token is shown once at creation
  label TEXT NOT NULL,
  created_at TEXT DEFAULT (datetime('now')),
  revoked_at TEXT
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
        columns = [row[1] for row in self.conn.execute("PRAGMA table_info(disputes)").fetchall()]
        if "filer" not in columns:
            self.conn.execute("ALTER TABLE disputes ADD COLUMN filer TEXT")
        if "outcome" not in columns:
            self.conn.execute("ALTER TABLE disputes ADD COLUMN outcome TEXT")
        score_columns = [row[1] for row in self.conn.execute("PRAGMA table_info(scores)").fetchall()]
        if "submitter_user_id" not in score_columns:
            self.conn.execute("ALTER TABLE scores ADD COLUMN submitter_user_id TEXT")
        if "submitter_name" not in score_columns:
            self.conn.execute("ALTER TABLE scores ADD COLUMN submitter_name TEXT")
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
        submitter: dict[str, Any] | None = None,
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
            "mean_score, ci_low, ci_high, median_score, n_tasks, n_runs, gen_gap, gap_flag, provisional, supersedes, "
            "submitter_user_id, submitter_name) "
            "VALUES (?,?,?,?,?,?,?,?,?,'provisional',?,?,?,?,?,?,?, ?,?,?,?,?)",
            (
                score_id, agent_name, model, profile, level, task_set, harness_hash, board, tier,
                agg["mean_score"], agg["ci_low"], agg["ci_high"], agg["median_score"], agg["n_tasks"], agg["n_runs"],
                gen_gap, 1 if (gen_gap is not None and abs(gen_gap) >= 10) else 0,
                1 if agg["provisional"] else 0,
                previous["id"] if previous else None,
                submitter.get("id") if submitter else None,
                submitter.get("display_name") if submitter else None,
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
        result["verification_jobs"] = [dict(r) for r in self.conn.execute("SELECT * FROM verification_jobs WHERE score_id=? ORDER BY assigned_at", (score_id,)).fetchall()]
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
        rows = self.conn.execute("SELECT within_ci, COUNT(DISTINCT verifier) AS n FROM verifications WHERE score_id=? GROUP BY within_ci", (score_id,)).fetchall()
        counts = {"within": 0, "outside": 0}
        for row in rows:
            counts["within" if row["within_ci"] else "outside"] = int(row["n"])
        return counts

    # -- disputes --------------------------------------------------------------
    def create_dispute(self, *, score_id: str, reason: str, filer: str | None = None) -> str:
        dispute_id = str(uuid.uuid4())
        self.conn.execute(
            "INSERT INTO disputes (id, score_id, status, reason, filer) VALUES (?,?, 'open', ?, ?)",
            (dispute_id, score_id, reason, filer),
        )
        self.conn.commit()
        return dispute_id

    def get_dispute(self, dispute_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM disputes WHERE id=?", (dispute_id,)).fetchone()
        return dict(row) if row else None

    def list_disputes(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM disputes ORDER BY created_at DESC").fetchall()]

    def resolve_dispute(self, dispute_id: str, *, status: str, resolution: str, outcome: str | None = None) -> None:
        self.conn.execute("UPDATE disputes SET status=?, resolution=?, outcome=? WHERE id=?", (status, resolution, outcome, dispute_id))
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

    def reputation_balance(self, subject: str) -> int:
        row = self.conn.execute("SELECT COALESCE(SUM(points), 0) AS balance FROM reputation WHERE subject=?", (subject,)).fetchone()
        return int(row["balance"])

    # -- verification lottery (docs/plan/07 §2, docs/plan/15 §6) --------------
    def upsert_verifier(self, *, user_id: str, org: str | None, opted_in: bool = True) -> None:
        self.conn.execute(
            "INSERT INTO verifiers (user_id, org, opted_in, reputation) VALUES (?,?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET org=excluded.org, opted_in=excluded.opted_in",
            (user_id, org, 1 if opted_in else 0, self.reputation_balance(user_id)),
        )
        self.conn.commit()

    def list_verifiers(self, *, opted_in_only: bool = True) -> list[dict[str, Any]]:
        query = "SELECT * FROM verifiers"
        if opted_in_only:
            query += " WHERE opted_in=1"
        return [dict(r) for r in self.conn.execute(query + " ORDER BY user_id").fetchall()]

    def insert_job(self, *, score_id: str, verifier: str, assigned_at: str, due_at: str, priority: bool = False) -> str:
        job_id = str(uuid.uuid4())
        self.conn.execute(
            "INSERT INTO verification_jobs (id, score_id, verifier, state, priority, assigned_at, due_at) VALUES (?,?,?,'assigned',?,?,?)",
            (job_id, score_id, verifier, 1 if priority else 0, assigned_at, due_at),
        )
        self.conn.commit()
        return job_id

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM verification_jobs WHERE id=?", (job_id,)).fetchone()
        return dict(row) if row else None

    def list_jobs(self, *, score_id: str | None = None, verifier: str | None = None, state: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM verification_jobs WHERE 1=1"
        params: list[Any] = []
        if score_id:
            query += " AND score_id=?"
            params.append(score_id)
        if verifier:
            query += " AND verifier=?"
            params.append(verifier)
        if state:
            query += " AND state=?"
            params.append(state)
        return [dict(r) for r in self.conn.execute(query + " ORDER BY assigned_at", params).fetchall()]

    def set_job_state(self, job_id: str, state: str) -> None:
        self.conn.execute("UPDATE verification_jobs SET state=? WHERE id=?", (state, job_id))
        self.conn.commit()

    # -- score history (enterprise API, SPEC.md §9) ---------------------------
    def score_history(self, *, agent_name: str | None = None, model: str | None = None, profile: str | None = None, level: str | None = None, board: str | None = None) -> list[dict[str, Any]]:
        """Every score row including superseded ones, chronological. The
        public board shows only the latest row per configuration; history is
        the enterprise view (docs/plan/08 §3)."""
        query = "SELECT * FROM scores WHERE 1=1"
        params: list[Any] = []
        for column, value in (("agent_name", agent_name), ("model", model), ("profile", profile), ("level", level), ("board", board)):
            if value:
                query += f" AND {column}=?"
                params.append(value)
        query += " ORDER BY created_at, rowid"
        return [dict(row) for row in self.conn.execute(query, params).fetchall()]

    # -- enterprise API keys ---------------------------------------------------
    def create_api_key(self, *, key_hash: str, label: str, scope: str = "enterprise") -> str:
        key_id = str(uuid.uuid4())
        self.conn.execute(
            "INSERT INTO api_keys (id, key_hash, label, scope) VALUES (?,?,?,?)",
            (key_id, key_hash, label, scope),
        )
        self.conn.commit()
        return key_id

    def api_key_by_hash(self, key_hash: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM api_keys WHERE key_hash=?", (key_hash,)).fetchone()
        return dict(row) if row else None

    def list_api_keys(self) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT id, label, scope, created_at, revoked_at FROM api_keys ORDER BY created_at").fetchall()
        return [dict(r) for r in rows]

    def revoke_api_key(self, key_id: str) -> bool:
        cursor = self.conn.execute("UPDATE api_keys SET revoked_at=datetime('now') WHERE id=? AND revoked_at IS NULL", (key_id,))
        self.conn.commit()
        return cursor.rowcount > 0

    # -- orders (Phase 3 paid services, SPEC.md §9) ------------------------------
    def create_order(self, *, kind: str, requester: str, level: str | None, score_id: str | None, amount_usd: float, fee_to_verifier: bool, note: str | None = None) -> str:
        order_id = str(uuid.uuid4())
        self.conn.execute(
            "INSERT INTO orders (id, kind, requester, level, score_id, amount_usd, fee_to_verifier, note) VALUES (?,?,?,?,?,?,?,?)",
            (order_id, kind, requester, level, score_id, float(amount_usd), 1 if fee_to_verifier else 0, note),
        )
        self.conn.commit()
        return order_id

    def get_order(self, order_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        return dict(row) if row else None

    def list_orders(self, *, requester: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM orders WHERE 1=1"
        params: list[Any] = []
        if requester:
            query += " AND requester=?"
            params.append(requester)
        if status:
            query += " AND status=?"
            params.append(status)
        return [dict(r) for r in self.conn.execute(query + " ORDER BY created_at, rowid", params).fetchall()]

    def update_order(self, order_id: str, **fields: Any) -> None:
        allowed = {"status", "payment_ref", "score_id", "note"}
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            return
        assignments = ", ".join(f"{key}=?" for key in updates) + ", updated_at=datetime('now')"
        self.conn.execute(f"UPDATE orders SET {assignments} WHERE id=?", (*updates.values(), order_id))
        self.conn.commit()
