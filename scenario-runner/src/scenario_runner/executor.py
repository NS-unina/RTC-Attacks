from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import os
import subprocess
import time
from typing import Dict, IO, List

from .models import PlannedRun, RunConfig, RunResult, ScenarioSpec
from .utils import log_flow


@dataclass
class ActiveProcess:
    planned_run: PlannedRun
    scenario_spec: ScenarioSpec
    command: List[str]
    process: subprocess.Popen
    log_handle: IO[str]
    log_file_path: Path
    start_utc: str
    start_perf: float


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _build_make_command(config: RunConfig, planned_run: PlannedRun) -> List[str]:
    # SCENARIO is passed for all labs for consistency.
    # Labs that do not use this variable will safely ignore it.
    return [
        "make",
        "auto-attack",
        f"INSTANCE={planned_run.instance}",
        f"SCENARIO={planned_run.scenario_id}",
    ]


def execute_plan(
    config: RunConfig,
    planned_runs: List[PlannedRun],
    scenario_catalog: Dict[int, ScenarioSpec],
    run_logs_dir: Path,
    ipc_env: dict[str, str] | None = None,
) -> List[RunResult]:
    start_time = time.monotonic()
    active_processes: Dict[str, ActiveProcess] = {}
    pending_runs = sorted(planned_runs, key=lambda item: item.launch_offset_sec)
    results: List[RunResult] = []

    while pending_runs or active_processes:
        elapsed = time.monotonic() - start_time

        while pending_runs and pending_runs[0].launch_offset_sec <= elapsed:
            planned_run = pending_runs.pop(0)
            scenario_spec = scenario_catalog[planned_run.scenario_id]

            log_file_path = run_logs_dir / f"instance_{planned_run.instance}.log"
            command = _build_make_command(config, planned_run)
            log_flow(
                "Launching instance=%s scenario=%s offset=%.2fs cwd=%s"
                % (
                    planned_run.instance,
                    planned_run.scenario_id,
                    planned_run.launch_offset_sec,
                    scenario_spec.lab_path,
                )
            )

            log_handle = log_file_path.open("w", encoding="utf-8")
            process = subprocess.Popen(  # noqa: S603
                command,
                cwd=str(scenario_spec.lab_path),
                env={**os.environ, **(ipc_env or {})},
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                text=True,
            )
            active_processes[planned_run.instance] = ActiveProcess(
                planned_run=planned_run,
                scenario_spec=scenario_spec,
                command=command,
                process=process,
                log_handle=log_handle,
                log_file_path=log_file_path,
                start_utc=_now_utc_iso(),
                start_perf=time.monotonic(),
            )

        finished_instances: List[str] = []
        for instance, active in active_processes.items():
            exit_code = active.process.poll()
            if exit_code is None:
                continue

            finished_instances.append(instance)
            end_perf = time.monotonic()
            end_utc = _now_utc_iso()
            result = RunResult(
                launch_index=active.planned_run.launch_index,
                instance=active.planned_run.instance,
                scenario_id=active.planned_run.scenario_id,
                lab_path=str(active.scenario_spec.lab_path),
                command=active.command,
                start_utc=active.start_utc,
                end_utc=end_utc,
                duration_sec=end_perf - active.start_perf,
                exit_code=exit_code,
                success=(exit_code == 0),
                log_path=str(active.log_file_path),
            )
            results.append(result)
            log_flow(
                "Completed instance=%s scenario=%s exit=%s duration=%.2fs"
                % (result.instance, result.scenario_id, result.exit_code, result.duration_sec)
            )

        for instance in finished_instances:
            active = active_processes.pop(instance)
            active.log_handle.close()

        if pending_runs or active_processes:
            time.sleep(0.25)

    results.sort(key=lambda item: item.launch_index)
    return results
