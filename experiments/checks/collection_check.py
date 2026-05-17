#!/usr/bin/env python3
"""Pre-experiment collection check.

Sanity-tests the full monitoring pipeline before a real experiment run:
  - scenario-runner executes and produces a summary
  - attack-window markers (BEGIN/END) are present in the runner logs
  - Suricata captures a non-empty PCAP
  - the offline alert pipeline produces alerts
  - alert/event alignment validation succeeds

Run this once per new machine setup to confirm the environment is working.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import sys
from pathlib import Path
import time
from typing import Dict, List

import typer

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments import config as cfg
from experiments.core.scenario import EXPECTED_SIDS as EXPECTED_ALERT_SIDS_BY_SCENARIO, parse_scenario_list
from experiments.core.timing import utc_tag
from experiments.infra.capture import CaptureStore
from experiments.infra.ids import IdsController
from experiments.infra.scenario_runner import ScenarioRunnerAdapter
from experiments.infra.shell import StepResult, write_cli_log
from experiments.pipeline import ids_dataset_pipeline as ids_pipeline


# ---------------------------------------------------------------------------
# Adapter functions — keep the logic body below unchanged
# ---------------------------------------------------------------------------

def start_ids(repo_root: Path) -> None:
    IdsController(repo_root).start()


def stop_ids(repo_root: Path) -> None:
    IdsController(repo_root).stop()


def load_capture_root(repo_root: Path) -> Path:
    return CaptureStore(repo_root).latest_capture_root()


def latest_runner_summary(base_dir: Path) -> Path:
    candidates = sorted(base_dir.glob("run_*/summary.json"))
    if not candidates:
        raise FileNotFoundError(f"No scenario-runner summary found under: {base_dir}")
    return candidates[-1]


def run_scenario_runner_spike(
    repo_root: Path,
    scenario_id: int,
    max_instances: int,
    output_dir: Path,
) -> tuple:
    return ScenarioRunnerAdapter(repo_root).run_spike(
        scenario_id=scenario_id,
        max_instances=max_instances,
        output_dir=output_dir,
    )


def build_alerts_from_capture(repo_root: Path, pcap_input: Path, alert_output: Path) -> StepResult:
    try:
        ids_pipeline.build_suricata_alerts_from_pcap(
            pcap_input=pcap_input,
            output_alert_file=alert_output,
            project_root=repo_root,
            suricata_image="suricata-rtc",
            suricata_rules="/etc/suricata/local.rules",
        )
        return StepResult(returncode=0, stdout="ok", stderr="")
    except Exception as exc:  # noqa: BLE001
        return StepResult(returncode=1, stdout="", stderr=str(exc))


def validate_alerts_against_runner(
    repo_root: Path,
    alerts_path: Path,
    runner_summary_path: Path,
    output_path: Path,
    window_post_sec: float,
    timeline_bin_sec: float,
) -> StepResult:
    try:
        ids_pipeline.build_alert_validation_report(
            alert_file=alerts_path,
            output_file=output_path,
            runner_summary_file=runner_summary_path,
            window_pre_sec=0.0,
            window_post_sec=window_post_sec,
            timeline_bin_sec=timeline_bin_sec,
        )
        return StepResult(returncode=0, stdout="ok", stderr="")
    except Exception as exc:  # noqa: BLE001
        return StepResult(returncode=1, stdout="", stderr=str(exc))


@dataclass
class ScenarioCollectionResult:
    scenario_id: int
    runner_exit_code: int
    runner_summary_path: str
    attack_markers_begin: int
    attack_markers_end: int
    capture_root: str
    pcap_file_count: int
    pcap_total_bytes: int
    alerts_file: str
    alerts_total: int
    alerts_expected_sid_count: int
    expected_sids: List[int]
    validation_report_file: str
    validation_events_total: int
    validation_detected_events: int
    collection_ok: bool
    detection_signal_present: bool
    error: str


def _count_markers_in_file(log_path: Path) -> tuple[int, int]:
    """Count RTC_ATTACK_WINDOW markers in log file."""
    if not log_path.exists():
        return 0, 0
    
    # Simplified with list comprehension and sum
    lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    return (
        sum(1 for line in lines if "RTC_ATTACK_WINDOW_BEGIN" in line),
        sum(1 for line in lines if "RTC_ATTACK_WINDOW_END" in line),
    )


def _count_markers_from_summary(summary_path: Path) -> tuple[int, int]:
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    results = payload.get("results", [])
    begin_total = 0
    end_total = 0

    for item in results:
        log_path_raw = item.get("log_path")
        if not log_path_raw:
            continue
        begin_count, end_count = _count_markers_in_file(Path(str(log_path_raw)))
        begin_total += begin_count
        end_total += end_count

    return begin_total, end_total


def _pcap_metrics(capture_root: Path) -> tuple[int, int]:
    pcap_dir = capture_root / "pcap"
    pcap_files = sorted(pcap_dir.glob("*.pcap")) if pcap_dir.exists() else []

    total_bytes = sum(path.stat().st_size for path in pcap_files)
    return len(pcap_files), total_bytes


def _load_alert_rows(alerts_file: Path) -> List[dict]:
    """Load alert records from JSONL file."""
    if not alerts_file.exists():
        return []
    
    # Simplified with list comprehension
    return [
        json.loads(line)
        for line in alerts_file.read_text(encoding="utf-8", errors="ignore").splitlines()
        if line.strip() and line.strip().startswith("{")
    ]


def _validate_one_scenario(
    repo_root: Path,
    scenario_id: int,
    output_root: Path,
    alert_window_post_sec: float,
    timeline_bin_sec: float,
    max_instances: int,
) -> ScenarioCollectionResult:
    scenario_dir = output_root / f"scenario_{scenario_id}"
    scenario_dir.mkdir(parents=True, exist_ok=True)

    runner_dir = scenario_dir / "runner"
    alerts_file = scenario_dir / "alerts.jsonl"
    validation_file = scenario_dir / "alert_validation.json"

    summary_path = Path()
    capture_root = Path()

    try:
        start_ids(repo_root)
        time.sleep(2)

        run_proc, summary_path = run_scenario_runner_spike(
            repo_root=repo_root,
            scenario_id=scenario_id,
            max_instances=max_instances,
            output_dir=runner_dir,
        )
        write_cli_log(scenario_dir / "scenario_runner_cli.log", run_proc)

    finally:
        time.sleep(2)
        stop_ids(repo_root)
        time.sleep(1)

    capture_root = load_capture_root(repo_root)
    pcap_count, pcap_total_bytes = _pcap_metrics(capture_root)

    build_alerts = build_alerts_from_capture(
        repo_root=repo_root,
        pcap_input=capture_root / "pcap",
        alert_output=alerts_file,
    )

    if build_alerts.returncode != 0:
        return ScenarioCollectionResult(
            scenario_id=scenario_id,
            runner_exit_code=run_proc.returncode,
            runner_summary_path=str(summary_path),
            attack_markers_begin=0,
            attack_markers_end=0,
            capture_root=str(capture_root),
            pcap_file_count=pcap_count,
            pcap_total_bytes=pcap_total_bytes,
            alerts_file=str(alerts_file),
            alerts_total=0,
            alerts_expected_sid_count=0,
            expected_sids=EXPECTED_ALERT_SIDS_BY_SCENARIO[scenario_id],
            validation_report_file=str(validation_file),
            validation_events_total=0,
            validation_detected_events=0,
            collection_ok=False,
            detection_signal_present=False,
            error="build-alerts failed",
        )

    validate_proc = validate_alerts_against_runner(
        repo_root=repo_root,
        alerts_path=alerts_file,
        runner_summary_path=summary_path,
        output_path=validation_file,
        window_post_sec=alert_window_post_sec,
        timeline_bin_sec=timeline_bin_sec,
    )

    if validate_proc.returncode != 0:
        return ScenarioCollectionResult(
            scenario_id=scenario_id,
            runner_exit_code=run_proc.returncode,
            runner_summary_path=str(summary_path),
            attack_markers_begin=0,
            attack_markers_end=0,
            capture_root=str(capture_root),
            pcap_file_count=pcap_count,
            pcap_total_bytes=pcap_total_bytes,
            alerts_file=str(alerts_file),
            alerts_total=0,
            alerts_expected_sid_count=0,
            expected_sids=EXPECTED_ALERT_SIDS_BY_SCENARIO[scenario_id],
            validation_report_file=str(validation_file),
            validation_events_total=0,
            validation_detected_events=0,
            collection_ok=False,
            detection_signal_present=False,
            error="validate-alerts failed",
        )

    begin_markers, end_markers = _count_markers_from_summary(summary_path)

    alert_rows = _load_alert_rows(alerts_file)
    expected_sids = EXPECTED_ALERT_SIDS_BY_SCENARIO[scenario_id]
    expected_sid_count = 0
    expected_sid_set = set(expected_sids)
    for row in alert_rows:
        sid_raw = row.get("sid")
        try:
            sid = int(sid_raw) if sid_raw is not None else None
        except (TypeError, ValueError):
            sid = None
        if sid in expected_sid_set:
            expected_sid_count += 1

    validation_payload = json.loads(validation_file.read_text(encoding="utf-8"))
    events_total = int(validation_payload.get("event_metrics", {}).get("total_events", 0))
    detected_events = int(validation_payload.get("event_metrics", {}).get("detected_events", 0))

    collection_ok = all(
        [
            run_proc.returncode == 0,
            summary_path.exists(),
            begin_markers > 0,
            end_markers > 0,
            pcap_count > 0,
            pcap_total_bytes > 0,
            alerts_file.exists(),
            validation_file.exists(),
            events_total > 0,
        ]
    )

    return ScenarioCollectionResult(
        scenario_id=scenario_id,
        runner_exit_code=run_proc.returncode,
        runner_summary_path=str(summary_path),
        attack_markers_begin=begin_markers,
        attack_markers_end=end_markers,
        capture_root=str(capture_root),
        pcap_file_count=pcap_count,
        pcap_total_bytes=pcap_total_bytes,
        alerts_file=str(alerts_file),
        alerts_total=len(alert_rows),
        alerts_expected_sid_count=expected_sid_count,
        expected_sids=expected_sids,
        validation_report_file=str(validation_file),
        validation_events_total=events_total,
        validation_detected_events=detected_events,
        collection_ok=collection_ok,
        detection_signal_present=(expected_sid_count > 0),
        error="",
    )


def run_validation(
    repo_root: Path,
    scenarios: List[int],
    output_dir: Path,
    alert_window_post_sec: float,
    timeline_bin_sec: float,
    max_instances: int,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    results: List[ScenarioCollectionResult] = []
    for scenario_id in scenarios:
        started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        print(f"[monitoring-validation] scenario={scenario_id} started_at={started}", flush=True)
        result = _validate_one_scenario(
            repo_root=repo_root,
            scenario_id=scenario_id,
            output_root=output_dir,
            alert_window_post_sec=alert_window_post_sec,
            timeline_bin_sec=timeline_bin_sec,
            max_instances=max_instances,
        )
        finished = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        print(
            (
                f"[monitoring-validation] scenario={scenario_id} "
                f"collection_ok={result.collection_ok} "
                f"detection_signal_present={result.detection_signal_present} "
                f"finished_at={finished}"
            ),
            flush=True,
        )
        results.append(result)

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo_root": str(repo_root),
        "scenarios": scenarios,
        "results": [asdict(item) for item in results],
        "aggregate": {
            "total": len(results),
            "collection_ok": sum(1 for item in results if item.collection_ok),
            "detection_signal_present": sum(1 for item in results if item.detection_signal_present),
            "failed": sum(1 for item in results if not item.collection_ok),
        },
    }

    out_file = output_dir / "collection_validation_report.json"
    out_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"[monitoring-validation] report={out_file}", flush=True)


def _run_scenario_runner_only(
    repo_root: Path,
    scenario_id: int,
    output_root: Path,
    max_instances: int,
) -> tuple[int, Path, str]:
    scenario_dir = output_root / f"scenario_{scenario_id}"
    scenario_dir.mkdir(parents=True, exist_ok=True)
    runner_dir = scenario_dir / "runner"

    run_proc, summary_path = run_scenario_runner_spike(
        repo_root=repo_root,
        scenario_id=scenario_id,
        max_instances=max_instances,
        output_dir=runner_dir,
    )
    write_cli_log(scenario_dir / "scenario_runner_cli.log", run_proc)

    try:
        summary_path = latest_runner_summary(runner_dir)
        summary_error = ""
    except Exception as exc:
        summary_path = Path()
        summary_error = str(exc)

    return run_proc.returncode, summary_path, summary_error


def _finalize_scenario_result(
    repo_root: Path,
    output_root: Path,
    scenario_id: int,
    run_exit_code: int,
    summary_path: Path,
    summary_error: str,
    capture_root: Path,
    alert_window_post_sec: float,
    timeline_bin_sec: float,
) -> ScenarioCollectionResult:
    scenario_dir = output_root / f"scenario_{scenario_id}"
    scenario_dir.mkdir(parents=True, exist_ok=True)

    alerts_file = scenario_dir / "alerts.jsonl"
    validation_file = scenario_dir / "alert_validation.json"

    pcap_count, pcap_total_bytes = _pcap_metrics(capture_root)

    if not summary_path.exists():
        return ScenarioCollectionResult(
            scenario_id=scenario_id,
            runner_exit_code=run_exit_code,
            runner_summary_path=str(summary_path),
            attack_markers_begin=0,
            attack_markers_end=0,
            capture_root=str(capture_root),
            pcap_file_count=pcap_count,
            pcap_total_bytes=pcap_total_bytes,
            alerts_file=str(alerts_file),
            alerts_total=0,
            alerts_expected_sid_count=0,
            expected_sids=EXPECTED_ALERT_SIDS_BY_SCENARIO[scenario_id],
            validation_report_file=str(validation_file),
            validation_events_total=0,
            validation_detected_events=0,
            collection_ok=False,
            detection_signal_present=False,
            error=f"runner summary unavailable: {summary_error}",
        )

    build_alerts = build_alerts_from_capture(
        repo_root=repo_root,
        pcap_input=capture_root / "pcap",
        alert_output=alerts_file,
    )

    if build_alerts.returncode != 0:
        return ScenarioCollectionResult(
            scenario_id=scenario_id,
            runner_exit_code=run_exit_code,
            runner_summary_path=str(summary_path),
            attack_markers_begin=0,
            attack_markers_end=0,
            capture_root=str(capture_root),
            pcap_file_count=pcap_count,
            pcap_total_bytes=pcap_total_bytes,
            alerts_file=str(alerts_file),
            alerts_total=0,
            alerts_expected_sid_count=0,
            expected_sids=EXPECTED_ALERT_SIDS_BY_SCENARIO[scenario_id],
            validation_report_file=str(validation_file),
            validation_events_total=0,
            validation_detected_events=0,
            collection_ok=False,
            detection_signal_present=False,
            error="build-alerts failed",
        )

    validate_proc = validate_alerts_against_runner(
        repo_root=repo_root,
        alerts_path=alerts_file,
        runner_summary_path=summary_path,
        output_path=validation_file,
        window_post_sec=alert_window_post_sec,
        timeline_bin_sec=timeline_bin_sec,
    )

    if validate_proc.returncode != 0:
        return ScenarioCollectionResult(
            scenario_id=scenario_id,
            runner_exit_code=run_exit_code,
            runner_summary_path=str(summary_path),
            attack_markers_begin=0,
            attack_markers_end=0,
            capture_root=str(capture_root),
            pcap_file_count=pcap_count,
            pcap_total_bytes=pcap_total_bytes,
            alerts_file=str(alerts_file),
            alerts_total=0,
            alerts_expected_sid_count=0,
            expected_sids=EXPECTED_ALERT_SIDS_BY_SCENARIO[scenario_id],
            validation_report_file=str(validation_file),
            validation_events_total=0,
            validation_detected_events=0,
            collection_ok=False,
            detection_signal_present=False,
            error="validate-alerts failed",
        )

    begin_markers, end_markers = _count_markers_from_summary(summary_path)
    alert_rows = _load_alert_rows(alerts_file)
    expected_sids = EXPECTED_ALERT_SIDS_BY_SCENARIO[scenario_id]
    expected_sid_set = set(expected_sids)
    expected_sid_count = 0
    for row in alert_rows:
        sid_raw = row.get("sid")
        try:
            sid = int(sid_raw) if sid_raw is not None else None
        except (TypeError, ValueError):
            sid = None
        if sid in expected_sid_set:
            expected_sid_count += 1

    validation_payload = json.loads(validation_file.read_text(encoding="utf-8"))
    events_total = int(validation_payload.get("event_metrics", {}).get("total_events", 0))
    detected_events = int(validation_payload.get("event_metrics", {}).get("detected_events", 0))

    collection_ok = all(
        [
            run_exit_code == 0,
            summary_path.exists(),
            begin_markers > 0,
            end_markers > 0,
            pcap_count > 0,
            pcap_total_bytes > 0,
            alerts_file.exists(),
            validation_file.exists(),
            events_total > 0,
        ]
    )

    return ScenarioCollectionResult(
        scenario_id=scenario_id,
        runner_exit_code=run_exit_code,
        runner_summary_path=str(summary_path),
        attack_markers_begin=begin_markers,
        attack_markers_end=end_markers,
        capture_root=str(capture_root),
        pcap_file_count=pcap_count,
        pcap_total_bytes=pcap_total_bytes,
        alerts_file=str(alerts_file),
        alerts_total=len(alert_rows),
        alerts_expected_sid_count=expected_sid_count,
        expected_sids=expected_sids,
        validation_report_file=str(validation_file),
        validation_events_total=events_total,
        validation_detected_events=detected_events,
        collection_ok=collection_ok,
        detection_signal_present=(expected_sid_count > 0),
        error="",
    )


def run_validation_parallel(
    repo_root: Path,
    scenarios: List[int],
    output_dir: Path,
    alert_window_post_sec: float,
    timeline_bin_sec: float,
    max_instances: int,
    parallel_workers: int,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    start_ids(repo_root)

    runner_results: Dict[int, tuple[int, Path, str]] = {}

    try:
        time.sleep(2)
        with ThreadPoolExecutor(max_workers=max(1, parallel_workers)) as executor:
            futures = {
                executor.submit(
                    _run_scenario_runner_only,
                    repo_root,
                    scenario_id,
                    output_dir,
                    max_instances,
                ): scenario_id
                for scenario_id in scenarios
            }

            for future in as_completed(futures):
                scenario_id = futures[future]
                try:
                    runner_results[scenario_id] = future.result()
                except Exception as exc:
                    runner_results[scenario_id] = (1, Path(), str(exc))
    finally:
        time.sleep(2)
        stop_ids(repo_root)
        time.sleep(1)

    capture_root = load_capture_root(repo_root)

    results: List[ScenarioCollectionResult] = []
    for scenario_id in scenarios:
        run_exit_code, summary_path, summary_error = runner_results.get(scenario_id, (1, Path(), "missing runner result"))
        result = _finalize_scenario_result(
            repo_root=repo_root,
            output_root=output_dir,
            scenario_id=scenario_id,
            run_exit_code=run_exit_code,
            summary_path=summary_path,
            summary_error=summary_error,
            capture_root=capture_root,
            alert_window_post_sec=alert_window_post_sec,
            timeline_bin_sec=timeline_bin_sec,
        )
        results.append(result)

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo_root": str(repo_root),
        "mode": "parallel",
        "scenarios": scenarios,
        "shared_capture_root": str(capture_root),
        "results": [asdict(item) for item in results],
        "aggregate": {
            "total": len(results),
            "collection_ok": sum(1 for item in results if item.collection_ok),
            "detection_signal_present": sum(1 for item in results if item.detection_signal_present),
            "failed": sum(1 for item in results if not item.collection_ok),
        },
    }

    out_file = output_dir / "collection_validation_report.json"
    out_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"[monitoring-validation] report={out_file}", flush=True)


def run_validation_dispatch(
    repo_root: Path,
    scenarios: List[int],
    output_dir: Path,
    alert_window_post_sec: float,
    timeline_bin_sec: float,
    max_instances: int,
    mode: str,
    parallel_workers: int,
) -> None:
    if mode == "parallel":
        run_validation_parallel(
            repo_root=repo_root,
            scenarios=scenarios,
            output_dir=output_dir,
            alert_window_post_sec=alert_window_post_sec,
            timeline_bin_sec=timeline_bin_sec,
            max_instances=max_instances,
            parallel_workers=parallel_workers,
        )
        return

    run_validation(
        repo_root=repo_root,
        scenarios=scenarios,
        output_dir=output_dir,
        alert_window_post_sec=alert_window_post_sec,
        timeline_bin_sec=timeline_bin_sec,
        max_instances=max_instances,
    )


app = typer.Typer()


@app.command()
def main(
    repo_root: Path = typer.Option(REPO_ROOT, help="Repository root path"),
    scenarios: str = typer.Option(cfg.get("experiment1_baseline.default_scenarios"), help="Comma-separated scenario list"),
    mode: str = typer.Option("sequential", help="Execution mode: sequential or parallel"),
    parallel_workers: int = typer.Option(cfg.get("collection_check.parallel_workers"), help="Max workers for parallel mode"),
    max_instances: int = typer.Option(cfg.get("collection_check.max_instances"), help="Scenario-runner max instances per scenario"),
    output_dir: str = typer.Option(None, help="Output directory (auto-generated if omitted)"),
    alert_window_post_sec: float = typer.Option(cfg.get("timing.alert_window_post_sec"), help="Post event window for validate-alerts"),
    timeline_bin_sec: float = typer.Option(cfg.get("timing.timeline_bin_sec"), help="Timeline bin size for validate-alerts"),
) -> None:
    """Monitoring data-collection validation."""
    root = repo_root.expanduser().resolve()
    scenario_list = parse_scenario_list(scenarios)

    out_dir = (
        Path(output_dir).expanduser().resolve()
        if output_dir
        else root / "experiments" / "results" / "collection_validation" / f"run_{utc_tag()}"
    )

    run_validation_dispatch(
        repo_root=root,
        scenarios=scenario_list,
        output_dir=out_dir,
        alert_window_post_sec=alert_window_post_sec,
        timeline_bin_sec=timeline_bin_sec,
        max_instances=max_instances,
        mode=mode,
        parallel_workers=parallel_workers,
    )


if __name__ == "__main__":
    app()
