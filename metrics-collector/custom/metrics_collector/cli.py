from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from .collectors import collect_cpu_mem_metrics, collect_deployment_times, collect_network_metrics
from .discovery import discover_stacks
from .models import DiscoverOptions
from .utils import ensure_metrics_dir, log_flow, save_csv, save_json

app = typer.Typer(help="Generalized metrics collector for Docker and Compose projects")
console = Console()


def _now_tag() -> str:
    # Change rationale: output filenames should match host local execution time.
    return datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")


def _discover(project_folder: Path, recursive: bool, only_compose: bool, only_container: Optional[str]):
    options = DiscoverOptions(
        recursive=recursive,
        only_compose=only_compose,
        only_container=only_container,
    )
    return discover_stacks(project_folder, options)


def _validated_project_folder(raw_project_folder: str) -> Path:
    """
    Compatibility note:
    Previous implementation used Path-typed Typer options directly.
    In some Typer/Click combinations inside container runtime, those options were
    interpreted as boolean flags (no value accepted), causing:
    'Option --dir does not take a value'.
    """
    project_folder = Path(raw_project_folder).expanduser().resolve()
    if not project_folder.exists():
        raise typer.BadParameter(f"Project folder does not exist: {project_folder}")
    if not project_folder.is_dir():
        raise typer.BadParameter(f"Project folder is not a directory: {project_folder}")
    return project_folder


@app.command("deployment-times")
def deployment_times(
    # Previous implementation (kept for traceability):
    # project_folder: Path = typer.Option(..., "--dir", exists=True, file_okay=False, dir_okay=True),
    # Updated implementation:
    # Use string option + explicit validation to avoid Typer/Click runtime ambiguity in containerized execution.
    project_folder: str = typer.Option(..., "--dir", help="Absolute path of the project folder"),
    recursive: bool = typer.Option(False, "--recursive", help="Scan subfolders recursively"),
    only_compose: bool = typer.Option(False, "--only-compose", help="Use only compose-defined services"),
    only_container: Optional[str] = typer.Option(None, "--only-container", help="Collect only for one container/service"),
) -> None:
    log_flow(
        "CLI command started: deployment-times "
        f"(dir={project_folder}, recursive={recursive}, only_compose={only_compose}, only_container={only_container})"
    )
    project_folder_path = _validated_project_folder(project_folder)
    stacks = _discover(project_folder_path, recursive, only_compose, only_container)
    if not stacks:
        raise typer.BadParameter("No valid stack found with the selected options")
    log_flow(f"Discovered stacks: {', '.join(stack.name for stack in stacks)}")

    tag = _now_tag()
    for stack in stacks:
        console.print(f"[cyan]Collecting deployment metrics for stack:[/cyan] {stack.name}")
        results = collect_deployment_times(stack=stack, only_container=only_container)
        rows = [item.model_dump() for item in results]
        metrics_dir = ensure_metrics_dir(stack.path)
        console.print(f"Saving deployment timing metrics to {metrics_dir}")
        json_path = metrics_dir / f"deployment_times_{tag}.json"
        csv_path = metrics_dir / f"deployment_times_{tag}.csv"
        save_json(json_path, rows)
        save_csv(csv_path, rows)
        log_flow(f"Saved deployment metrics: json={json_path} csv={csv_path}")


@app.command("cpu-memory-utilization")
def cpu_memory_utilization(
    # Previous implementation (kept for traceability):
    # project_folder: Path = typer.Option(..., "--dir", exists=True, file_okay=False, dir_okay=True),
    # Updated implementation:
    # Use string option + explicit validation to avoid Typer/Click runtime ambiguity in containerized execution.
    project_folder: str = typer.Option(..., "--dir", help="Absolute path of the project folder"),
    recursive: bool = typer.Option(False, "--recursive", help="Scan subfolders recursively"),
    only_compose: bool = typer.Option(False, "--only-compose", help="Use only compose-defined services"),
    only_container: Optional[str] = typer.Option(None, "--only-container", help="Collect only for one container/service"),
    baseline_samples: int = typer.Option(10, "--baseline-samples", min=1),
    sample_interval_sec: float = typer.Option(1.0, "--sample-interval-sec", min=0.1),
) -> None:
    log_flow(
        "CLI command started: cpu-memory-utilization "
        f"(dir={project_folder}, recursive={recursive}, only_compose={only_compose}, "
        f"only_container={only_container}, baseline_samples={baseline_samples}, "
        f"sample_interval_sec={sample_interval_sec})"
    )
    project_folder_path = _validated_project_folder(project_folder)
    stacks = _discover(project_folder_path, recursive, only_compose, only_container)
    if not stacks:
        raise typer.BadParameter("No valid stack found with the selected options")
    log_flow(f"Discovered stacks: {', '.join(stack.name for stack in stacks)}")

    tag = _now_tag()
    for stack in stacks:
        console.print(f"[cyan]Collecting CPU and memory metrics for stack:[/cyan] {stack.name}")
        results = collect_cpu_mem_metrics(
            stack=stack,
            baseline_samples=baseline_samples,
            sample_interval_sec=sample_interval_sec,
        )
        if only_container:
            results = [item for item in results if item.container == only_container]
        rows = [item.model_dump() for item in results]
        metrics_dir = ensure_metrics_dir(stack.path)
        json_path = metrics_dir / f"cpu_memory_{tag}.json"
        csv_path = metrics_dir / f"cpu_memory_{tag}.csv"
        # Previous implementation (kept for traceability):
        # save_json(json_path, rows)
        #
        # Updated implementation:
        # Persist sampling metadata and per-sample series in the JSON envelope.
        save_json(
            json_path,
            {
                "stack": stack.name,
                "stack_path": str(stack.path),
                "sampling_interval_sec": sample_interval_sec,
                "baseline_samples": baseline_samples,
                "metrics": rows,
            },
        )
        save_csv(csv_path, rows)
        log_flow(f"Saved CPU/memory metrics: json={json_path} csv={csv_path}")


