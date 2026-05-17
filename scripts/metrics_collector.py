#!/usr/bin/env python3
"""Deprecated compatibility wrapper for the standalone metrics collector script.

Change rationale: the legacy script duplicated functionality now maintained in
`metrics-collector/`. This wrapper keeps backward compatibility while routing
all executions to the maintained CLI.
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    collector_dir = repo_root / "metrics-collector"
    if not collector_dir.exists():
        print("metrics-collector directory not found.", file=sys.stderr)
        return 2

    print(
        "[deprecated] scripts/metrics_collector.py now forwards to metrics-collector CLI."
    )
    command = ["poetry", "run", "metrics-collector", *sys.argv[1:]]
    completed = subprocess.run(command, cwd=collector_dir, check=False)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
