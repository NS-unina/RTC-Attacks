#!/usr/bin/env python3
"""Pre-experiment parallel capture check.

For each scenario, runs N parallel instances and verifies that:
  - Suricata captured a non-empty PCAP
  - the expected IDS alerts are present within the attack windows

Use before Experiment 2 to confirm the stack handles parallel load correctly.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
import sys
from pathlib import Path
import time
from typing import Any, Dict, List

import typer

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments import config as cfg
from experiments.core.scenario import EXPECTED_SIDS as EXPECTED_ALERT_SIDS_BY_SCENARIO, parse_scenario_list
from experiments.core.timing import utc_now_iso
from experiments.infra.capture import CaptureStore
from experiments.infra.ids import IdsController
from experiments.infra.scenario_runner import ScenarioRunnerAdapter
from experiments.infra.shell import StepResult, run_cmd, write_cli_log
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


@dataclass
class ScenarioCaptureResult:
    scenario_id: int
    run_started_utc: str
    run_finished_utc: str
    runner_exit_code: int
    runner_summary_path: str
    capture_root: str
    pcap_file_count: int
    pcap_total_bytes: int
    pcap_total_packets: int
    expected_alert_sids: List[int]
    alert_file: str
    alert_total_count: int
    alert_expected_sid_count: int
    alert_windows_total: int
    alert_windows_hit: int
    alert_ok: bool
    alert_error: str
    capture_ok: bool
    run_ok: bool
    overall_ok: bool


def _parse_utc(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)


def _count_packets_with_ids_image(repo_root: Path, pcap_file: Path, ids_runtime_image: str) -> int:
    relative_pcap = pcap_file.resolve().relative_to(repo_root.resolve())

    cmd = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{repo_root}:/work",
        ids_runtime_image,
        "sh",
        "-lc",
        f"tcpdump -r /work/{relative_pcap} 2>/dev/null | wc -l",
    ]
    proc = run_cmd(cmd=cmd, cwd=repo_root, check=False)
    if proc.returncode != 0:
        return 0

    output = proc.stdout.strip()
    if not output:
        return 0

    try:
        return int(output)
    except ValueError:
        return 0


def _pcap_metrics(capture_root: Path, repo_root: Path, ids_runtime_image: str) -> tuple[int, int, int]:
    pcap_dir = capture_root / "pcap"
    pcap_files = sorted(pcap_dir.glob("*.pcap")) if pcap_dir.exists() else []

    total_bytes = sum(path.stat().st_size for path in pcap_files)
    total_packets = sum(
        _count_packets_with_ids_image(
            repo_root=repo_root,
            pcap_file=path,
            ids_runtime_image=ids_runtime_image,
        )
        for path in pcap_files
    )

    return len(pcap_files), total_bytes, total_packets

def _run_scenario_parallel(
    repo_root: Path,
    scenario_id: int,
    max_instances: int,
    runner_outputs_root: Path,
) -> tuple[int, Path]:
    scenario_output_dir = runner_outputs_root / f"scenario_{scenario_id}"
    proc, summary = run_scenario_runner_spike(
        repo_root=repo_root,
        scenario_id=scenario_id,
        max_instances=max_instances,
        output_dir=scenario_output_dir,
    )
    write_cli_log(scenario_output_dir / "last_cli_output.log", proc)

    return proc.returncode, summary


def _build_alerts_from_capture(repo_root: Path, pcap_input: Path, alert_output: Path) -> None:
    proc = build_alerts_from_capture(repo_root=repo_root, pcap_input=pcap_input, alert_output=alert_output)
    if proc.returncode != 0:
        raise RuntimeError(
            "build-alerts failed:\n"
            f"STDOUT:\n{proc.stdout}\n\nSTDERR:\n{proc.stderr}"
        )


def _load_alert_records(alert_file: Path) -> List[Dict[str, Any]]:
    if not alert_file.exists():
        return []

    rows: List[Dict[str, Any]] = []
    for raw_line in alert_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue

        ts = payload.get("timestamp") or payload.get("time")
        sid = payload.get("sid")
        if ts is None:
            continue
        try:
            sid_int = int(sid) if sid is not None else None
        except (TypeError, ValueError):
            sid_int = None
        rows.append(
            {
                "timestamp": _parse_utc(str(ts)),
                "sid": sid_int,
            }
        )
    return rows


def _load_attack_windows_from_runner_summary(summary_path: Path) -> List[tuple[datetime, datetime]]:
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    results = payload.get("results", [])
    windows: List[tuple[datetime, datetime]] = []
    for item in results:
        start_utc = item.get("start_utc")
        end_utc = item.get("end_utc")
        if not start_utc or not end_utc:
            continue
        windows.append((_parse_utc(start_utc), _parse_utc(end_utc)))
    return windows


def _evaluate_alert_windows(
    alert_rows: List[Dict[str, Any]],
    windows: List[tuple[datetime, datetime]],
    expected_sids: List[int],
    post_window_sec: float,
) -> tuple[int, int, int]:
    expected_sid_set = set(expected_sids)
    alerts_matching_sid = [row for row in alert_rows if row["sid"] in expected_sid_set]
    hit_windows = 0

    for start_ts, end_ts in windows:
        window_end = end_ts + timedelta(seconds=post_window_sec)
        found = any(
            (start_ts <= row["timestamp"] <= window_end)
            for row in alerts_matching_sid
        )
        if found:
            hit_windows += 1

    return len(alert_rows), len(alerts_matching_sid), hit_windows


def run_parallel_capture_test(
    repo_root: Path,
    scenarios: List[int],
    max_instances: int,
    output_json: Path,
    ids_runtime_image: str,
    alert_window_post_sec: float,
) -> None:
    results: List[ScenarioCaptureResult] = []
    runner_outputs_root = repo_root / "experiments" / "results" / "capture_parallel" / "runner_outputs"
    runner_outputs_root.mkdir(parents=True, exist_ok=True)

    for scenario_id in scenarios:
        run_started = utc_now_iso()
        runner_exit_code = 1
        runner_summary_path = ""
        capture_root_path = ""
        pcap_file_count = 0
        pcap_total_bytes = 0
        pcap_total_packets = 0
        alert_file_path = ""
        alert_total_count = 0
        alert_expected_sid_count = 0
        alert_windows_total = 0
        alert_windows_hit = 0
        alert_ok = False
        alert_error = ""
        expected_alert_sids = EXPECTED_ALERT_SIDS_BY_SCENARIO.get(scenario_id, [])

        try:
            start_ids(repo_root)
            time.sleep(2)

            runner_exit_code, summary_path = _run_scenario_parallel(
                repo_root=repo_root,
                scenario_id=scenario_id,
                max_instances=max_instances,
                runner_outputs_root=runner_outputs_root,
            )
            runner_summary_path = str(summary_path)

        finally:
            time.sleep(2)
            stop_ids(repo_root)
            time.sleep(1)

        capture_root = load_capture_root(repo_root)
        capture_root_path = str(capture_root)
        pcap_file_count, pcap_total_bytes, pcap_total_packets = _pcap_metrics(
            capture_root=capture_root,
            repo_root=repo_root,
            ids_runtime_image=ids_runtime_image,
        )

        run_ok = runner_exit_code == 0
        capture_ok = pcap_file_count > 0 and pcap_total_packets > 0
        if run_ok and capture_ok and expected_alert_sids:
            scenario_alert_dir = repo_root / "experiments" / "results" / "capture_parallel" / "alerts"
            scenario_alert_dir.mkdir(parents=True, exist_ok=True)
            alert_file = scenario_alert_dir / f"scenario_{scenario_id}_alerts.jsonl"
            alert_file_path = str(alert_file)
            try:
                _build_alerts_from_capture(
                    repo_root=repo_root,
                    pcap_input=capture_root / "pcap",
                    alert_output=alert_file,
                )
                alert_rows = _load_alert_records(alert_file)
                windows = _load_attack_windows_from_runner_summary(Path(runner_summary_path))
                alert_windows_total = len(windows)
                (
                    alert_total_count,
                    alert_expected_sid_count,
                    alert_windows_hit,
                ) = _evaluate_alert_windows(
                    alert_rows=alert_rows,
                    windows=windows,
                    expected_sids=expected_alert_sids,
                    post_window_sec=alert_window_post_sec,
                )
                alert_ok = alert_windows_total > 0 and alert_windows_hit == alert_windows_total
            except Exception as exc:  # noqa: BLE001
                alert_error = str(exc)
                alert_ok = False

        result = ScenarioCaptureResult(
            scenario_id=scenario_id,
            run_started_utc=run_started,
            run_finished_utc=utc_now_iso(),
            runner_exit_code=runner_exit_code,
            runner_summary_path=runner_summary_path,
            capture_root=capture_root_path,
            pcap_file_count=pcap_file_count,
            pcap_total_bytes=pcap_total_bytes,
            pcap_total_packets=pcap_total_packets,
            expected_alert_sids=expected_alert_sids,
            alert_file=alert_file_path,
            alert_total_count=alert_total_count,
            alert_expected_sid_count=alert_expected_sid_count,
            alert_windows_total=alert_windows_total,
            alert_windows_hit=alert_windows_hit,
            alert_ok=alert_ok,
            alert_error=alert_error,
            capture_ok=capture_ok,
            run_ok=run_ok,
            overall_ok=run_ok and capture_ok and (alert_ok if expected_alert_sids else True),
        )
        results.append(result)

    payload = {
        "generated_at_utc": utc_now_iso(),
        "max_instances": max_instances,
        "ids_runtime_image": ids_runtime_image,
        "scenarios": scenarios,
        "results": [asdict(item) for item in results],
        "summary": {
            "total": len(results),
            "run_ok": sum(1 for item in results if item.run_ok),
            "capture_ok": sum(1 for item in results if item.capture_ok),
            "alert_ok": sum(1 for item in results if item.alert_ok),
            "overall_ok": sum(1 for item in results if item.overall_ok),
        },
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(json.dumps(payload["summary"], indent=2))
    print(f"Report: {output_json}")


app = typer.Typer()


@app.command()
def main(
    scenarios: str = typer.Option(cfg.get("experiment1_baseline.default_scenarios"), help="Comma-separated scenario IDs"),
    max_instances: int = typer.Option(2, help="Parallel instances per scenario"),
    output: str = typer.Option(None, help="Output report JSON path (auto-generated if omitted)"),
    ids_runtime_image: str = typer.Option(cfg.get("paths.suricata_image"), help="Runtime image for offline packet counting tools"),
    alert_window_post_sec: float = typer.Option(cfg.get("timing.alert_window_post_sec"), help="Post-attack time tolerance window in seconds"),
) -> None:
    """Validate packet capture with parallel scenario instances."""
    repo_root = REPO_ROOT
    scenario_list = parse_scenario_list(scenarios)
    
    if max_instances < 1:
        raise ValueError("--max-instances must be >= 1")

    output_json = (
        Path(output).expanduser().resolve()
        if output
        else repo_root / "experiments" / "results" / "capture_parallel" / f"run_{datetime.now().astimezone().strftime('%Y%m%d_%H%M%S')}.json"
    )

    run_parallel_capture_test(
        repo_root=repo_root,
        scenarios=scenario_list,
        max_instances=max_instances,
        output_json=output_json,
        ids_runtime_image=ids_runtime_image,
        alert_window_post_sec=alert_window_post_sec,
    )


if __name__ == "__main__":
    app()
