from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Optional

import typer
from rich.console import Console

from .discovery import discover_scenarios
from .executor import execute_plan
from .ipc import IpcEventServer
from .models import RunConfig, Strategy
from .planner import build_plan
from .reporting import write_reports
from .stopper import stop_scenarios
from .utils import ensure_dir, log_flow, utc_now_tag

app = typer.Typer(help="Scenario runner for RTC-Attacks auto-attack orchestration")
console = Console()


@app.callback(invoke_without_command=True)
def root(
    ctx: typer.Context,
    stop_all: bool = typer.Option(
        False,
        "--stop-all",
        help="Stop all discovered scenarios and exit",
    ),
) -> None:
    # Change rationale: support a direct global shutdown flag without requiring a subcommand.
    if stop_all:
        if ctx.invoked_subcommand is not None:
            raise typer.BadParameter("--stop-all cannot be combined with a subcommand")
        stop(scenario=None, labs_dir="./public/labs")
        raise typer.Exit(code=0)

    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())
        raise typer.Exit(code=0)


@app.command("list-scenarios")
def list_scenarios(
    labs_dir: str = typer.Option("./public/labs", "--labs-dir", help="Path to labs root directory"),
) -> None:
    labs_path = Path(labs_dir).expanduser().resolve()
    scenario_catalog = discover_scenarios(labs_path)
    if not scenario_catalog:
        raise typer.BadParameter(f"No scenarios discovered in {labs_path}")

    for scenario_id in sorted(scenario_catalog.keys()):
        scenario_spec = scenario_catalog[scenario_id]
        console.print(f"{scenario_id}: {scenario_spec.lab_path}")


@app.command("run")
def run(
    strategy: Strategy = typer.Option(..., "--strategy", help="Execution strategy: staggered or spike"),
    scenario: int = typer.Option(..., "--scenario", help="Scenario id to execute"),
    max_instances: int = typer.Option(8, "--max-instances", min=1, help="Number of instances to launch"),
    interval_sec: float = typer.Option(
        30.0,
        "--interval-sec",
        min=0.1,
        help="Interval between launches for staggered runs",
    ),
    labs_dir: str = typer.Option("./public/labs", "--labs-dir", help="Path to labs root directory"),
    output_dir: str = typer.Option("./runner-results", "--output-dir", help="Output directory for reports and logs"),
) -> None:
    started_perf = perf_counter()

    labs_path = Path(labs_dir).expanduser().resolve()
    out_root = ensure_dir(Path(output_dir).expanduser().resolve())
    run_id = utc_now_tag()
    run_dir = ensure_dir(out_root / f"run_{run_id}")
    run_logs_dir = ensure_dir(run_dir / "logs")
    # Use /tmp for the socket to avoid AF_UNIX path length limit (108 bytes on Linux).
    ipc_socket = Path(f"/tmp/rtc_{run_id}.sock")
    ipc_events_path = run_dir / "ipc_events.jsonl"
    ipc_client = Path(__file__).with_name("ipc_client.py").resolve()

    config = RunConfig(
        strategy=strategy,
        scenario=scenario,
        max_instances=max_instances,
        interval_sec=interval_sec,
        labs_dir=labs_path,
        output_dir=run_dir,
    )

    scenario_catalog = discover_scenarios(labs_path)
    if not scenario_catalog:
        raise typer.BadParameter(f"No scenarios discovered in {labs_path}")

    if config.scenario not in scenario_catalog:
        raise typer.BadParameter(
            f"Unknown scenario id: {config.scenario}. Available ids: {sorted(scenario_catalog.keys())}"
        )

    planned_runs = build_plan(config)

    log_flow(
        "Run starting strategy=%s scenario=%s max_instances=%s run_dir=%s"
        % (config.strategy.value, config.scenario, config.max_instances, run_dir)
    )
    for planned_run in planned_runs:
        log_flow(
            "Plan launch=%s offset=%.2fs instance=%s scenario=%s"
            % (
                planned_run.launch_index,
                planned_run.launch_offset_sec,
                planned_run.instance,
                planned_run.scenario_id,
            )
        )

    with IpcEventServer(ipc_socket, ipc_events_path) as ipc_server:
        results = execute_plan(
            config=config,
            planned_runs=planned_runs,
            scenario_catalog=scenario_catalog,
            run_logs_dir=run_logs_dir,
            ipc_env={
                "RTC_IPC_SOCKET": str(ipc_socket),
                "RTC_EVENT": f"python3 {ipc_client}",
            },
        )
        ipc_events = ipc_server.load_events()

    report_json = run_dir / "summary.json"
    report_csv = run_dir / "summary.csv"
    summary = write_reports(
        config=config,
        results=results,
        report_json=report_json,
        report_csv=report_csv,
        started_perf=started_perf,
        ipc_events=ipc_events,
    )

    if summary.failed_runs > 0:
        console.print(
            "[yellow]Completed with failures:[/yellow] "
            f"{summary.success_runs}/{summary.total_runs} succeeded"
        )
    else:
        console.print(f"[green]Completed:[/green] {summary.success_runs}/{summary.total_runs} succeeded")

    console.print(f"Report JSON: {summary.report_json}")
    console.print(f"Report CSV:  {summary.report_csv}")
    console.print(f"Total duration: {summary.duration_sec:.2f}s")


@app.command("stop")
def stop(
    scenario: Optional[int] = typer.Option(None, "--scenario", help="Scenario id to stop; when omitted, stop all scenarios"),
    labs_dir: str = typer.Option("./public/labs", "--labs-dir", help="Path to labs root directory"),
) -> None:
    # Change rationale: provide an explicit CLI teardown path for all scenarios or one selected scenario.
    labs_path = Path(labs_dir).expanduser().resolve()
    scenario_catalog = discover_scenarios(labs_path)
    if not scenario_catalog:
        raise typer.BadParameter(f"No scenarios discovered in {labs_path}")

    if scenario is not None and scenario not in scenario_catalog:
        raise typer.BadParameter(
            f"Unknown scenario id: {scenario}. Available ids: {sorted(scenario_catalog.keys())}"
        )

    if scenario is None:
        selected_specs = list(scenario_catalog.values())
        selected_label = "all"
    else:
        selected_specs = [scenario_catalog[scenario]]
        selected_label = str(scenario)

    seen_labs: set[Path] = set()
    unique_specs = []
    for scenario_spec in selected_specs:
        if scenario_spec.lab_path in seen_labs:
            continue
        seen_labs.add(scenario_spec.lab_path)
        unique_specs.append(scenario_spec)

    log_flow("Stop requested scenario=%s labs=%s" % (selected_label, len(unique_specs)))
    stop_results = stop_scenarios(unique_specs)

    failed_results = [result for result in stop_results if result.exit_code != 0]

    for result in stop_results:
        status = "OK" if result.exit_code == 0 else "FAIL"
        console.print(
            f"[{status}] scenario={result.scenario_id} instance={result.instance} "
            f"lab={result.lab_path} exit={result.exit_code}"
        )

    if failed_results:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
