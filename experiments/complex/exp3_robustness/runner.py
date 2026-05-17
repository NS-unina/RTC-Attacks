"""Experiment 3 — Detection Robustness under Load.

Objective: verify that the IDS does not miss attacks when the host is under load.
Answers: "detection accuracy under increased traffic load."

Design:
  1. Create a constant background load by running N stacks concurrently.
  2. Inject a single "probe" attack (silent, low-traffic scenario).
  3. Measure whether the IDS fired the expected alert.
  4. Repeat at increasing background load levels to plot Recall vs CPU Load.

NOTE: This experiment MUST run on a physical host (not a VM) to get
meaningful CPU/RAM saturation data.

Results are written to ``experiments/results/exp3_robustness/<run_tag>/``.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterator

import typer

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments import config as cfg
from experiments.core.timing import utc_now_iso, utc_tag
from experiments.infra.capture import CaptureStore
from experiments.infra.ids import IdsController
from experiments.infra.scenario_runner import ScenarioRunnerAdapter
from experiments.infra.shell import StepResult, write_cli_log
from experiments.pipeline import ids_dataset_pipeline as ids_pipeline


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ProbeResult:
    """Outcome of a single probe attack under a given background load."""

    load_level: int          # Number of concurrent background stacks
    probe_scenario_id: int
    monitoring_enabled: bool

    runner_exit_code: int
    runner_summary_path: str
    capture_root: str

    event_total: int
    event_detected_count: int
    event_recall: float      # 1.0 = IDS fired, 0.0 = IDS missed
    alert_count: int

    probe_ok: bool
    error: str


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class RobustnessConfig:
    """Parameters for Experiment 3."""

    # Number of background stacks to run at each load level.
    load_levels: list[int]          # e.g. [0, 2, 4, 6, 8]

    # The "silent" attack used as probe.
    probe_scenario_id: int          # e.g. 7 (NoSQLi) or 8 (XSS)

    # Background scenario to create load (heavy traffic, e.g. scenario 4).
    background_scenario_id: int

    output_dir: Path

    ids_warmup_sec: float = 2.0
    ids_cooldown_sec: float = 2.0
    alert_window_post_sec: float = 5.0
    timeline_bin_sec: float = 1.0


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class RobustnessRunner:
    """Orchestrator for Experiment 3 (Detection Robustness under Load).

    Usage::

        config = RobustnessConfig(
            load_levels=[0, 2, 4, 6, 8],
            probe_scenario_id=7,
            background_scenario_id=4,
            output_dir=Path("experiments/results/exp3_robustness/run_01"),
        )
        runner = RobustnessRunner(config, repo_root=Path("."))
        for result in runner.run():
            print(result)
    """

    def __init__(self, config: RobustnessConfig, repo_root: Path) -> None:
        self._config = config
        self._repo_root = repo_root
        self._capture_store = CaptureStore(repo_root)
        self._scenario_runner = ScenarioRunnerAdapter(repo_root)
        self._ids = IdsController(repo_root)

    def run(self) -> Iterator[ProbeResult]:
        """Execute probe at each load level. Yields one result per level."""
        cfg = self._config
        cfg.output_dir.mkdir(parents=True, exist_ok=True)

        all_results: list[ProbeResult] = []
        for level in cfg.load_levels:
            result = self._run_at_load(level)
            all_results.append(result)
            yield result

        self._write_report(all_results)

    # ------------------------------------------------------------------
    # Internal: single probe at a given load level
    # ------------------------------------------------------------------

    def _run_at_load(self, load_level: int) -> ProbeResult:
        cfg = self._config
        level_dir = cfg.output_dir / f"load_{load_level:02d}"
        level_dir.mkdir(parents=True, exist_ok=True)

        runner_dir = level_dir / "probe_runner"
        alerts_file = level_dir / "alerts.jsonl"
        attack_events_file = level_dir / "attack_events.json"
        alert_validation_file = level_dir / "alert_validation.json"

        run_proc = None
        background_proc = None
        background_log = None
        runner_summary_path = ""
        capture_root_path = ""

        try:
            self._ids.start()
            time.sleep(cfg.ids_warmup_sec)

            if load_level > 0:
                # Change rationale: robustness must probe while background load is active.
                background_proc, background_log = self._scenario_runner.start_spike_background(
                    scenario_id=cfg.background_scenario_id,
                    max_instances=load_level,
                    output_dir=level_dir / "background_runner",
                    log_path=level_dir / "background_runner.log",
                )
                time.sleep(1)

            # Inject the probe attack.
            run_proc, summary_file = self._scenario_runner.run_spike(
                scenario_id=cfg.probe_scenario_id,
                max_instances=1,
                output_dir=runner_dir,
            )
            write_cli_log(level_dir / "probe_cli.log", run_proc)
            runner_summary_path = str(summary_file)

        finally:
            time.sleep(cfg.ids_cooldown_sec)
            self._ids.stop()
            # Stop background stacks so the host is clean for the next step.
            self._scenario_runner.stop_all()
            if background_proc is not None and background_proc.poll() is None:
                background_proc.terminate()
                try:
                    background_proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    background_proc.kill()
            if background_log is not None:
                background_log.close()
            time.sleep(1)

        capture_root = self._capture_store.latest_capture_root()
        capture_root_path = str(capture_root)

        if run_proc is None or run_proc.returncode != 0:
            return ProbeResult(
                load_level=load_level,
                probe_scenario_id=cfg.probe_scenario_id,
                monitoring_enabled=True,
                runner_exit_code=1,
                runner_summary_path=runner_summary_path,
                capture_root=capture_root_path,
                event_total=0, event_detected_count=0,
                event_recall=0.0, alert_count=0,
                probe_ok=False, error="probe runner failed",
            )

        # Build alerts and validate.
        alerts_step = self._build_alerts(capture_root, alerts_file)
        if not alerts_step.ok:
            return ProbeResult(
                load_level=load_level,
                probe_scenario_id=cfg.probe_scenario_id,
                monitoring_enabled=True,
                runner_exit_code=run_proc.returncode,
                runner_summary_path=runner_summary_path,
                capture_root=capture_root_path,
                event_total=0, event_detected_count=0,
                event_recall=0.0, alert_count=0,
                probe_ok=False, error="build-alerts failed",
            )

        events_step = self._build_attack_events(summary_file, attack_events_file)
        if not events_step.ok:
            return ProbeResult(
                load_level=load_level,
                probe_scenario_id=cfg.probe_scenario_id,
                monitoring_enabled=True,
                runner_exit_code=run_proc.returncode,
                runner_summary_path=runner_summary_path,
                capture_root=capture_root_path,
                event_total=0, event_detected_count=0,
                event_recall=0.0, alert_count=0,
                probe_ok=False, error="build-attack-events failed",
            )

        validate_step = self._validate_alerts(alerts_file, summary_file, alert_validation_file)

        alert_count = self._count_alerts(alerts_file)
        event_total, event_detected, event_recall = 0, 0, 0.0
        probe_ok = False

        if validate_step.ok and alert_validation_file.exists():
            payload = json.loads(alert_validation_file.read_text(encoding="utf-8"))
            em = payload.get("metrics", {})
            event_total = int(em.get("total_events", 0))
            event_detected = int(em.get("detected_events", 0))
            event_recall = float(em.get("event_recall", 0.0))
            probe_ok = bool(payload.get("validation_passed", False))

        return ProbeResult(
            load_level=load_level,
            probe_scenario_id=cfg.probe_scenario_id,
            monitoring_enabled=True,
            runner_exit_code=run_proc.returncode,
            runner_summary_path=runner_summary_path,
            capture_root=capture_root_path,
            event_total=event_total,
            event_detected_count=event_detected,
            event_recall=event_recall,
            alert_count=alert_count,
            probe_ok=probe_ok,
            error="",
        )

    # ------------------------------------------------------------------
    # Pipeline wrappers
    # ------------------------------------------------------------------

    def _build_alerts(self, capture_root: Path, alerts_file: Path) -> StepResult:
        try:
            ids_pipeline.build_suricata_alerts_from_pcap(
                pcap_input=capture_root / "pcap",
                output_alert_file=alerts_file,
                project_root=self._repo_root,
                suricata_image="suricata-rtc",
                suricata_rules="/etc/suricata/local.rules",
            )
            return StepResult(returncode=0, stdout="ok", stderr="")
        except Exception as exc:
            return StepResult(returncode=1, stdout="", stderr=str(exc))

    def _build_attack_events(self, summary_file: Path, output_path: Path) -> StepResult:
        try:
            ids_pipeline.build_attack_events_from_runner_summary(
                summary_file=summary_file,
                output_file=output_path,
            )
            return StepResult(returncode=0, stdout="ok", stderr="")
        except Exception as exc:
            return StepResult(returncode=1, stdout="", stderr=str(exc))

    def _validate_alerts(
        self, alerts_path: Path, summary_file: Path, output_path: Path
    ) -> StepResult:
        cfg = self._config
        try:
            ids_pipeline.build_alert_validation_report(
                alert_file=alerts_path,
                output_file=output_path,
                runner_summary_file=summary_file,
                window_pre_sec=0.0,
                window_post_sec=cfg.alert_window_post_sec,
                timeline_bin_sec=cfg.timeline_bin_sec,
            )
            return StepResult(returncode=0, stdout="ok", stderr="")
        except Exception as exc:
            return StepResult(returncode=1, stdout="", stderr=str(exc))

    def _count_alerts(self, alerts_file: Path) -> int:
        if not alerts_file.exists():
            return 0
        count = 0
        for line in alerts_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line.startswith("{"):
                count += 1
        return count

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------

    def _write_report(self, results: list[ProbeResult]) -> None:
        payload = {
            "experiment": "exp3_robustness",
            "generated_at_utc": utc_now_iso(),
            "config": {
                "load_levels": self._config.load_levels,
                "probe_scenario_id": self._config.probe_scenario_id,
                "background_scenario_id": self._config.background_scenario_id,
            },
            "recall_vs_load": [
                {"load_level": r.load_level, "event_recall": r.event_recall}
                for r in results
            ],
            "results": [asdict(r) for r in results],
        }
        report_path = self._config.output_dir / "report.json"
        report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\n[exp3] Report written to: {report_path}")


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

app = typer.Typer()


@app.command()
def main(
    load_levels: str = typer.Option("0,2,4,6,8", help="Comma-separated background stack counts"),
    probe_scenario: int = typer.Option(7, help="Probe scenario ID"),
    background_scenario: int = typer.Option(4, help="Background load scenario ID"),
    output_dir: str = typer.Option(None, help="Output directory (auto-generated if omitted)"),
) -> None:
    """Experiment 3 — Detection Robustness under Load."""
    # Simplified parsing with list comprehension
    levels = [int(x.strip()) for x in load_levels.split(",") if x.strip()]
    
    out_dir = (
        Path(output_dir).expanduser().resolve()
        if output_dir
        else REPO_ROOT / "experiments" / "results" / "exp3_robustness" / f"run_{utc_tag()}"
    )

    config = RobustnessConfig(
        load_levels=levels,
        probe_scenario_id=probe_scenario,
        background_scenario_id=background_scenario,
        output_dir=out_dir,
        ids_warmup_sec=cfg.get("timing.ids_warmup_sec"),
        ids_cooldown_sec=cfg.get("timing.ids_cooldown_sec"),
        alert_window_post_sec=cfg.get("timing.alert_window_post_sec"),
        timeline_bin_sec=cfg.get("timing.timeline_bin_sec"),
    )

    runner = RobustnessRunner(config, repo_root=REPO_ROOT)
    for result in runner.run():
        status = "DETECTED" if result.probe_ok else f"MISSED({result.error})"
        print(f"[exp3] load={result.load_level} probe={result.probe_scenario_id} recall={result.event_recall:.3f} alerts={result.alert_count} → {status}")


if __name__ == "__main__":
    app()
