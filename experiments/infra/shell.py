"""Low-level shell execution utilities.

Responsibility: run subprocess commands and capture their output.
This module has no knowledge of the experiment domain.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence
import subprocess


@dataclass
class StepResult:
    """Result of a single orchestration step."""

    cmd: str 
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def raise_on_failure(self, step_name: str) -> None:
        if not self.ok:
            raise RuntimeError(
                f"Step '{step_name}' failed (rc={self.returncode}):\n{self.stderr}"
            )


def run_cmd(
    cmd: Sequence[str],
    cwd: Path,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run a shell command in *cwd* and return the CompletedProcess."""
    return subprocess.run(  # noqa: S603
        list(cmd),
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=check,
    )


def write_cli_log(log_path: Path, proc: subprocess.CompletedProcess[str]) -> None:
    """Persist stdout/stderr of a subprocess to a file for post-mortem inspection."""
    log_path.write_text(
        f"STDOUT:\n{proc.stdout}\n\nSTDERR:\n{proc.stderr}\n",
        encoding="utf-8",
    )


class MakeRunner:
    """Utility to run 'make auto-attack' commands for given scenario/instance."""

    def __init__(self, lab_path: Path):
        self.lab_path = lab_path

    def start(self, scenario_id: int = 1, instance: int = "default") -> StepResult:
        cmd = [
            "make",
            "start",
            f"SCENARIO={scenario_id}",
            f"INSTANCE={instance}",
        ]
        proc = run_cmd(cmd, cwd=self.lab_path)
        return StepResult(
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )

    def stop(self, scenario_id: int = 1, instance: int = "default") -> StepResult:
        cmd = [
            "make",
            "stop",
            f"SCENARIO={scenario_id}",
            f"INSTANCE={instance}",
        ]
        proc = run_cmd(cmd, cwd=self.lab_path)
        return StepResult(
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )

    def attack(self, scenario_id: int = 1, instance: int = "default") -> StepResult:
        cmd = [
            "make",
            "attack",
            f"SCENARIO={scenario_id}",
            f"INSTANCE={instance}",
        ]
        proc = run_cmd(cmd, cwd=self.lab_path)
        return StepResult(
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )