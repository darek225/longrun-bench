from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ultra session state (docs/plan/09-remaining-details.md §4, SPEC.md §2).
#
# Ultra runs span sessions: the harness enforces session boundaries, state
# snapshots at each boundary, and the runner resumes with the workspace and
# memory file intact. The snapshot is this file (session.json in the run
# directory). It records everything needed to re-render the exact instance
# and to keep budgets cumulative across sessions: steps and tokens spent in
# earlier sessions count against the same run budgets, always.

SESSION_FILE = "session.json"
STATUSES = ("in_progress", "paused", "completed", "abandoned")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class SessionState:
    run_id: str
    task_id: str
    task_dir: str
    seed: int
    params: dict[str, Any]
    agent: dict[str, Any]
    session_number: int = 0
    steps_used: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    wall_clock_s: float = 0.0
    status: str = "in_progress"
    schedule: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "task_dir": self.task_dir,
            "seed": self.seed,
            "params": self.params,
            "agent": self.agent,
            "session_number": self.session_number,
            "steps_used": self.steps_used,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "wall_clock_s": self.wall_clock_s,
            "status": self.status,
            "schedule": self.schedule,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionState":
        return cls(
            run_id=str(data["run_id"]),
            task_id=str(data["task_id"]),
            task_dir=str(data["task_dir"]),
            seed=int(data["seed"]),
            params=dict(data.get("params", {})),
            agent=dict(data.get("agent", {})),
            session_number=int(data.get("session_number", 0)),
            steps_used=int(data.get("steps_used", 0)),
            input_tokens=int(data.get("input_tokens", 0)),
            output_tokens=int(data.get("output_tokens", 0)),
            wall_clock_s=float(data.get("wall_clock_s", 0.0)),
            status=str(data.get("status", "in_progress")),
            schedule=list(data.get("schedule", [])),
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
        )

    def save(self, run_dir: str | Path) -> Path:
        self.updated_at = _utc_now()
        if not self.created_at:
            self.created_at = self.updated_at
        path = Path(run_dir) / SESSION_FILE
        path.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        return path

    def record_session(self, *, steps: int, wall_clock_s: float, end_reason: str) -> None:
        """Append one completed session to the schedule log (plan 09 §4: the
        runner commits to a schedule; the log is the record of keeping it)."""
        self.schedule.append(
            {
                "session": self.session_number,
                "ended_at": _utc_now(),
                "steps_this_session": int(steps),
                "wall_clock_s": round(float(wall_clock_s), 4),
                "end_reason": end_reason,
            }
        )


def load_session(run_dir: str | Path) -> SessionState | None:
    path = Path(run_dir) / SESSION_FILE
    if not path.exists():
        return None
    return SessionState.from_dict(json.loads(path.read_text(encoding="utf-8")))
