"""IDS (Suricata) lifecycle adapter.

Responsibility: start and stop the IDS stack via Makefile targets.
Supports use as a context manager for safe teardown.
"""

from __future__ import annotations

from pathlib import Path

from experiments.infra.shell import StepResult, run_cmd
from experiments.pipeline import ids_dataset_pipeline as ids_pipeline


class IdsController:
    """Controls the Suricata IDS stack through Make targets.

    Usage as context manager ensures the IDS is stopped even on failure:

        with IdsController(repo_root) as ids:
            ids.wait_ready(seconds=2)
            # ... run scenario ...
    """

    def __init__(self, repo_root: Path = Path.cwd()) -> None:
        self._repo_root = repo_root

    def start(self) -> None:
        """Start Suricata via `make start-suricata`."""
        proc = run_cmd(["make", "start-suricata"], cwd=self._repo_root)
        if proc.returncode != 0:
            raise RuntimeError(
                f"make start-suricata failed:\n{proc.stdout}\n{proc.stderr}"
            )

    def stop(self) -> None:
        """Stop Suricata via `make stop-suricata` (best-effort, no exception on failure)."""
        run_cmd(["make", "stop-suricata"], cwd=self._repo_root)

    def __enter__(self) -> "IdsController":
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.stop()


    def build_alerts(self, capture_path: Path, alerts_file: Path) -> StepResult:
        try:
            ids_pipeline.build_suricata_alerts_from_pcap(
                pcap_input=capture_path,
                output_alert_file=alerts_file,
                project_root=self._repo_root,
                suricata_image="suricata-rtc",
                suricata_rules="/etc/suricata/local.rules",
            )
            return StepResult(cmd="build-suricata-alerts-from-pcap", returncode=0, stdout="build-alerts ok", stderr="")
        except Exception as exc:
            print("ERROR building alerts:", exc)
            return StepResult(cmd="build-suricata-alerts-from-pcap", returncode=1, stdout="", stderr=str(exc))