from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class Strategy(str, Enum):
    STAGGERED = "staggered"
    SPIKE = "spike"


@dataclass(frozen=True)
class ScenarioSpec:
    scenario_id: int
    lab_path: Path


@dataclass(frozen=True)
class RunConfig:
    strategy: Strategy
    scenario: int
    max_instances: int
    interval_sec: float
    labs_dir: Path
    output_dir: Path

    def __post_init__(self) -> None:
        if self.max_instances < 1:
            raise ValueError("max_instances must be >= 1")
        if self.interval_sec <= 0:
            raise ValueError("interval_sec must be > 0")


@dataclass(frozen=True)
class PlannedRun:
    launch_index: int
    launch_offset_sec: float
    instance: str
    scenario_id: int


@dataclass(frozen=True)
class RunResult:
    launch_index: int
    instance: str
    scenario_id: int
    lab_path: str
    command: list[str]
    start_utc: str
    end_utc: str
    duration_sec: float
    exit_code: int
    success: bool
    log_path: str


@dataclass(frozen=True)
class ExecutionSummary:
    strategy: Strategy
    max_instances: int
    total_runs: int
    success_runs: int
    failed_runs: int
    duration_sec: float
    report_json: str
    report_csv: str
