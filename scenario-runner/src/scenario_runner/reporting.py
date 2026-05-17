from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from time import perf_counter

from .models import ExecutionSummary, RunConfig, RunResult
from .utils import save_csv, save_json


def _results_to_rows(results: list[RunResult]) -> list[dict[str, object]]:
    return [asdict(result) for result in results]


def write_reports(
    config: RunConfig,
    results: list[RunResult],
    report_json: Path,
    report_csv: Path,
    started_perf: float,
    ipc_events: list[dict[str, object]] | None = None,
) -> ExecutionSummary:
    rows = _results_to_rows(results)
    duration = perf_counter() - started_perf

    payload = {
        "config": {
            "strategy": config.strategy.value,
            "scenario": config.scenario,
            "max_instances": config.max_instances,
            "interval_sec": config.interval_sec,
            "labs_dir": str(config.labs_dir),
        },
        "results": rows,
        "ipc_events": ipc_events or [],
    }

    save_json(report_json, payload)
    save_csv(report_csv, rows)

    success_runs = sum(1 for result in results if result.success)
    failed_runs = len(results) - success_runs

    return ExecutionSummary(
        strategy=config.strategy,
        max_instances=config.max_instances,
        total_runs=len(results),
        success_runs=success_runs,
        failed_runs=failed_runs,
        duration_sec=duration,
        report_json=str(report_json),
        report_csv=str(report_csv),
    )