@app.command("network-latency-overhead")
def network_latency_overhead(
    # Previous implementation (kept for traceability):
    # project_folder: Path = typer.Option(..., "--dir", exists=True, file_okay=False, dir_okay=True),
    # Updated implementation:
    # Use string option + explicit validation to avoid Typer/Click runtime ambiguity in containerized execution.
    project_folder: str = typer.Option(..., "--dir", help="Absolute path of the project folder"),
    recursive: bool = typer.Option(False, "--recursive", help="Scan subfolders recursively"),
    only_compose: bool = typer.Option(False, "--only-compose", help="Use only compose-defined services"),
    only_container: Optional[str] = typer.Option(None, "--only-container", help="Collect only for one container/service"),
    sample_interval_sec: float = typer.Option(1.0, "--sample-interval-sec", min=0.1),
    # Previous implementation (kept for traceability):
    # network_plan: Optional[Path] = typer.Option(None, "--network-plan", exists=True, dir_okay=False),
    # Updated implementation:
    # Use string option + explicit validation for the same reason as project folder.
    network_plan: Optional[str] = typer.Option(None, "--network-plan", help="Path to JSON network plan"),
) -> None:
    log_flow(
        "CLI command started: network-latency-overhead "
        f"(dir={project_folder}, recursive={recursive}, only_compose={only_compose}, "
        f"only_container={only_container}, sample_interval_sec={sample_interval_sec}, "
        f"network_plan={network_plan})"
    )
    project_folder_path = _validated_project_folder(project_folder)
    network_plan_path: Optional[Path] = None
    if network_plan:
        network_plan_path = Path(network_plan).expanduser().resolve()
        if not network_plan_path.exists():
            raise typer.BadParameter(f"Network plan does not exist: {network_plan_path}")
        if network_plan_path.is_dir():
            raise typer.BadParameter(f"Network plan must be a file: {network_plan_path}")

    stacks = _discover(project_folder_path, recursive, only_compose, only_container)
    if not stacks:
        raise typer.BadParameter("No valid stack found with the selected options")
    log_flow(f"Discovered stacks: {', '.join(stack.name for stack in stacks)}")

    tag = _now_tag()
    for stack in stacks:
        console.print(f"[cyan]Collecting network metrics for stack:[/cyan] {stack.name}")
        results = collect_network_metrics(
            stack=stack,
            sample_interval_sec=sample_interval_sec,
            network_plan_path=network_plan_path,
        )
        if only_container:
            results = [item for item in results if item.source == only_container]
        rows = [item.model_dump() for item in results]
        metrics_dir = ensure_metrics_dir(stack.path)
        json_path = metrics_dir / f"network_latency_{tag}.json"
        csv_path = metrics_dir / f"network_latency_{tag}.csv"
        # Previous implementation (kept for traceability):
        # save_json(json_path, rows)
        #
        # Updated implementation:
        # Persist sampling metadata and per-sample series in the JSON envelope.
        save_json(
            json_path,
            {
                "stack": stack.name,
                "stack_path": str(stack.path),
                "sampling_interval_sec": sample_interval_sec,
                "network_plan": str(network_plan_path) if network_plan_path else None,
                "metrics": rows,
            },
        )
        save_csv(csv_path, rows)
        log_flow(f"Saved network metrics: json={json_path} csv={csv_path}")


if __name__ == "__main__":
    app()
