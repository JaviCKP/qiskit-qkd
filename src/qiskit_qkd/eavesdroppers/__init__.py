"""Adversarial models for QKD protocol simulations."""

from .bb84 import (
    EveAttackResult,
    InterceptResendEve,
    NoEve,
    PhotonNumberSplittingEve,
    eve_from_config,
)

__all__ = [
    "EveAttackResult",
    "InterceptResendEve",
    "NoEve",
    "PhotonNumberSplittingEve",
    "eve_from_config",
]
