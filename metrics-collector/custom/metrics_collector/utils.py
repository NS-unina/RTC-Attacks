from __future__ import annotations

import csv
from datetime import datetime
import json
import subprocess
import time
from pathlib import Path
from typing import Any, Iterable, List


def run_cmd(cmd: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        check=check,
        text=True,
        capture_output=True,
    )


def timed_cmd(cmd: list[str], cwd: Path, check: bool = True) -> tuple[float, subprocess.CompletedProcess[str]]:
    start = time.perf_counter()
    proc = run_cmd(cmd, cwd=cwd, check=check)
    end = time.perf_counter()
    return (end - start), proc


def log_flow(message: str) -> None:
    """
    Emit a timestamped flow log to help users follow command execution order.
    """
    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[metrics-collector][{timestamp}] {message}", flush=True)


def ensure_metrics_dir(stack_path: Path) -> Path:
    metrics_dir = stack_path / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    return metrics_dir


def save_json(path: Path, data: Any) -> None:
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def save_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_cpu_percent(value: str) -> float:
    return float(value.replace("%", "").strip())


def parse_mem_usage_mb(value: str) -> float:
    used = value.split("/")[0].strip().upper()
    if used.endswith("GIB"):
        return float(used[:-3].strip()) * 1024.0
    if used.endswith("MIB"):
        return float(used[:-3].strip())
    if used.endswith("KIB"):
        return float(used[:-3].strip()) / 1024.0
    return 0.0


def mean(values: Iterable[float]) -> float:
    data: List[float] = list(values)
    if not data:
        return 0.0
    return sum(data) / len(data)
