"""Shared visual style helpers for optional plots."""

from __future__ import annotations

QKD_COLORS = (
    "#0072B2",
    "#D55E00",
    "#009E73",
    "#CC79A7",
    "#E69F00",
    "#56B4E9",
    "#F0E442",
)

METRIC_LABELS = {
    "afterpulse_clicks": "Afterpulse clicks",
    "alice_setting": "Alice setting",
    "abort_fraction": "Abort fraction",
    "bob_setting": "Bob setting",
    "chsh_margin": "CHSH margin",
    "chsh_s": "CHSH S",
    "correlation": "Correlation",
    "dark_count_rate_hz": "Dark count rate (Hz)",
    "dead_time_discards": "Dead-time discards",
    "detected": "Detected",
    "detected_fraction": "Detected fraction",
    "distance_km": "Distance (km)",
    "emitted": "Emitted",
    "error_fraction": "Error fraction",
    "errors": "Errors",
    "eve_information_estimate": "Eve information estimate",
    "eve_intercepted_fraction": "Eve intercepted fraction",
    "final_key_length": "Final key length",
    "gain": "Gain",
    "loss_db": "Loss (dB)",
    "qber": "QBER",
    "qber_margin": "QBER margin",
    "raw_detection_rate_hz": "Raw detection rate (Hz)",
    "secret_key_rate_bps": "Secret key rate (bps)",
    "secure_fraction": "Secure fraction",
    "sifted": "Sifted",
    "sifted_fraction": "Sifted fraction",
    "sifted_key_rate_bps": "Sifted key rate (bps)",
    "time_s": "Time (s)",
    "timing_discard_fraction": "Timing discard fraction",
    "timing_discards": "Timing discards",
    "transmitted": "Transmitted",
}


def metric_label(name: str) -> str:
    """Return a human-readable label for a metric or row column."""

    if name in METRIC_LABELS:
        return METRIC_LABELS[name]
    return name.replace("_", " ").capitalize()


def compact_value(value: object) -> str:
    """Return compact tick-label text for simple numeric axes."""

    if isinstance(value, float):
        return f"{value:g}"
    return str(value)
