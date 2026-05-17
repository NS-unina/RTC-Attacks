"""Experiment 1 — Baseline Characteristics.

Objective: measure the "cost" of each scenario under ideal conditions.
Each scenario is executed N times (default 30) with monitoring ON or OFF.

Per-run outcomes:
  - scenario execution success / failure
  - IDS detection: TP / TN / FP / FN, Precision, Recall, F1
  - event-level recall (attack windows)

Results are written to ``experiments/results/exp1_baseline/<run_tag>/``.
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
from experiments.core import logger
from experiments.core.scenario import ALL_SCENARIO_IDS, ScenarioSidsEvents, get_scenario_spec, parse_scenario_list
from experiments.core.timing import utc_now_iso, utc_tag
from experiments.infra.capture import CaptureStore
from experiments.infra.ids import IdsController
from experiments.infra.lab_executor import execute_lab
from experiments.infra.resource_monitor import (
    ResourceMonitor,
    RttTargetConfig,
    ScenarioRttConfig,
    rtt_config_from_ipc_events,
)
from experiments.infra.shell import StepResult, write_cli_log
from experiments.pipeline import ids_dataset_pipeline as ids_pipeline


def _load_ipc_events(summary_file: Path | None) -> list[dict]:
    if summary_file is None or not summary_file.exists():
        return []
    try:
        payload = json.loads(summary_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    events = payload.get("ipc_events", [])
    return events if isinstance(events, list) else []


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class RepetitionResult:
    """Outcome of a single scenario run (one repetition of Experiment 1)."""

    repetition: int
    scenario_id: int
    ids_enabled: bool

    # Execution
    runner_exit_code: int
    runner_summary_path: str
    capture_root: str
    execution_ok: bool

    # IDS event-level
    event_total: int
    event_detected_count: int
    event_recall: float

    # IDS event-level TP/TN/FP/FN
    validation_tp: int
    validation_tn: int
    validation_fp: int
    validation_fn: int

    # IDS flow-level
    flow_tp: int
    flow_tn: int
    flow_fp: int
    flow_fn: int
    flow_precision: float
    flow_recall: float
    flow_f1: float
    flow_accuracy: float

    # Path to resource_metrics.json (always generated; ResourceMonitor always active)
    resource_metrics_path: str

    ok: bool
    error: str


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class BaselineConfig:
    """Parameters for Experiment 1."""

    scenarios: list[int]
    repetitions: int
    ids_enabled: bool  # When True: run IDS (Suricata) and capture traffic; when False: skip IDS/capture
    output_dir: Path
    alert_window_post_sec: float = 5.0
    timeline_bin_sec: float = 1.0
    # Seconds to wait after IDS start before collecting baseline resource samples.
    ids_warmup_sec: float = 2.0
    # Seconds to wait after scenario before stopping IDS.
    ids_cooldown_sec: float = 2.0
    # Resource monitor settings (always active: CPU/RAM/disk/RTT)
    resource_sample_interval_sec: float = 0.25
    resource_baseline_samples: int = 5


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class BaselineRunner:
    """Orchestrator for Experiment 1 (Baseline Characteristics).

    Usage::

        config = BaselineConfig(
            scenarios=[1, 2, 3, 4, 5, 6, 7, 8, 9],
            repetitions=30,
            ids_enabled=True,
            output_dir=Path("experiments/results/exp1_baseline/run_01"),
        )
        runner = BaselineRunner(config, repo_root=Path("."))
        for result in runner.run():
            print(result)
    """

    def __init__(self, config: BaselineConfig, repo_root: Path) -> None:
        self._config = config
        self._repo_root = repo_root
        self._labs_dir = repo_root / "public" / "labs"
        self._capture_store = CaptureStore(repo_root)
        self._ids = IdsController(repo_root)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> Iterator[RepetitionResult]:
        """Execute all repetitions for all scenarios. Yields each result."""
        cfg = self._config

        logger.info("Creating output directory...")
        cfg.output_dir.mkdir(parents=True, exist_ok=True)

        all_results: list[RepetitionResult] = []

        for rep in range(1, cfg.repetitions + 1):
            for scenario_id in cfg.scenarios:
                spec = get_scenario_spec(scenario_id)
                logger.info("Run scenario %d (repetition %d/%d)", scenario_id, rep, cfg.repetitions)
                result = self._run_one(spec, rep)
                all_results.append(result)
                yield result

        self._write_report(all_results)

    # ------------------------------------------------------------------
    # Internal: single run
    # ------------------------------------------------------------------

    def _run_one(self, spec: ScenarioSidsEvents, repetition: int) -> RepetitionResult:
        cfg = self._config
        run_dir = cfg.output_dir / spec.label / f"rep_{repetition:02d}"
        run_dir.mkdir(parents=True, exist_ok=True)

        runner_dir = run_dir / "runner"
        alerts_file = run_dir / "alerts.jsonl"
        attack_events_file = run_dir / "attack_events.json"
        alert_validation_file = run_dir / "alert_validation.json"
        detection_metrics_file = run_dir / "detection_metrics.json"
        dataset_csv = run_dir / "ids_dataset.csv"
        resource_metrics_file = run_dir / "resource_metrics.json"

        runner_summary_path = ""
        capture_root_path = ""
        resource_metrics_path = ""
        run_proc = None
        summary_file: Path | None = None
        live_ipc_events: list[dict] = []

        # ResourceMonitor always active (CPU/RAM/disk/RTT); configured from IPC lab_ready metadata.
        monitor = ResourceMonitor(
            scenario_config=ScenarioRttConfig(),  # Start empty; will be configured from IPC
            sample_interval_sec=cfg.resource_sample_interval_sec,
        )

        try:
            # IDS + capture only when ids_enabled=True
            if cfg.ids_enabled:
                logger.info("IDS ENABLED: Starting IDS...")
                self._ids.start()
                time.sleep(cfg.ids_warmup_sec)


            # Execute lab scenario
            result = execute_lab(
                labs_dir=self._labs_dir,
                scenario_id=spec.scenario_id,
                instance=1,
                output_dir=runner_dir,
            )
            logger.info("Collecting baseline resource metrics...")
            monitor.collect_baseline(cfg.resource_baseline_samples)

            monitor.start_attack_phase()
            logger.info("Scenario executed successfully")
            run_exit_code = result["exit_code"]
            live_ipc_events = result["ipc_events"]
            run_output_dir = Path(result["output_dir"])
            
            # Write summary.json for compatibility
            summary_file = run_output_dir / "summary.json"
            summary_data = {
                "config": {
                    "strategy": "spike",
                    "scenario": spec.scenario_id,
                    "max_instances": 1,
                    "interval_sec": 0.0,
                    "labs_dir": str(self._labs_dir),
                },
                "results": [result],
                "ipc_events": live_ipc_events,
            }
            summary_file.write_text(json.dumps(summary_data, indent=2), encoding="utf-8")
            runner_summary_path = str(summary_file)
            
            # Apply RTT config from IPC events
            ipc_rtt_cfg = rtt_config_from_ipc_events(
                events=live_ipc_events,
                scenario_id=spec.scenario_id,
            )
            if ipc_rtt_cfg.rtt_targets:
                monitor.apply_runtime_rtt_config(ipc_rtt_cfg)
            
            run_proc = subprocess.CompletedProcess(
                args=["make", "auto-attack"],
                returncode=run_exit_code,
                stdout="",
                stderr="",
            )

        finally:

            # ResourceMonitor always saves (always active)
            monitor.stop()
            ipc_events = list(live_ipc_events)
            if not ipc_events:
                ipc_events = _load_ipc_events(summary_file)
            monitor.save(resource_metrics_file, ipc_events)
            resource_metrics_path = str(resource_metrics_file)

            # IDS stop only when it was started
            if cfg.ids_enabled:
                time.sleep(cfg.ids_cooldown_sec)
                self._ids.stop()
                time.sleep(1)

        # Construct failure result helper
        def fail(error: str) -> RepetitionResult:
            return RepetitionResult(
                repetition=repetition,
                scenario_id=spec.scenario_id,
                ids_enabled=cfg.ids_enabled,
                runner_exit_code=1,
                runner_summary_path=runner_summary_path,
                capture_root=capture_root_path,
                execution_ok=False,
                event_total=0,
                event_detected_count=0,
                event_recall=0.0,
                validation_tp=0,
                validation_tn=0,
                validation_fp=0,
                validation_fn=0,
                flow_tp=0,
                flow_tn=0,
                flow_fp=0,
                flow_fn=0,
                flow_precision=0.0,
                flow_recall=0.0,
                flow_f1=0.0,
                flow_accuracy=0.0,
                resource_metrics_path=resource_metrics_path,
                ok=False,
                error=error,
            )

        if run_proc is None or run_proc.returncode != 0:
            return fail("scenario-runner execution failed")
        assert summary_file is not None

        # When IDS is disabled, return execution-only result (no alert/flow metrics)
        if not cfg.ids_enabled:
            return RepetitionResult(
                repetition=repetition,
                scenario_id=spec.scenario_id,
                ids_enabled=False,
                runner_exit_code=run_proc.returncode,
                runner_summary_path=runner_summary_path,
                capture_root=capture_root_path,
                execution_ok=True,
                event_total=0, event_detected_count=0, event_recall=0.0,
                validation_tp=0, validation_tn=0, validation_fp=0, validation_fn=0,
                flow_tp=0, flow_tn=0, flow_fp=0, flow_fn=0,
                flow_precision=0.0, flow_recall=0.0, flow_f1=0.0, flow_accuracy=0.0,
                resource_metrics_path=resource_metrics_path,
                ok=True, error="",
            )

        capture_root = self._capture_store.latest_capture_root()
        capture_root_path = str(capture_root)

        # Build alerts from PCAP
        alerts_step = self._build_alerts(capture_root, alerts_file)
        if not alerts_step.ok:
            return fail("build-alerts failed")

        # Extract attack events from runner summary
        events_step = self._build_attack_events(summary_file, attack_events_file)
        if not events_step.ok:
            return fail("build-attack-events failed")

        # Validate alert/event alignment
        validate_step = self._validate_alerts(
            alerts_file, summary_file, alert_validation_file
        )
        if not validate_step.ok:
            return fail("validate-alerts failed")

        validation = json.loads(alert_validation_file.read_text(encoding="utf-8"))
        event_metrics = validation.get("metrics", {})
        confusion = validation.get("confusion_matrix", {})
        event_total = int(event_metrics.get("total_events", 0))
        event_detected_count = int(event_metrics.get("detected_events", 0))
        event_recall = float(event_metrics.get("event_recall", 0.0))
        # Change rationale: evaluate run success on event-level alert validation.
        event_ok = bool(validation.get("validation_passed", False))

        # Build flow dataset
        dataset_step = self._build_dataset(
            capture_root, alerts_file, attack_events_file, dataset_csv, detection_metrics_file
        )
        if not dataset_step.ok:
            return RepetitionResult(
                repetition=repetition,
                scenario_id=spec.scenario_id,
                ids_enabled=True,
                runner_exit_code=run_proc.returncode,
                runner_summary_path=runner_summary_path,
                capture_root=capture_root_path,
                execution_ok=True,
                event_total=event_total,
                event_detected_count=event_detected_count,
                event_recall=event_recall,
                validation_tp=int(confusion.get("TP", 0)),
                validation_tn=int(confusion.get("TN", 0)),
                validation_fp=int(confusion.get("FP", 0)),
                validation_fn=int(confusion.get("FN", 0)),
                flow_tp=0, flow_tn=0, flow_fp=0, flow_fn=0,
                flow_precision=0.0, flow_recall=0.0, flow_f1=0.0, flow_accuracy=0.0,
                resource_metrics_path=resource_metrics_path,
                ok=False, error="build-dataset failed",
            )

        metrics = json.loads(detection_metrics_file.read_text(encoding="utf-8"))
        ok = event_ok

        return RepetitionResult(
            repetition=repetition,
            scenario_id=spec.scenario_id,
            ids_enabled=True,
            runner_exit_code=run_proc.returncode,
            runner_summary_path=runner_summary_path,
            capture_root=capture_root_path,
            execution_ok=True,
            event_total=event_total,
            event_detected_count=event_detected_count,
            event_recall=event_recall,
            validation_tp=int(confusion.get("TP", 0)),
            validation_tn=int(confusion.get("TN", 0)),
            validation_fp=int(confusion.get("FP", 0)),
            validation_fn=int(confusion.get("FN", 0)),
            flow_tp=int(metrics.get("TP", 0)),
            flow_tn=int(metrics.get("TN", 0)),
            flow_fp=int(metrics.get("FP", 0)),
            flow_fn=int(metrics.get("FN", 0)),
            flow_precision=float(metrics.get("precision", 0.0)),
            flow_recall=float(metrics.get("recall", 0.0)),
            flow_f1=float(metrics.get("f1", 0.0)),
            flow_accuracy=float(metrics.get("accuracy", 0.0)),
            resource_metrics_path=resource_metrics_path,
            ok=ok,
            error="",
        )

    # ------------------------------------------------------------------
    # Pipeline wrappers (delegate to ids_pipeline, capture exceptions)
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
            return StepResult(returncode=0, stdout="build-alerts ok", stderr="")
        except Exception as exc:
            return StepResult(returncode=1, stdout="", stderr=str(exc))

    def _build_attack_events(self, summary_file: Path, output_path: Path) -> StepResult:
        try:
            ids_pipeline.build_attack_events_from_runner_summary(
                summary_file=summary_file,
                output_file=output_path,
            )
            return StepResult(returncode=0, stdout="build-attack-events ok", stderr="")
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
            return StepResult(returncode=0, stdout="validate-alerts ok", stderr="")
        except Exception as exc:
            return StepResult(returncode=1, stdout="", stderr=str(exc))

    def _build_dataset(
        self,
        capture_root: Path,
        alerts_path: Path,
        events_path: Path,
        out_csv: Path,
        metrics_out: Path,
    ) -> StepResult:
        try:
            ids_pipeline._build_dataset_impl(
                pcap_input=capture_root / "pcap",
                alert_file=alerts_path,
                events_file=events_path,
                out_csv=out_csv,
                out_parquet=None,
                metrics_out=metrics_out,
                match_window_sec=3.0,
            )
            return StepResult(returncode=0, stdout="build-dataset ok", stderr="")
        except Exception as exc:
            return StepResult(returncode=1, stdout="", stderr=str(exc))

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------

    def _write_report(self, results: list[RepetitionResult]) -> None:
        summary = _aggregate_baseline(results)
        payload = {
            "experiment": "exp1_baseline",
            "generated_at_utc": utc_now_iso(),
            "config": {
                "scenarios": self._config.scenarios,
                "repetitions": self._config.repetitions,
                "ids_enabled": self._config.ids_enabled,
            },
            "summary": summary,
            "results": [asdict(r) for r in results],
        }
        report_path = self._config.output_dir / "report.json"
        report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\n[exp1] Report written to: {report_path}")

# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------


def _aggregate_baseline(results: list[RepetitionResult]) -> dict:
    """Compute per-scenario averages and success rates."""
    by_scenario: dict[int, dict] = {}
    for r in results:
        slot = by_scenario.setdefault(
            r.scenario_id,
            {
                "runs": 0, "ok_runs": 0,
                "sum_event_recall": 0.0,
                "sum_flow_recall": 0.0,
                "sum_flow_precision": 0.0,
                "sum_flow_f1": 0.0,
            },
        )
        slot["runs"] += 1
        slot["ok_runs"] += int(r.ok)
        slot["sum_event_recall"] += r.event_recall
        slot["sum_flow_recall"] += r.flow_recall
        slot["sum_flow_precision"] += r.flow_precision
        slot["sum_flow_f1"] += r.flow_f1

    aggregated = []
    for sid, slot in sorted(by_scenario.items()):
        n = max(slot["runs"], 1)
        aggregated.append({
            "scenario_id": sid,
            "runs": slot["runs"],
            "success_rate": slot["ok_runs"] / n,
            "avg_event_recall": slot["sum_event_recall"] / n,
            "avg_flow_recall": slot["sum_flow_recall"] / n,
            "avg_flow_precision": slot["sum_flow_precision"] / n,
            "avg_flow_f1": slot["sum_flow_f1"] / n,
        })

    total = len(results)
    return {
        "total_runs": total,
        "overall_success_rate": sum(1 for r in results if r.ok) / max(total, 1),
        "per_scenario": aggregated,
    }


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

app = typer.Typer()


@app.command()
def main(
    scenarios: str = typer.Option(
        cfg.get("experiment1_baseline.default_scenarios"),
        help="Comma-separated scenario IDs",
    ),
    repetitions: int = typer.Option(
        cfg.get("experiment1_baseline.repetitions"),
        help="Runs per scenario",
    ),
    monitoring: str = typer.Option(
        "on" if cfg.get("experiment1_baseline.monitoring_enabled") else "off",
        help="Enable IDS monitoring (on/off)",
    ),
    output_dir: str = typer.Option(
        None,
        help="Output directory (auto-generated if omitted)",
    ),
    alert_window_post_sec: float = typer.Option(
        cfg.get("timing.alert_window_post_sec"),
        help="Post-event alert window in seconds",
    ),
    timeline_bin_sec: float = typer.Option(
        cfg.get("timing.timeline_bin_sec"),
        help="Timeline bin size in seconds",
    ),
) -> None:
    """Experiment 1 — Baseline Characteristics."""
    scenario_list = parse_scenario_list(scenarios)
    out_dir = (
        Path(output_dir).expanduser().resolve()
        if output_dir
        else REPO_ROOT / "experiments" / "results" / "exp1_baseline" / f"run_{utc_tag()}"
    )

    config = BaselineConfig(
        scenarios=scenario_list,
        repetitions=repetitions,
        ids_enabled=(monitoring == "on"),
        output_dir=out_dir,
        alert_window_post_sec=alert_window_post_sec,
        timeline_bin_sec=timeline_bin_sec,
    )

    runner = BaselineRunner(config, repo_root=REPO_ROOT)
    for result in runner.run():
        status = "OK" if result.ok else f"FAIL({result.error})"
        print(
            f"[exp1] rep={result.repetition:02d} scenario={result.scenario_id} "
            f"recall={result.event_recall:.3f} f1={result.flow_f1:.3f} → {status}"
        )


if __name__ == "__main__":
    app()
