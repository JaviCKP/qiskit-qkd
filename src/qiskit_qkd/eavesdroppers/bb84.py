"""Adversarial BB84 models kept separate from accidental channel noise."""

from __future__ import annotations

import random
from dataclasses import dataclass

from qiskit_qkd._json import JSONObject
from qiskit_qkd._validation import (
    normalize_string_tuple,
    require_bool,
    require_non_empty_str,
    require_non_negative_int,
    require_probability,
)
from qiskit_qkd.channel_core import PreparedState
from qiskit_qkd.config import EveConfig


def _validate_bit(name: str, value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value not in {0, 1}:
        raise ValueError(f"{name} must be 0 or 1")
    return value


def _validate_attack_position(value: str) -> str:
    """Normalize the two supported Eve placement seams.

    ``EveConfig`` performs the public normalization as well.  Keeping this
    small validator here makes the attack models safe to construct directly,
    which is useful for unit tests and for third-party protocol adapters.
    """

    position = require_non_empty_str("attack_position", value).lower()
    aliases = {
        "post-loss": "post_loss",
        "postloss": "post_loss",
        "before_loss": "pre_loss",
        "pre-loss": "pre_loss",
        "preloss": "pre_loss",
    }
    position = aliases.get(position, position)
    if position not in {"post_loss", "pre_loss"}:
        raise ValueError("attack_position must be post_loss or pre_loss")
    return position


@dataclass(frozen=True, slots=True)
class EveAttackResult:
    """Result of one adversarial action before Bob measures a BB84 signal."""

    resend_bit: int
    resend_basis: str
    intercepted: bool = False
    eve_action: str | None = None
    eve_basis: str | None = None
    eve_bit: int | None = None
    eve_detectable: bool = False
    eve_knows_alice_bit: bool = False
    block_signal: bool = False
    forwarded_photon_number: int | None = None
    attack_position: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "resend_bit",
            _validate_bit("resend_bit", self.resend_bit),
        )
        object.__setattr__(
            self,
            "resend_basis",
            require_non_empty_str("resend_basis", self.resend_basis),
        )
        object.__setattr__(
            self,
            "intercepted",
            require_bool("intercepted", self.intercepted),
        )
        if self.eve_action is not None:
            object.__setattr__(
                self,
                "eve_action",
                require_non_empty_str("eve_action", self.eve_action),
            )
        if self.eve_basis is not None:
            object.__setattr__(
                self,
                "eve_basis",
                require_non_empty_str("eve_basis", self.eve_basis),
            )
        if self.eve_bit is not None:
            object.__setattr__(self, "eve_bit", _validate_bit("eve_bit", self.eve_bit))
        object.__setattr__(
            self,
            "eve_detectable",
            require_bool("eve_detectable", self.eve_detectable),
        )
        object.__setattr__(
            self,
            "eve_knows_alice_bit",
            require_bool("eve_knows_alice_bit", self.eve_knows_alice_bit),
        )
        object.__setattr__(
            self,
            "block_signal",
            require_bool("block_signal", self.block_signal),
        )
        if self.forwarded_photon_number is not None:
            object.__setattr__(
                self,
                "forwarded_photon_number",
                require_non_negative_int(
                    "forwarded_photon_number",
                    self.forwarded_photon_number,
                ),
            )
        if self.attack_position is not None:
            object.__setattr__(
                self,
                "attack_position",
                _validate_attack_position(self.attack_position),
            )

    def tags(self) -> JSONObject:
        """Return JSON-safe simulator diagnostics for event tracing."""

        if not self.intercepted:
            return {}
        tags: JSONObject = {
            "eve_intercepted": True,
            "eve_bit": self.eve_bit,
            "eve_resend_bit": self.resend_bit,
            "eve_resend_basis": self.resend_basis,
            "eve_knows_bit": self.eve_knows_alice_bit,
        }
        if self.attack_position is not None:
            tags["eve_attack_position"] = self.attack_position
        if self.block_signal:
            tags["eve_blocked_signal"] = True
        if self.forwarded_photon_number is not None:
            tags["eve_forwarded_photons"] = self.forwarded_photon_number
        if self.eve_action == "pns_split":
            tags["eve_photons_kept"] = 1
        return tags


