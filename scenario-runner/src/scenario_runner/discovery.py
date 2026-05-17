from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from .models import ScenarioSpec


def _extract_scenario_ids_from_dir_name(dir_name: str) -> List[int]:
    ids: List[int] = []
    for token in dir_name.split("_"):
        if token.isdigit():
            ids.append(int(token))
        else:
            break
    return ids


def discover_scenarios(labs_dir: Path) -> Dict[int, ScenarioSpec]:
    scenarios: Dict[int, ScenarioSpec] = {}

    if not labs_dir.exists() or not labs_dir.is_dir():
        raise ValueError(f"Labs directory does not exist or is not a directory: {labs_dir}")

    for entry in sorted(labs_dir.iterdir(), key=lambda item: item.name):
        if not entry.is_dir():
            continue

        makefile = entry / "Makefile"
        if not makefile.exists():
            continue

        scenario_ids = _extract_scenario_ids_from_dir_name(entry.name)
        for scenario_id in scenario_ids:
            if scenario_id in scenarios:
                raise ValueError(
                    f"Scenario id {scenario_id} is declared more than once "
                    f"({scenarios[scenario_id].lab_path} and {entry})"
                )
            scenarios[scenario_id] = ScenarioSpec(scenario_id=scenario_id, lab_path=entry.resolve())

    return scenarios
