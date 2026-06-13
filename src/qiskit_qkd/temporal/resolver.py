"""Resolve dynamic scenario parameters at a concrete simulation time."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from qiskit_qkd._validation import require_non_negative_number
from qiskit_qkd.config.dynamics import (
    DynamicConfig,
    ParameterSchedule,
    validate_parameter_target,
)
from qiskit_qkd.config.schema import Scenario


@dataclass(frozen=True, slots=True)
class ParameterResolver:
    """Build effective immutable scenarios from time-dependent schedules."""

    parameter_schedules: tuple[ParameterSchedule, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.parameter_schedules, tuple | list):
            raise TypeError("parameter_schedules must be a tuple or list")
        schedules: list[ParameterSchedule] = []
        for index, schedule in enumerate(self.parameter_schedules):
            if isinstance(schedule, ParameterSchedule):
                schedules.append(schedule)
            elif isinstance(schedule, Mapping):
                schedules.append(ParameterSchedule.from_dict(schedule))
            else:
                raise TypeError(f"parameter_schedules[{index}] must be a schedule")
        object.__setattr__(self, "parameter_schedules", tuple(schedules))

    def scenario_at(self, scenario: Scenario, *, time_s: float) -> Scenario:
        """Return a static effective scenario with active schedules applied.

        The returned scenario carries no pending dynamic schedules: they are
        consumed by the resolution, so the result can be passed directly to a
        protocol runner.
        """

        time = require_non_negative_number("time_s", time_s)
        updates: dict[str, dict[str, Any]] = {}
        active_targets: set[str] = set()
        for schedule in self._schedules_for(scenario):
            value = schedule.value_at(time)
            if value is None:
                continue
            if schedule.target in active_targets:
                raise ValueError(
                    "Multiple dynamic schedules are active for "
                    f"{schedule.target!r} at time_s={time}",
                )
            active_targets.add(schedule.target)
            section, field = schedule.target.split(".")
            updates.setdefault(section, {})[field] = value

        effective = scenario
        for section, section_updates in updates.items():
            if section == "scenario":
                effective = replace(effective, **section_updates)
                continue
            section_config = getattr(effective, section)
            effective = replace(
                effective,
                **{section: replace(section_config, **section_updates)},
            )
        if effective.dynamic.parameter_schedules:
            effective = replace(effective, dynamic=DynamicConfig())
        return effective

    def parameter_values(self, scenario: Scenario, *, time_s: float) -> dict[str, Any]:
        """Return values for all scheduled targets after resolving ``time_s``."""

        effective = self.scenario_at(scenario, time_s=time_s)
        targets = dict.fromkeys(
            schedule.target for schedule in self._schedules_for(scenario)
        )
        return {
            target: get_parameter_value(effective, target)
            for target in targets
        }

    def _schedules_for(self, scenario: Scenario) -> tuple[ParameterSchedule, ...]:
        return scenario.dynamic.parameter_schedules + self.parameter_schedules


def get_parameter_value(scenario: Scenario, target: str) -> Any:
    """Read a validated ``section.field`` target from a scenario."""

    normalized = validate_parameter_target(target)
    section, field = normalized.split(".")
    if section == "scenario":
        return getattr(scenario, field)
    return getattr(getattr(scenario, section), field)


def scenario_at(scenario: Scenario, *, time_s: float) -> Scenario:
    """Convenience wrapper around :class:`ParameterResolver`."""

    return ParameterResolver().scenario_at(scenario, time_s=time_s)