class NoEve:
    """No-adversary model that leaves the signal unchanged."""

    def attack(
        self,
        *,
        bit: int,
        basis: str,
        basis_choices: tuple[str, ...],
        rng: random.Random,
        photon_number: int = 1,
        surviving_photon_number: int = 1,
        intensity_class: str | None = None,
        prepared_state: PreparedState | None = None,
    ) -> EveAttackResult:
        del rng, photon_number, surviving_photon_number, intensity_class
        normalize_string_tuple("basis_choices", basis_choices)
        if prepared_state is not None:
            bit = prepared_state.prepared_bit
            basis = prepared_state.alice_basis
        return EveAttackResult(
            resend_bit=_validate_bit("bit", bit),
            resend_basis=require_non_empty_str("basis", basis),
        )


@dataclass(frozen=True, slots=True)
class InterceptResendEve:
    """Pedagogical BB84 intercept-resend attack.

    Eve chooses a BB84 basis, measures the signal, and resends the measured bit
    in her chosen basis. Wrong-basis interceptions are the detectable
    disturbance that drives the familiar p/4 BB84 QBER trend.
    """

    intercept_probability: float = 1.0
    attack_position: str = "post_loss"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "intercept_probability",
            require_probability(
                "intercept_probability",
                self.intercept_probability,
            ),
        )
        object.__setattr__(
            self,
            "attack_position",
            _validate_attack_position(self.attack_position),
        )

    def attack(
        self,
        *,
        bit: int,
        basis: str,
        basis_choices: tuple[str, ...],
        rng: random.Random,
        photon_number: int = 1,
        surviving_photon_number: int = 1,
        intensity_class: str | None = None,
        prepared_state: PreparedState | None = None,
    ) -> EveAttackResult:
        del photon_number, surviving_photon_number, intensity_class
        if prepared_state is not None:
            bit = prepared_state.prepared_bit
            basis = prepared_state.alice_basis
        bit = _validate_bit("bit", bit)
        basis = require_non_empty_str("basis", basis)
        choices = normalize_string_tuple("basis_choices", basis_choices)
        if self.intercept_probability <= 0.0:
            return EveAttackResult(
                resend_bit=bit,
                resend_basis=basis,
                attack_position=self.attack_position,
            )
        if rng.random() >= self.intercept_probability:
            return EveAttackResult(
                resend_bit=bit,
                resend_basis=basis,
                attack_position=self.attack_position,
            )

        eve_basis = rng.choice(choices)
        if eve_basis == basis:
            eve_bit = bit
            eve_detectable = False
            eve_knows_alice_bit = True
        else:
            eve_bit = rng.randrange(2)
            eve_detectable = True
            eve_knows_alice_bit = False

        return EveAttackResult(
            resend_bit=eve_bit,
            resend_basis=eve_basis,
            intercepted=True,
            eve_action="intercept_resend",
            eve_basis=eve_basis,
            eve_bit=eve_bit,
            eve_detectable=eve_detectable,
            eve_knows_alice_bit=eve_knows_alice_bit,
            attack_position=self.attack_position,
        )


