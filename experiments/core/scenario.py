"""Domain constants and helpers for RTC-Attacks scenarios.

Single source of truth for scenario identifiers and expected IDS signatures.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


# Mapping: scenario_id → expected Suricata SIDs that confirm attack detection.
EXPECTED_SIDS: dict[int, list[int]] = {
    1: [2000001],
    2: [2000002],
    3: [2000003],
    4: [2000004],
    5: [2000005],
    6: [2000006],
    7: [2000007],
    8: [2000008, 2000010],
    9: [2000009],
}

ALL_SCENARIO_IDS: tuple[int, ...] = tuple(sorted(EXPECTED_SIDS.keys()))


@dataclass(frozen=True)
class ScenarioSidsEvents:
    """Immutable descriptor for a single RTC-Attacks scenario."""

    scenario_id: int
    expected_sids: tuple[int, ...]

    @property
    def label(self) -> str:
        return f"scenario_{self.scenario_id}"


def get_scenario_spec(scenario_id: int) -> ScenarioSidsEvents:
    """Return the ScenarioSidsEvents for a given ID, raising ValueError if unknown."""
    if scenario_id not in EXPECTED_SIDS:
        raise ValueError(f"Unknown scenario id: {scenario_id}. Valid: {ALL_SCENARIO_IDS}")
    return ScenarioSidsEvents(
        scenario_id=scenario_id,
        expected_sids=tuple(EXPECTED_SIDS[scenario_id]),
    )


def parse_scenario_list(raw: str, allowed: Iterable[int] | None = None) -> list[int]:
    """Parse a comma-separated string of scenario IDs into a validated list."""
    values: list[int] = []
    for token in raw.split(","):
        clean = token.strip()
        if not clean:
            continue
        if not clean.isdigit():
            raise ValueError(f"Invalid scenario id: '{clean}'")
        values.append(int(clean))

    if not values:
        raise ValueError("Empty scenario list")

    allowed_set = set(allowed) if allowed is not None else set(ALL_SCENARIO_IDS)
    invalid = [v for v in values if v not in allowed_set]
    if invalid:
        raise ValueError(f"Unsupported scenario ids: {invalid}. Valid: {sorted(allowed_set)}")

    return values
