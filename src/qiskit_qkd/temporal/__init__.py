"""Temporal profiles and scenario resolvers."""

from typing import TYPE_CHECKING

from .profiles import (
    ConstantProfile,
    ExponentialRampProfile,
    LinearRampProfile,
    TimeProfile,
    profile_from_dict,
)

if TYPE_CHECKING:
    from .resolver import ParameterResolver

__all__ = [
    "ConstantProfile",
    "ExponentialRampProfile",
    "LinearRampProfile",
    "ParameterResolver",
    "TimeProfile",
    "get_parameter_value",
    "profile_from_dict",
    "scenario_at",
]


def __getattr__(name: str) -> object:
    if name == "ParameterResolver":
        from .resolver import ParameterResolver

        return ParameterResolver
    if name == "get_parameter_value":
        from .resolver import get_parameter_value

        return get_parameter_value
    if name == "scenario_at":
        from .resolver import scenario_at

        return scenario_at
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
