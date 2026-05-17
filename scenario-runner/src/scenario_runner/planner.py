from __future__ import annotations

from typing import List

from .models import PlannedRun, RunConfig, Strategy


def build_plan(config: RunConfig) -> List[PlannedRun]:
    planned_runs: List[PlannedRun] = []

    for launch_index in range(1, config.max_instances + 1):
        # Change rationale: experiments only need simultaneous or fixed-interval launches.
        if config.strategy == Strategy.SPIKE:
            launch_offset = 0.0
        else:
            launch_offset = (launch_index - 1) * config.interval_sec

        planned_runs.append(
            PlannedRun(
                launch_index=launch_index,
                launch_offset_sec=launch_offset,
                instance=str(launch_index),
                scenario_id=config.scenario,
            )
        )

    return planned_runs
