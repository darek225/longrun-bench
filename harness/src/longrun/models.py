from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Budgets:
    steps: int
    wall_clock_minutes: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Budgets":
        return cls(
            steps=int(data.get("steps", 20)),
            wall_clock_minutes=int(data.get("wall_clock_minutes", 15)),
        )

    def to_dict(self) -> dict[str, int]:
        return {"steps": self.steps, "wall_clock_minutes": self.wall_clock_minutes}


@dataclass(frozen=True)
class RubricCriterion:
    criterion: str
    weight: float
    anchors: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RubricCriterion":
        return cls(
            criterion=str(data["criterion"]),
            weight=float(data["weight"]),
            anchors=dict(data.get("anchors", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"criterion": self.criterion, "weight": self.weight, "anchors": self.anchors}


@dataclass
class TaskManifest:
    task_dir: Path
    raw: dict[str, Any]
    id: str
    level: int
    category: str
    version: str
    prompt_template: str
    parameters: dict[str, Any]
    budgets: Budgets
    rubric: list[RubricCriterion]
    deterministic_checks: list[dict[str, Any]]
    network_allowlist: list[str] = field(default_factory=list)
    quarters_active: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, task_dir: Path, data: dict[str, Any]) -> "TaskManifest":
        return cls(
            task_dir=task_dir,
            raw=data,
            id=str(data["id"]),
            level=int(data["level"]),
            category=str(data["category"]),
            version=str(data.get("version", "0.1.0")),
            prompt_template=str(data["prompt_template"]),
            parameters=dict(data.get("parameters", {})),
            budgets=Budgets.from_dict(dict(data.get("budgets", {}))),
            rubric=[RubricCriterion.from_dict(item) for item in data.get("rubric", [])],
            deterministic_checks=list(data.get("deterministic_checks", [])),
            network_allowlist=[str(item) for item in data.get("network_allowlist", [])],
            quarters_active=[str(item) for item in data.get("quarters_active", [])],
        )


@dataclass
class TaskInstance:
    task_id: str
    task_dir: Path
    seed: int
    params: dict[str, Any]
    prompt: str
    budgets: Budgets
    rubric: list[RubricCriterion]
    deterministic_checks: list[dict[str, Any]]
    network_allowlist: list[str]
    task_set_version: str = "0.1.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_dir": str(self.task_dir),
            "seed": self.seed,
            "params": self.params,
            "prompt": self.prompt,
            "budgets": self.budgets.to_dict(),
            "rubric": [item.to_dict() for item in self.rubric],
            "deterministic_checks": self.deterministic_checks,
            "network_allowlist": self.network_allowlist,
            "task_set_version": self.task_set_version,
        }
