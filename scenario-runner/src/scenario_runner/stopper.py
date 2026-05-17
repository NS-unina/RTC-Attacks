from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
from typing import Iterable, List, Set

from .models import ScenarioSpec
from .utils import log_flow


@dataclass
class StopResult:
    scenario_id: int
    instance: str
    lab_path: Path
    command: List[str]
    exit_code: int


def _read_stack_id(lab_path: Path) -> str | None:
    makefile_path = lab_path / "Makefile"
    if not makefile_path.exists():
        return None

    for line in makefile_path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\s*STACK_ID\s*:?=\s*(.+?)\s*$", line)
        if match:
            return match.group(1).strip()
    return None


def _list_active_projects() -> Set[str]:
    completed = subprocess.run(  # noqa: S603
        ["docker", "ps", "--format", "{{.Label \"com.docker.compose.project\"}}"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return set()

    projects: Set[str] = set()
    for raw_line in completed.stdout.splitlines():
        project = raw_line.strip()
        if project:
            projects.add(project)
    return projects


def _resolve_instances_for_stack(stack_id: str, active_projects: Set[str]) -> List[str]:
    instances: Set[str] = {"default"}
    prefix = f"{stack_id}_"

    for project in active_projects:
        if project == stack_id:
            instances.add("default")
            continue
        if not project.startswith(prefix):
            continue
        suffix = project[len(prefix):]
        if suffix.isdigit():
            instances.add(suffix)

    def _instance_sort_key(value: str) -> tuple[int, int]:
        if value == "default":
            return (0, 0)
        return (1, int(value))

    return sorted(instances, key=_instance_sort_key)


def stop_scenarios(scenario_specs: Iterable[ScenarioSpec]) -> List[StopResult]:
    results: List[StopResult] = []
    active_projects = _list_active_projects()

    for scenario_spec in sorted(scenario_specs, key=lambda item: item.scenario_id):
        stack_id = _read_stack_id(scenario_spec.lab_path)
        instances = ["default"]
        if stack_id is not None:
            instances = _resolve_instances_for_stack(stack_id=stack_id, active_projects=active_projects)

        for instance in instances:
            command = ["make", "stop", f"INSTANCE={instance}"]
            log_flow(
                "Stopping scenario=%s instance=%s cwd=%s command=%s"
                % (scenario_spec.scenario_id, instance, scenario_spec.lab_path, " ".join(command))
            )

            completed = subprocess.run(  # noqa: S603
                command,
                cwd=str(scenario_spec.lab_path),
                check=False,
                text=True,
            )
            results.append(
                StopResult(
                    scenario_id=scenario_spec.scenario_id,
                    instance=instance,
                    lab_path=scenario_spec.lab_path,
                    command=command,
                    exit_code=completed.returncode,
                )
            )

    return results
