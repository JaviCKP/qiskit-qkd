from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


def test_bb84_aer_noisy_example_runs_and_reports_noise_effects() -> None:
    pytest.importorskip("qiskit_aer")

    example = Path(__file__).resolve().parents[1] / "examples" / "bb84_aer_noisy.py"

    completed = subprocess.run(
        [sys.executable, str(example)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "BB84 Aer noisy comparison" in completed.stdout
    assert "ideal" in completed.stdout
    assert "depolarizing" in completed.stdout
    assert "phase_damping" in completed.stdout
    assert "readout" in completed.stdout
    assert "NoiseModel" in completed.stdout


def test_bb84_physical_noise_example_runs_and_reports_layered_effects() -> None:
    example = (
        Path(__file__).resolve().parents[1] / "examples" / "bb84_physical_noise.py"
    )

    completed = subprocess.run(
        [sys.executable, str(example)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "BB84 physical noise comparison" in completed.stdout
    assert "preparation" in completed.stdout
    assert "misalignment" in completed.stdout
    assert "background" in completed.stdout
    assert "event-layer" in completed.stdout


def test_bb84_dynamic_channel_example_runs_and_reports_time_rows() -> None:
    example = (
        Path(__file__).resolve().parents[1] / "examples" / "bb84_dynamic_channel.py"
    )

    completed = subprocess.run(
        [sys.executable, str(example)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "BB84 dynamic channel characterization" in completed.stdout
    assert "prep_err" in completed.stdout
    assert "bg_rate_hz" in completed.stdout
    assert "qber" in completed.stdout


def test_bb84_eve_example_runs_and_reports_attack_effects() -> None:
    example = (
        Path(__file__).resolve().parents[1]
        / "examples"
        / "bb84_eve_intercept_resend.py"
    )

    completed = subprocess.run(
        [sys.executable, str(example)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "BB84 Eve intercept-resend comparison" in completed.stdout
    assert "intercept_25" in completed.stdout
    assert "intercept_100" in completed.stdout
    assert "eve_info" in completed.stdout


def test_bb84_decoy_example_runs_and_reports_intensity_stats() -> None:
    example = Path(__file__).resolve().parents[1] / "examples" / "bb84_decoy.py"

    completed = subprocess.run(
        [sys.executable, str(example)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "BB84 decoy-state source comparison" in completed.stdout
    assert "signal" in completed.stdout
    assert "decoy" in completed.stdout
    assert "vacuum" in completed.stdout


def test_bb84_ideal_example_runs_and_prints_circuit() -> None:
    example = Path(__file__).resolve().parents[1] / "examples" / "bb84_ideal.py"

    completed = subprocess.run(
        [sys.executable, str(example)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Ideal BB84 summary" in completed.stdout
    assert "First Qiskit circuit" in completed.stdout
    assert "RuntimeWarning" not in completed.stderr


def test_bb84_fiber_sweep_example_runs_and_reports_distances() -> None:
    example = Path(__file__).resolve().parents[1] / "examples" / "bb84_fiber_sweep.py"

    completed = subprocess.run(
        [sys.executable, str(example)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "BB84 fiber sweep" in completed.stdout
    assert "secret_bps" in completed.stdout
    assert "100.0" in completed.stdout


def test_bb84_visualization_example_runs_or_reports_optional_extra() -> None:
    example = Path(__file__).resolve().parents[1] / "examples" / "bb84_visualization.py"

    completed = subprocess.run(
        [sys.executable, str(example)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "BB84 visualization demo" in completed.stdout
    assert (
        "saved examples/figures/bb84_distance_summary.svg" in completed.stdout
        or "requires qiskit-qkd[plot]" in completed.stdout
    )


def test_e91_chsh_example_runs_and_reports_bell_violation() -> None:
    example = Path(__file__).resolve().parents[1] / "examples" / "e91_chsh.py"

    completed = subprocess.run(
        [sys.executable, str(example)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Ideal E91 singlet" in completed.stdout
    assert "CHSH S" in completed.stdout
    assert "violation=True" in completed.stdout
