"""Qiskit-first tools for quantum key distribution simulations."""

from typing import TYPE_CHECKING

from .analysis import (
    DEFAULT_CONFIDENCE_LEVEL,
    ConfidenceInterval,
    add_derived_metrics,
    authoritative_metrics_from_result,
    authoritative_result_metrics,
    bell_rows_from_result,
    decoy_rows_from_result,
    extract_authoritative_metrics,
    mean_confidence_interval,
    metric_rows_from_results,
    observed_metric_rows_from_results,
    proportion_confidence_interval,
    secure_distance_limit,
    summarize_metric_rows,
    t_confidence_interval,
    t_interval,
    wilson_interval,
)
from .channel_core import PreparedState
from .config import (
    ChannelConfig,
    DecoyIntensity,
    DetectorConfig,
    DynamicConfig,
    E91Config,
    EveConfig,
    ParameterSchedule,
    PostProcessingConfig,
    ProtocolConfig,
    Scenario,
    SourceConfig,
    TimingConfig,
)
from .provenance import PACKAGE_VERSION as __version__
from .reproducibility import make_rng
from .results import Event, Metrics, ResultAssessment, SimulationResult
from .sources import (
    EmissionEvent,
    EntangledPairSource,
    IdealSinglePhotonSource,
    WeakCoherentDecoySource,
    source_from_config,
)

if TYPE_CHECKING:
    from .backends import QiskitSamplerBackend
    from .channels import (
        ChannelCharacterizer,
        ChannelState,
        FiberChannel,
        FreeSpaceChannel,
        IdealChannel,
        SpaceChannel,
        UnderwaterChannel,
    )
    from .eavesdroppers import (
        EveAttackResult,
        InterceptResendEve,
        NoEve,
        PhotonNumberSplittingEve,
    )
    from .protocols import BB84Protocol, E91Protocol
    from .qiskit_integration import (
        AerNoiseModelAdapter,
        CircuitFactory,
        TranspilationOptions,
    )
    from .temporal import (
        ConstantProfile,
        ExponentialRampProfile,
        LinearRampProfile,
        ParameterResolver,
    )

__all__ = [
    "AerNoiseModelAdapter",
    "ConfidenceInterval",
    "DEFAULT_CONFIDENCE_LEVEL",
    "add_derived_metrics",
    "authoritative_metrics_from_result",
    "authoritative_result_metrics",
    "BB84Protocol",
    "bell_rows_from_result",
    "ChannelConfig",
    "ChannelCharacterizer",
    "ChannelState",
    "CircuitFactory",
    "ConstantProfile",
    "DecoyIntensity",
    "DetectorConfig",
    "DynamicConfig",
    "E91Config",
    "E91Protocol",
    "EmissionEvent",
    "EntangledPairSource",
    "Event",
    "EveAttackResult",
    "EveConfig",
    "ExponentialRampProfile",
    "FiberChannel",
    "FreeSpaceChannel",
    "IdealChannel",
    "IdealSinglePhotonSource",
    "InterceptResendEve",
    "LinearRampProfile",
    "Metrics",
    "NoEve",
    "ParameterResolver",
    "ParameterSchedule",
    "PhotonNumberSplittingEve",
    "PostProcessingConfig",
    "PreparedState",
    "ProtocolConfig",
    "QiskitSamplerBackend",
    "ResultAssessment",
    "Scenario",
    "SimulationResult",
    "SpaceChannel",
    "SourceConfig",
    "TimingConfig",
    "TranspilationOptions",
    "UnderwaterChannel",
    "WeakCoherentDecoySource",
    "__version__",
    "decoy_rows_from_result",
    "extract_authoritative_metrics",
    "make_rng",
    "metric_rows_from_results",
    "mean_confidence_interval",
    "observed_metric_rows_from_results",
    "proportion_confidence_interval",
    "secure_distance_limit",
    "summarize_metric_rows",
    "source_from_config",
    "t_confidence_interval",
    "t_interval",
    "wilson_interval",
]


def __getattr__(name: str) -> object:
    if name == "BB84Protocol":
        from .protocols import BB84Protocol

        return BB84Protocol
    if name == "E91Protocol":
        from .protocols import E91Protocol

        return E91Protocol
    if name == "CircuitFactory":
        from .qiskit_integration import CircuitFactory

        return CircuitFactory
    if name == "AerNoiseModelAdapter":
        from .qiskit_integration import AerNoiseModelAdapter

        return AerNoiseModelAdapter
    if name == "TranspilationOptions":
        from .qiskit_integration import TranspilationOptions

        return TranspilationOptions
    if name == "QiskitSamplerBackend":
        from .backends import QiskitSamplerBackend

        return QiskitSamplerBackend
    if name == "ChannelCharacterizer":
        from .channels import ChannelCharacterizer

        return ChannelCharacterizer
    if name == "ChannelState":
        from .channels import ChannelState

        return ChannelState
    if name == "SpaceChannel":
        from .channels import SpaceChannel

        return SpaceChannel
    if name == "FreeSpaceChannel":
        from .channels import FreeSpaceChannel

        return FreeSpaceChannel
    if name == "FiberChannel":
        from .channels import FiberChannel

        return FiberChannel
    if name == "IdealChannel":
        from .channels import IdealChannel

        return IdealChannel
    if name == "UnderwaterChannel":
        from .channels import UnderwaterChannel

        return UnderwaterChannel
    if name == "ConstantProfile":
        from .temporal import ConstantProfile

        return ConstantProfile
    if name == "LinearRampProfile":
        from .temporal import LinearRampProfile

        return LinearRampProfile
    if name == "ExponentialRampProfile":
        from .temporal import ExponentialRampProfile

        return ExponentialRampProfile
    if name == "ParameterResolver":
        from .temporal import ParameterResolver

        return ParameterResolver
    if name == "EveAttackResult":
        from .eavesdroppers import EveAttackResult

        return EveAttackResult
    if name == "InterceptResendEve":
        from .eavesdroppers import InterceptResendEve

        return InterceptResendEve
    if name == "NoEve":
        from .eavesdroppers import NoEve

        return NoEve
    if name == "PhotonNumberSplittingEve":
        from .eavesdroppers import PhotonNumberSplittingEve

        return PhotonNumberSplittingEve
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