@dataclass(frozen=True, slots=True)
class PhotonNumberSplittingEve:
    """First-order photon-number-splitting attack for weak coherent BB84.

    Eve performs an idealized photon-number measurement. On multi-photon
    pulses she keeps one photon and forwards the BB84 state without changing
    basis, so she learns sifted bits after basis announcement without adding
    QBER. Optionally, she can block single-photon pulses to mimic lossy links.
    """

    split_probability: float = 1.0
    block_single_photon_probability: float = 0.0
    attack_position: str = "post_loss"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "split_probability",
            require_probability("split_probability", self.split_probability),
        )
        object.__setattr__(
            self,
            "block_single_photon_probability",
            require_probability(
                "block_single_photon_probability",
                self.block_single_photon_probability,
            ),
        )
        object.__setattr__(
            self,
            "attack_position",
            _validate_attack_position(self.attack_position),
        )

    def attack(
        self,
        *,
        bit: int,
        basis: str,
        basis_choices: tuple[str, ...],
        rng: random.Random,
        photon_number: int = 1,
        surviving_photon_number: int = 1,
        intensity_class: str | None = None,
        prepared_state: PreparedState | None = None,
    ) -> EveAttackResult:
        del intensity_class
        if prepared_state is not None:
            bit = prepared_state.prepared_bit
            basis = prepared_state.alice_basis
        bit = _validate_bit("bit", bit)
        basis = require_non_empty_str("basis", basis)
        normalize_string_tuple("basis_choices", basis_choices)
        photon_number = require_non_negative_int("photon_number", photon_number)
        surviving_photon_number = require_non_negative_int(
            "surviving_photon_number",
            surviving_photon_number,
        )
        # A post-loss Eve can only observe photons that survived the channel.
        # Reject inconsistent diagnostics instead of allowing an attack to
        # manufacture a forwarded count larger than the emitted pulse.
        if (
            self.attack_position == "post_loss"
            and surviving_photon_number > photon_number
        ):
            raise ValueError(
                "surviving_photon_number cannot exceed photon_number",
            )
        # The number visible to Eve depends on her physical placement.  For a
        # pre-loss attack it is the source emission; post-loss sees survivors.
        observed_photon_number = (
            photon_number
            if self.attack_position == "pre_loss"
            else surviving_photon_number
        )
        if observed_photon_number == 0:
            return EveAttackResult(
                resend_bit=bit,
                resend_basis=basis,
                attack_position=self.attack_position,
            )

        if (
            observed_photon_number >= 2
            and (
                self.split_probability == 1.0
                or (
                    self.split_probability > 0.0
                    and rng.random() < self.split_probability
                )
            )
        ):
            return EveAttackResult(
                resend_bit=bit,
                resend_basis=basis,
                intercepted=True,
                eve_action="pns_split",
                eve_basis=basis,
                eve_bit=bit,
                eve_detectable=False,
                eve_knows_alice_bit=True,
                forwarded_photon_number=observed_photon_number - 1,
                attack_position=self.attack_position,
            )

        if (
            observed_photon_number == 1
            and (
                self.block_single_photon_probability == 1.0
                or (
                    self.block_single_photon_probability > 0.0
                    and rng.random() < self.block_single_photon_probability
                )
            )
        ):
            return EveAttackResult(
                resend_bit=bit,
                resend_basis=basis,
                intercepted=True,
                eve_action="pns_block_single",
                eve_detectable=True,
                eve_knows_alice_bit=False,
                block_signal=True,
                forwarded_photon_number=0,
                attack_position=self.attack_position,
            )

        return EveAttackResult(
            resend_bit=bit,
            resend_basis=basis,
            attack_position=self.attack_position,
        )


def eve_from_config(
    config: EveConfig,
) -> NoEve | InterceptResendEve | PhotonNumberSplittingEve:
    """Build an adversarial model from validated scenario configuration."""

    kind = config.kind.lower()
    if kind in {"none", "no_eve"}:
        return NoEve()
    if kind == "intercept_resend":
        return InterceptResendEve(
            intercept_probability=config.intercept_probability,
            attack_position=config.attack_position,
        )
    if kind == "photon_number_splitting":
        return PhotonNumberSplittingEve(
            split_probability=config.pns_split_probability,
            block_single_photon_probability=(
                config.pns_block_single_photon_probability
            ),
            attack_position=config.attack_position,
        )
    raise ValueError(f"Unsupported eavesdropper kind: {config.kind!r}")
