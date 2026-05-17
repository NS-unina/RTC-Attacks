
from pathlib import Path

from experiments.infra.shell import StepResult, run_cmd
import time


class MakeRunner:
    """Utility to run 'make auto-attack' commands for given scenario/instance."""

    def __init__(self, lab_path: Path, scenario_id: int = 1, instance: int = "default"):
        self.lab_path = lab_path
        self.scenario_id = scenario_id
        self.instance = instance

    def write_cli_log(self, log_path: Path, proc: StepResult, append: bool = True) -> None:
        """Persist stdout/stderr of a subprocess to a file for post-mortem inspection."""
        # print(f"Writing CLI log to {log_path}...")
        mode = 'a' if append else 'w'
        log_content = f"CMD: {proc.cmd}\n returncode: {proc.returncode}\nSTDOUT:\n{proc.stdout}\n\nSTDERR:\n{proc.stderr}\n"
        with log_path.open(mode=mode, encoding="utf-8") as f:
            f.write(log_content)

    def start(self):
        cmd = [
            "make",
            "start",
            f"SCENARIO={self.scenario_id}",
            f"INSTANCE={self.instance}",
        ]
        proc = run_cmd(cmd, cwd=self.lab_path)
        return StepResult(
            cmd=" ".join(cmd),
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )

    def stop(self):
        cmd = [
            "make",
            "stop",
            f"SCENARIO={self.scenario_id}",
            f"INSTANCE={self.instance}",
        ]
        proc = run_cmd(cmd, cwd=self.lab_path)
        return StepResult(
            cmd=" ".join(cmd),
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )

    def attack(self, waiting_time: int = 2):

        time.sleep(waiting_time)  # Wait for lab to be fully ready
        cmd = [
            "make",
            "attack",
            f"SCENARIO={self.scenario_id}",
            f"INSTANCE={self.instance}",
        ]
        proc = run_cmd(cmd, cwd=self.lab_path)
        return StepResult(
            cmd=" ".join(cmd),
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )