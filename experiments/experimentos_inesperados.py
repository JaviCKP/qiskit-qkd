"""
Experimentos BB84 con resultados inesperados pero explicables.

Cada experimento explora un fenómeno no intuitivo del protocolo BB84:
  - Efectos de ruido que no siempre degradan la clave
  - Paradojas del detector: más eficiencia no siempre ayuda
  - Eve sutil vs Eve agresiva
  - Efectos de timing y reloj
  - Tamaño de muestra y varianza estadística
  - Preparación de errores y su interacción con otros parámetros
  - Decoy states y cómo el vacío puede ser útil
  - La trampa de la amplificación de privacidad
  ...y muchos más.
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import replace
from pathlib import Path

from qiskit_qkd import (
    BB84Protocol,
    ChannelConfig,
    DecoyIntensity,
    DetectorConfig,
    EveConfig,
    PostProcessingConfig,
    Scenario,
    SourceConfig,
    TimingConfig,
)
from qiskit_qkd.backends import backend_from_scenario
from qiskit_qkd.experiments import write_artifact

SEPARATOR = "=" * 72
SUBSEP = "-" * 72
_ARTIFACT_ROWS: list[dict] = []
_ARTIFACT_SCENARIOS: list[Scenario] = []


def _record_artifact_row(scenario: object, payload: dict) -> None:
    try:
        to_dict = getattr(scenario, "to_dict", None)
        if not callable(to_dict):
            return
        row = dict(payload)
        row["scenario"] = to_dict()
        _ARTIFACT_ROWS.append(row)
        _ARTIFACT_SCENARIOS.append(scenario)
    except (AttributeError, TypeError):
        return


def _configure_console_output() -> None:
    """Keep the Unicode scientific notation printable on Windows consoles."""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")

# ─────────────────────────────────────────────────────────────────────────────
# Utilidades
# ─────────────────────────────────────────────────────────────────────────────

def _mapping(value: object) -> dict:
    """Return a plain mapping for result payloads and dataclass assessments."""

    if value is None:
        return {}
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        value = to_dict()
    return dict(value) if hasattr(value, "items") else {}


def run_result(scenario: Scenario):
    """Run one scenario through the canonical scenario-aware backend."""

    return BB84Protocol().run(scenario, backend=backend_from_scenario(scenario))


def run(scenario: Scenario) -> dict:
    """Return authoritative assessment plus physical observations.

    ``Metrics.qber``, ``Metrics.abort`` and ``Metrics.secret_key_rate_bps`` are
    schema-v1 compatibility values.  They are intentionally not consulted
    here: in particular, ``metrics.qber == 0`` is not evidence that QBER was
    defined when no sifted bits exist.
    """

    result = run_result(scenario)
    assessment = _mapping(result.assessment)
    classical = _mapping(result.classical)
    decoy = _mapping(result.decoy)
    bell = _mapping(result.bell)
    m = result.metrics
    qber_defined = bool(assessment.get("qber_defined", False))
    qber_value = assessment.get("qber_value") if qber_defined else None
    rate_status = assessment.get("rate_estimate_status", "unavailable")
    rate_value = (
        assessment.get("rate_estimate_bps")
        if rate_status == "available"
        else None
    )
    threshold_exceeded = assessment.get("threshold_exceeded")
    abort = (
        threshold_exceeded is True
        or assessment.get("key_status") == "no_key_threshold_exceeded"
    )
    payload = {
        # Physical observations (not security decisions).
        "pulses":           m.pulses,
        "emitted":          m.emitted,
        "transmitted":      m.transmitted,
        "detected":         m.detected,
        "sifted":           m.sifted,
        "errors":           m.errors,
        "gain":             m.gain,
        "loss_db":          m.loss_db,
        "sifted_bps":       m.sifted_key_rate_bps,
        "timing_discards":  m.timing_discards,
        "dead_time_discards": m.dead_time_discards,
        "afterpulse":       m.afterpulse_clicks,
        "eve_frac":         m.eve_intercepted_fraction,
        "eve_info":         m.eve_information_estimate,
        # Authoritative result-level evidence.
        "assessment":       assessment,
        "classical":        classical,
        "decoy":            decoy,
        "decoy_security":   _mapping(decoy.get("security")),
        "bell":             bell,
        "qber_defined":     qber_defined,
        "qber":             qber_value,
        "rate_estimate_status": rate_status,
        "secret_bps":       rate_value,
        "verification_status": assessment.get(
            "verification_status",
            classical.get("verification_status"),
        ),
        "abort":            abort,
    }
    _record_artifact_row(scenario, payload)
    return payload


def header(title: str) -> None:
    print(f"\n{SEPARATOR}")
    print(f"  {title}")
    print(SEPARATOR)


def subheader(title: str) -> None:
    print(f"\n{SUBSEP}")
    print(f"  {title}")
    print(SUBSEP)


def show(label: str, r: dict, notes: str = "") -> None:
    abort_str = " [ABORT]" if r["abort"] else ""
    qber = "n/d" if not r["qber_defined"] else f"{r['qber']:.4f}"
    rate = (
        "n/d"
        if r["secret_bps"] is None
        else f"{r['secret_bps']:10.2f}"
    )
    print(
        f"  {label:<38} | "
        f"QBER={qber:>6} | "
        f"rate={rate} bps | "
        f"sifted={r['sifted']:5d} | "
        f"gain={r['gain']:.5f}{abort_str}"
    )
    if notes:
        print(f"    ↳ {notes}")


def qber_text(r: dict, width: int = 8) -> str:
    value = "n/d" if not r["qber_defined"] else f"{r['qber']:.4f}"
    return f"{value:>{width}}"


def rate_text(r: dict, width: int = 12) -> str:
    value = "n/d" if r["secret_bps"] is None else f"{r['secret_bps']:.2f}"
    return f"{value:>{width}}"


# ═════════════════════════════════════════════════════════════════════════════
# EXPERIMENTO 1
# "Más fotones emitidos NO significa más clave secreta"
# Fuente coherente débil (WCS) con μ alto vs μ bajo
# ═════════════════════════════════════════════════════════════════════════════
def exp1_high_mu_kills_key():
    header("EXP 1 – μ alto y PNS: la ganancia no es la seguridad")

    print("""
  HIPÓTESIS: aumentar μ eleva la ganancia, pero también la fracción
  multifotónica que puede aprovechar un ataque PNS.
  DISEÑO: se comparan exactamente las mismas intensidades (señal, señuelo
  débil y vacío) sin Eve y con PhotonNumberSplittingEve situado antes de la
  pérdida del canal. La evidencia de seguridad es decoy["security"], no una
  tasa genérica de Metrics.
""")

    base = dict(pulses=3_000, clock_rate_hz=1_000_000.0, seed=42)
    for mu in [0.3, 0.7, 1.5, 3.0]:
        intensities = (
            DecoyIntensity("signal", mean_photon_number=mu, selection_probability=0.7),
            DecoyIntensity("weak", mean_photon_number=0.1, selection_probability=0.2),
            DecoyIntensity("vacuum", mean_photon_number=0.0, selection_probability=0.1),
        )
        common = dict(
            **base,
            source=SourceConfig(kind="weak_coherent", decoy_intensities=intensities),
            channel=ChannelConfig(kind="fiber", distance_km=20.0, attenuation_db_km=0.2),
            detector=DetectorConfig(kind="threshold", efficiency=0.85),
            post_processing=PostProcessingConfig(
                qber_abort_threshold=0.11,
                decoy_security_estimation_enabled=True,
            ),
        )
        for label, eve in (
            ("sin Eve", EveConfig(kind="none")),
            (
                "PNS pre-loss",
                EveConfig(
                    kind="photon_number_splitting",
                    attack_position="pre_loss",
                    pns_block_single_photon_probability=1.0,
                ),
            ),
        ):
            scenario = Scenario(**common, eavesdropper=eve)
            r = run(scenario)
            security = r["decoy_security"]
            security_status = security.get("data_status", "unavailable")
            security_rate = (
                security.get("secret_key_rate_bps")
                if security_status == "available"
                else None
            )
            security_rate_text = (
                "n/a" if security_rate is None else f"{security_rate:.2f}"
            )
            gains = ", ".join(
                f"{name}={row.get('gain', 0.0):.4f}"
                for name, row in r["decoy"].items()
                if name != "security" and isinstance(row, dict)
            )
            print(
                f"  μ={mu:.2f} {label:<8} | gains({gains}) | "
                f"decoy_status={security_status} | "
                f"decoy_rate={security_rate_text} | Eve_info={r['eve_info']:.3f}"
            )

    print("""
  CONCLUSIÓN: una comparación sin atacante no prueba una degradación PNS.
  La fracción multifotónica y la información estimada de Eve deben leerse
  junto con la tasa de decoy.security; el valor óptimo depende del canal,
  detector, estimador y tamaño de muestra.
""")


# ═════════════════════════════════════════════════════════════════════════════
# EXPERIMENTO 2
# "Eve al 25% eleva el QBER menos de lo esperado"
# ═════════════════════════════════════════════════════════════════════════════
def exp2_eve_qber_math():
    header("EXP 2 – El QBER de Eve sigue una fórmula exacta: Q = p_int/4")

    print("""
  HIPÓTESIS INGENUA: Eve interceptando el 50% de los fotones causa QBER=50%.
  REALIDAD: Eve introduce errores solo cuando su base es incorrecta (50% veces)
  y Bob mide diferente a Alice (50% veces en esa base). Resultado: QBER=p/4.
  Con p=1.0 (intercepción total) el QBER máximo teórico es sólo 0.25.
""")

    base = Scenario(
        pulses=16_000,
        clock_rate_hz=1_000_000.0,
        seed=100,
        post_processing=PostProcessingConfig(qber_abort_threshold=None),
    )

    print(f"  {'p_intercept':>12} | {'QBER_obs':>9} | {'QBER_teórico':>13} | {'error_abs':>10}")
    print(f"  {'-'*12} | {'-'*9} | {'-'*13} | {'-'*10}")

    for p in [0.0, 0.1, 0.25, 0.5, 0.75, 1.0]:
        scenario = replace(
            base,
            seed=100 + int(p * 100),
            eavesdropper=EveConfig(kind="intercept_resend", intercept_probability=p),
        )
        r = run(scenario)
        teorico = p / 4.0
        print(
            f"  {p:12.2f} | {qber_text(r, 9)} | {teorico:13.4f} | "
            f"{abs((r['qber'] or 0.0) - teorico):10.4f}"
        )

    print("""
  CONCLUSIÓN: El QBER sigue exactamente Q = p_int/4 (ruido de fondo cero).
  Esto es sorprendente: interceptar el 100% solo introduce 25% de error.
  El 11% es solo el umbral configurado en este ejemplo; no es universal.
  Cambiarlo requiere declarar el modelo de seguridad y sus supuestos.
""")


# ═════════════════════════════════════════════════════════════════════════════
# EXPERIMENTO 3
# "Ruido de preparación vs ruido de Eve: la QBER agregada puede coincidir"
# ═════════════════════════════════════════════════════════════════════════════
def exp3_prep_error_mimics_eve():
    header("EXP 3 – QBER agregada no identifica la causa de la perturbación")

    print("""
  HIPÓTESIS INGENUA: Si Alice comete errores de preparación, Bob lo detecta.
  REALIDAD: se puede escoger p_int = 4 * prep_error para hacer coincidir
  aproximadamente una sola métrica agregada. Eso no hace idénticos los
  procesos: difieren la información de Eve, metadatos, distribuciones
  condicionadas y su respuesta a otros ruidos. La autenticación tampoco
  identifica por sí sola la causa física del error.
""")

    pulses = 8_000
    base_kwargs = dict(
        clock_rate_hz=1_000_000.0,
        seed=200,
        post_processing=PostProcessingConfig(qber_abort_threshold=None),
    )

    print(f"\n  {'escenario':<35} | {'QBER':>8} | {'secret_bps':>12}")
    print(f"  {'-'*35} | {'-'*8} | {'-'*12}")

    # Ideal
    r = run(Scenario(pulses=pulses, **base_kwargs))
    show("ideal (0 ruido)", r)

    # Solo errores de preparación
    for prep_err in [0.05, 0.10, 0.15, 0.20]:
        s = Scenario(
            pulses=pulses,
            **base_kwargs,
            source=SourceConfig(preparation_error_probability=prep_err),
        )
        r = run(s)
        show(f"prep_error={prep_err:.2f}", r)

    # Solo Eve (equivalente teórico: p = 4*prep_err)
    for prep_err in [0.05, 0.10, 0.15, 0.20]:
        p_eve = min(1.0, 4 * prep_err)
        s = replace(
            Scenario(pulses=pulses, **base_kwargs),
            seed=201,
            eavesdropper=EveConfig(kind="intercept_resend",
                                   intercept_probability=p_eve),
        )
        r = run(s)
        show(f"Eve p={p_eve:.2f} (QBER comparable)", r)

    print("""
  CONCLUSIÓN: la QBER agregada no basta para distinguir algunas causas de
  perturbación. Las diferencias de información de Eve y de modelo deben
  mantenerse explícitas; reconciliación y amplificación de privacidad no
  convierten los dos procesos en exactamente indistinguibles.
""")


# ═════════════════════════════════════════════════════════════════════════════
# EXPERIMENTO 4
# "Detector más eficiente puede empeorar la clave con ruido oscuro"
# ═════════════════════════════════════════════════════════════════════════════
def exp4_efficiency_dark_count_tradeoff():
    header("EXP 4 – Barridos factoriales del detector: una variable cada vez")

    print("""
  Se separan tres efectos que antes cambiaban simultáneamente: eficiencia,
  tasa de conteos oscuros y anchura de ventana. A ruido y ventana constantes,
  aumentar la eficiencia suele mejorar la relación señal/ruido; las
  interacciones se estudian aparte, no se atribuyen a una sola variable.
""")

    base_kwargs = dict(
        pulses=4_000,
        clock_rate_hz=1_000_000.0,
        seed=300,
        channel=ChannelConfig(kind="fiber", distance_km=50.0, attenuation_db_km=0.2),
        post_processing=PostProcessingConfig(qber_abort_threshold=0.11),
    )

    def sweep(label: str, values: list[float], detector_for):
        print(f"\n  {label}")
        print(f"  {'value':>12} | {'QBER':>8} | {'rate_status':>16} | {'gain':>8}")
        print(f"  {'-'*12} | {'-'*8} | {'-'*16} | {'-'*8}")
        for value in values:
            scenario = Scenario(**base_kwargs, detector=detector_for(value))
            r = run(scenario)
            qber = "n/d" if not r["qber_defined"] else f"{r['qber']:.4f}"
            print(
                f"  {value:12.4g} | {qber:>8} | "
                f"{r['rate_estimate_status']:>16} | {r['gain']:8.5f}"
            )

    fixed_dark = 100.0
    fixed_gate = 1e-9
    sweep(
        "eficiencia (dark_hz=100, gate_ns=1)",
        [0.2, 0.5, 0.7, 0.9],
        lambda efficiency: DetectorConfig(
            kind="threshold", efficiency=efficiency,
            dark_count_rate_hz=fixed_dark, gate_width_s=fixed_gate,
        ),
    )
    fixed_efficiency = 0.7
    sweep(
        "dark count (efficiency=0.7, gate_ns=1)",
        [0.0, 1e3, 1e4, 1e5, 1e6],
        lambda dark: DetectorConfig(
            kind="threshold", efficiency=fixed_efficiency,
            dark_count_rate_hz=dark, gate_width_s=fixed_gate,
        ),
    )
    sweep(
        "ventana (efficiency=0.7, dark_hz=100)",
        [0.25e-9, 0.5e-9, 1e-9, 2e-9, 5e-9],
        lambda gate: DetectorConfig(
            kind="threshold", efficiency=fixed_efficiency,
            dark_count_rate_hz=fixed_dark, gate_width_s=gate,
        ),
    )

    print("""
  CONCLUSIÓN: cada barrido permite atribuir cambios a su variable controlada.
  Un diseño factorial adicional puede mostrar interacciones, pero no sustituye
  estos tres controles aislados.
""")


# ═════════════════════════════════════════════════════════════════════════════
# EXPERIMENTO 5
# "Dead time: el detector que se protege a sí mismo destruye la clave"
# ═════════════════════════════════════════════════════════════════════════════
def exp5_dead_time_saturation():
    header("EXP 5 – Dead time: el detector que 'descansa' destruye la tasa de clave")

    print("""
  HIPÓTESIS INGENUA: el dead time sólo afecta si hay muchos fotones.
  REALIDAD: con clock_rate_hz alto y dead_time_s largo, la mayoría de pulsos
  caen dentro del dead time del detector → ganancia colapsa a casi cero.
  La tasa de clave se desploma aunque el QBER sea bajo.
""")

    base_kwargs = dict(
        pulses=4_000,
        clock_rate_hz=1_000_000.0,   # 1 μs entre pulsos
        seed=400,
        post_processing=PostProcessingConfig(qber_abort_threshold=None),
    )

    print(f"\n  {'dead_time_s':>12} | {'dead_time_ns':>12} | "
          f"{'gain':>8} | {'dead_time_discards':>18} | {'rate_status':>16}")
    print(f"  {'-'*12} | {'-'*12} | {'-'*8} | {'-'*18} | {'-'*16}")

    for dead_ns in [0, 100, 500, 1_000, 2_000, 5_000, 10_000]:
        dead_s = dead_ns * 1e-9
        scenario = Scenario(
            **base_kwargs,
            detector=DetectorConfig(
                kind="threshold",
                efficiency=0.85,
                dead_time_s=dead_s,
            ),
        )
        r = run(scenario)
        print(
            f"  {dead_s:12.2e} | {dead_ns:12d} | "
            f"{r['gain']:8.5f} | {r['dead_time_discards']:18d} | "
            f"{r['rate_estimate_status']:>16}"
        )

    print("""
  CONCLUSIÓN: dead_time=10 μs con clock a 1 MHz significa que el detector
  tarda 10 pulsos en recuperarse. Cada detección bloquea los 10 siguientes.
  Cuando el gain era ~0.85, casi todos los pulsos se descartan → tasa ≈ 0.
""")


# ═════════════════════════════════════════════════════════════════════════════
# EXPERIMENTO 6
# "Afterpulse: el eco fantasma del detector"
# ═════════════════════════════════════════════════════════════════════════════
def exp6_afterpulse_ghost_clicks():
    header("EXP 6 – Afterpulse: clicks fantasma que inflan el QBER")

    print("""
  HIPÓTESIS INGENUA: si hay un afterpulse, es solo un click extra poco dañino.
  REALIDAD: el afterpulse es un click sin señal real → bit aleatorio → QBER
  sube, sifted sube (parece que recibimos más), pero los bits son basura.
  Con afterpulse alto, el QBER puede superar el umbral y abortar el protocolo.
""")

    base_kwargs = dict(
        pulses=4_000,
        clock_rate_hz=1_000_000.0,
        seed=500,
        post_processing=PostProcessingConfig(qber_abort_threshold=0.11),
    )

    print(f"\n  {'afterpulse_prob':>16} | {'QBER':>8} | {'afterpulses':>11} | "
          f"{'sifted':>8} | {'secret_bps':>12} | {'abort':>5}")
    print(f"  {'-'*16} | {'-'*8} | {'-'*11} | {'-'*8} | {'-'*12} | {'-'*5}")

    for ap in [0.0, 0.01, 0.05, 0.10, 0.20, 0.40, 0.80]:
        scenario = Scenario(
            **base_kwargs,
            detector=DetectorConfig(
                kind="threshold",
                efficiency=0.85,
                afterpulse_probability=ap,
            ),
        )
        r = run(scenario)
        abort_str = "  YES" if r["abort"] else "   no"
        print(
            f"  {ap:16.2f} | {qber_text(r)} | {r['afterpulse']:11d} | "
            f"{r['sifted']:8d} | {rate_text(r)} | {abort_str}"
        )

    print("""
  CONCLUSIÓN: afterpulse_probability=0.80 puede parecer poco realista, pero
  incluso al 5-10% el QBER ya aumenta significativamente. Este es un efecto
  real en detectores de avalancha (SPAD/APD) a bajas temperaturas.
""")


# ═════════════════════════════════════════════════════════════════════════════
# EXPERIMENTO 7
# "La rotación de polarización sigue sin²(θ/2) por base"
# ═════════════════════════════════════════════════════════════════════════════
def exp7_polarization_rotation_surprise():
    header("EXP 7 – Rotación de polarización: sin²(θ/2) y dependencia de base")

    print("""
  Para el modelo actual, la probabilidad de error por base sigue
  Q(θ)=sin²(θ/2). En el eje Y usado en la primera tabla, θ=π invierte ambas
  bases y da QBER≈1. Si el eje deja Z invariante y solo mezcla X, θ=π da
  aproximadamente QBER=0.5 con bases equiprobables. No es una fase global
  inofensiva para todo el protocolo: hay que reportar la base y el modelo.

  (polarization_rotation_y_rad rota sobre eje Y del bloch sphere)
""")

    base_kwargs = dict(
        pulses=4_000,
        clock_rate_hz=1_000_000.0,
        seed=600,
        post_processing=PostProcessingConfig(qber_abort_threshold=None),
    )

    print(f"\n  {'rotación Y (rad)':>17} | {'QBER':>8} | {'esperada':>8} | {'descripción'}")
    print(f"  {'-'*17} | {'-'*8} | {'-'*8} | {'-'*32}")

    angles = [
        (0.0, "0"),
        (math.pi / 2, "π/2"),
        (math.pi, "π"),
        (3 * math.pi / 2, "3π/2"),
        (2 * math.pi, "2π"),
    ]

    for angle, desc in angles:
        scenario = Scenario(
            **base_kwargs,
            channel=ChannelConfig(polarization_rotation_y_rad=angle),
        )
        r = run(scenario)
        expected = math.sin(angle / 2) ** 2
        observed = "n/d" if not r["qber_defined"] else f"{r['qber']:.4f}"
        print(
            f"  {angle:17.4f} | {observed:>8} | {expected:8.4f} | {desc}"
        )

    print("\n  Ahora eje Z:")
    print(f"\n  {'rotación Z (rad)':>17} | {'QBER':>8} | {'descripción'}")
    print(f"  {'-'*17} | {'-'*8} | {'-'*40}")

    z_angles = [
        (0.0,         "sin rotación"),
        (math.pi/4,   "π/4"),
        (math.pi/2,   "π/2"),
        (math.pi,     "π = 180°"),
        (2*math.pi,   "2π"),
    ]
    for angle, desc in z_angles:
        scenario = Scenario(
            **base_kwargs,
            channel=ChannelConfig(polarization_rotation_z_rad=angle),
        )
        r = run(scenario)
        print(f"  {angle:17.4f} | {qber_text(r)} | {desc}")

    print("""
  CONCLUSIÓN: la tabla compara la predicción sin²(θ/2) con la observación.
  Si QBER≥0.5, la evaluación de tasa queda no disponible o cero; en
  particular, no reaparece una tasa positiva al alcanzar QBER=1.
""")


# ═════════════════════════════════════════════════════════════════════════════
# EXPERIMENTO 8
# "Jitter de reloj hace que los pulsos caigan fuera de la ventana"
# ═════════════════════════════════════════════════════════════════════════════
def exp8_timing_jitter_kills_gain():
    header("EXP 8 – Jitter de clock: los fotones no llegan cuando Bob espera")

    print("""
  HIPÓTESIS INGENUA: un poco de jitter en el reloj no importa mucho.
  REALIDAD: si jitter_std_s > gate_width_s/2, muchos fotones llegaran
  fuera de la ventana del detector y serán descartados (timing_discard).
  El gain colapsa, aunque el QBER de los que quedan sea bajo.
""")

    base_kwargs = dict(
        pulses=4_000,
        clock_rate_hz=1_000_000.0,   # pulsos cada 1 μs
        seed=700,
        detector=DetectorConfig(kind="threshold", efficiency=0.85,
                                gate_width_s=1e-9),  # ventana de 1 ns
        post_processing=PostProcessingConfig(qber_abort_threshold=None),
    )

    print(f"\n  {'jitter_std_s':>13} | {'jitter_ns':>9} | "
          f"{'gain':>8} | {'timing_discards':>15} | {'sifted':>8}")
    print(f"  {'-'*13} | {'-'*9} | {'-'*8} | {'-'*15} | {'-'*8}")

    for jitter_ns in [0, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 50.0]:
        jitter_s = jitter_ns * 1e-9
        scenario = Scenario(
            **base_kwargs,
            timing=TimingConfig(jitter_std_s=jitter_s),
        )
        r = run(scenario)
        print(
            f"  {jitter_s:13.2e} | {jitter_ns:9.1f} | "
            f"{r['gain']:8.5f} | {r['timing_discards']:15d} | "
            f"{r['sifted']:8d}"
        )

    print("""
  CONCLUSIÓN: con jitter de 5 ns y ventana de 1 ns, la mayoría de fotones
  llegan fuera de la ventana. El simulador descarta esos pulsos como
  "timing_discard" → sifted≈0. En la práctica, se necesita sincronización
  de reloj muy precisa (típicamente jitter < 100 ps en fibra óptica).
""")


# ═════════════════════════════════════════════════════════════════════════════
# EXPERIMENTO 9
# "Drift de reloj acumulado borra toda la sesión"
# ═════════════════════════════════════════════════════════════════════════════
def exp9_clock_drift_accumulates():
    header("EXP 9 – Clock drift: el desajuste acumulado es catastrófico a largo plazo")

    print("""
  HIPÓTESIS INGENUA: unos pocos ppm de diferencia de frecuencia no importan.
  REALIDAD: el drift es ACUMULATIVO. Con 10 ppm y 1M pulsos a 1 MHz,
  el offset acumulado al final es de 10 μs >> gate_width de 1 ns.
  Los últimos pulsos se descartan totalmente. Menos pulsos = sesión más corta.
""")

    base_kwargs = dict(
        clock_rate_hz=1_000_000.0,
        seed=800,
        detector=DetectorConfig(kind="threshold", gate_width_s=1e-9),
        post_processing=PostProcessingConfig(qber_abort_threshold=None),
        timing=TimingConfig(slot_assignment_policy="discard"),
    )

    print(f"\n  {'drift_ppm':>10} | {'pulses':>8} | "
          f"{'gain':>8} | {'sifted':>8} | {'secret_bps':>12}")
    print(f"  {'-'*10} | {'-'*8} | {'-'*8} | {'-'*8} | {'-'*12}")

    for drift_ppm in [0.0, 0.1, 1.0, 5.0, 10.0, 50.0, 100.0]:
        for n_pulses in [1_000, 10_000]:
            scenario = Scenario(
                pulses=n_pulses,
                **base_kwargs,
                timing=TimingConfig(
                    clock_drift_ppm=drift_ppm,
                    slot_assignment_policy="discard",
                ),
            )
            r = run(scenario)
            print(
                f"  {drift_ppm:10.1f} | {n_pulses:8d} | "
                f"{r['gain']:8.5f} | {r['sifted']:8d} | "
                f"{rate_text(r)}"
            )

    print("""
  CONCLUSIÓN: drift de 100 ppm a 1 MHz = desplazamiento de 100 ns/s.
  Con 10k pulsos (10 ms de sesión) el desfase es 1 ns, ya comparable
  con gate_width. Con 1M pulsos (1 s de sesión) → 100 ns de desfase →
  todos los fotones fuera de ventana.
""")


# ═════════════════════════════════════════════════════════════════════════════
# EXPERIMENTO 10
# "Sifting desactivado: la QBER global se acerca a 25%"
# ═════════════════════════════════════════════════════════════════════════════
def exp10_no_sifting():
    header("EXP 10 – Sin sifting: la QBER global se acerca a 25%")

    print("""
  HIPÓTESIS INGENUA: si Alice y Bob miden en bases distintas, solo se introduce
  algo de ruido extra.
  REALIDAD: medir en base X cuando Alice preparó en Z da un bit COMPLETAMENTE
  aleatorio. La mitad de las parejas usa bases distintas y, en ellas, la
  mitad de los bits discrepa: QBER global ≈ 0.5 × 0.5 = 25%.
""")

    base_kwargs = dict(
        pulses=4_000,
        clock_rate_hz=1_000_000.0,
        seed=900,
    )

    print(f"\n  {'escenario':<30} | {'QBER':>8} | {'sifted':>8} | {'secret_bps':>12}")
    print(f"  {'-'*30} | {'-'*8} | {'-'*8} | {'-'*12}")

    # Con sifting
    s = Scenario(**base_kwargs,
                  post_processing=PostProcessingConfig(sifting_enabled=True,
                                                       qber_abort_threshold=None))
    r = run(s)
    show("con sifting (normal)", r)

    # Sin sifting
    s = Scenario(**base_kwargs,
                  post_processing=PostProcessingConfig(sifting_enabled=False,
                                                       qber_abort_threshold=None))
    r = run(s)
    show("sin sifting (QBER≈0.25)", r)

    # Sin sifting + error de preparación
    s = Scenario(**base_kwargs,
                  source=SourceConfig(preparation_error_probability=0.10),
                  post_processing=PostProcessingConfig(sifting_enabled=False,
                                                       qber_abort_threshold=None))
    r = run(s)
    show("sin sifting + prep_err=0.10", r)

    print("""
  NOTA: QBER global con sifting desactivado ≈ 0.25, no 0.50. Esto se debe a que
  cuando las bases NO coinciden, el bit de Bob es totalmente aleatorio,
  pero solo la mitad de los pares de bases divergen en BB84 (Z vs X y X vs Z).
  De esos, la mitad dan error → 0.5 * 0.5 = 0.25. Inesperado pero correcto.
""")


# ═════════════════════════════════════════════════════════════════════════════
# EXPERIMENTO 11
# "Background radiation: más luz = más clave?? No: más ruido"
# ═════════════════════════════════════════════════════════════════════════════
def exp11_background_radiation():
    header("EXP 11 – Radiación de fondo: más 'fotones' = más ruido no clave")

    print("""
  HIPÓTESIS INGENUA: si hay más fotones en el canal, hay más detecciones →
  más clave.
  REALIDAD: los fotones de fondo son bits aleatorios. Si la fuente es débil
  (baja emission_probability), el background domina y el QBER sube.
  El gain sube pero la clave secreta colapsa.
""")

    base_kwargs = dict(
        pulses=2_000,
        clock_rate_hz=1_000_000.0,
        seed=1000,
        post_processing=PostProcessingConfig(qber_abort_threshold=None),
    )

    print(f"\n  {'bg_rate_hz':>12} | {'emission':>9} | "
          f"{'gain':>8} | {'QBER':>8} | {'detected':>9} | {'secret_bps':>12}")
    print(f"  {'-'*12} | {'-'*9} | {'-'*8} | {'-'*8} | {'-'*9} | {'-'*12}")

    configs = [
        (0,          1.0),
        (1_000,      1.0),
        (100_000,    1.0),
        (1_000_000,  1.0),
        (10_000_000, 1.0),
        (10_000_000, 0.5),
        (10_000_000, 0.1),
        (10_000_000, 0.0),   # solo background, sin señal
    ]

    for bg_hz, emission in configs:
        scenario = Scenario(
            **base_kwargs,
            source=SourceConfig(emission_probability=emission),
            channel=ChannelConfig(background_count_rate_hz=bg_hz),
            detector=DetectorConfig(
                kind="threshold",
                efficiency=0.85,
                gate_width_s=1e-9,
            ),
        )
        r = run(scenario)
        print(
            f"  {bg_hz:12.0f} | {emission:9.1f} | "
                f"{r['gain']:8.5f} | {qber_text(r)} | "
                f"{r['detected']:9d} | {rate_text(r)}"
        )

    print("""
  CONCLUSIÓN: con emission=0.0 y solo background, los bits que sobreviven al
  cribado son aleatorios y la QBER post-cribado tiende a 0.5, no a 0.25.
  Con emission=1.0, la señal domina y el background apenas afecta. El ratio
  señal/ruido importa.
""")


# ═════════════════════════════════════════════════════════════════════════════
# EXPERIMENTO 12
# "Phase damping vs depolarizing: no es lo mismo aunque ambos añaden errores"
# ═════════════════════════════════════════════════════════════════════════════
def exp12_phase_vs_depolar():
    header("EXP 12 – Phase damping vs Depolarizing: efectos muy distintos en BB84")

    print("""
  HIPÓTESIS INGENUA: phase damping y depolarizing son ambos "ruido cuántico"
  y deberían tener el mismo efecto en el QBER.
  REALIDAD: en BB84, la base Z mide {|0⟩,|1⟩} y la base X mide {|+⟩,|-⟩}.
  Phase damping destruye coherencias → afecta más la base X.
  Depolarizing mezcla todo → afecta ambas bases por igual.
  Resultado: misma probabilidad numérica, efectos distintos en QBER.
""")

    base_kwargs = dict(
        pulses=2_000,
        clock_rate_hz=1_000_000.0,
        seed=1100,
        post_processing=PostProcessingConfig(qber_abort_threshold=None),
    )

    print(f"\n  {'tipo_ruido':<25} | {'prob':>6} | {'QBER':>8} | {'secret_bps':>12}")
    print(f"  {'-'*25} | {'-'*6} | {'-'*8} | {'-'*12}")

    for prob in [0.0, 0.05, 0.10, 0.15, 0.20, 0.25]:
        # Depolarizing
        s = Scenario(
            **base_kwargs,
            channel=ChannelConfig(depolarizing_probability=prob),
        )
        r = run(s)
        show(f"depolarizing p={prob:.2f}", r)

        # Phase damping
        s = Scenario(
            **base_kwargs,
            channel=ChannelConfig(phase_damping_probability=prob),
        )
        r = run(s)
        show(f"phase_damping p={prob:.2f}", r)

    print("""
  CONCLUSIÓN: ambos ruidos con la misma probabilidad numérica producen
  distintos QBERs porque actúan de forma diferente sobre los estados cuánticos.
  El depolarizing es más dañino a igualdad de parámetro.
""")


# ═════════════════════════════════════════════════════════════════════════════
# EXPERIMENTO 13
# "Tamaño de sesión pequeño: la varianza estadística puede dar QBER=0"
# ═════════════════════════════════════════════════════════════════════════════
def exp13_statistical_variance():
    header("EXP 13 – Sesiones pequeñas: QBER=0 no significa canal perfecto")

    print("""
  HIPÓTESIS INGENUA: QBER=0 significa que el canal es perfecto.
  REALIDAD: con pocas muestras, es posible que NINGÚN error ocurra por azar,
  incluso con Eve activa. La varianza estadística domina.
  Solo con muchos pulsos el QBER converge a su valor real.
""")

    seeds = [42, 43, 44, 45, 46, 47, 48, 49, 50, 51]

    print("\n  Eve intercept_prob=0.25, múltiples seeds:\n")
    print(f"  {'pulses':>8} | {'seed':>5} | {'QBER':>8} | {'sifted':>8} | {'errors':>8}")
    print(f"  {'-'*8} | {'-'*5} | {'-'*8} | {'-'*8} | {'-'*8}")

    for n_pulses in [64, 256, 1_024, 8_192]:
        for seed in seeds[:4]:  # Solo 4 seeds por tamaño
            scenario = Scenario(
                pulses=n_pulses,
                clock_rate_hz=1_000_000.0,
                seed=seed,
                eavesdropper=EveConfig(kind="intercept_resend", intercept_probability=0.25),
                post_processing=PostProcessingConfig(qber_abort_threshold=None),
            )
            r = run(scenario)
            print(
                f"  {n_pulses:8d} | {seed:5d} | {qber_text(r)} | "
                f"{r['sifted']:8d} | {r['errors']:8d}"
            )
        print()

    print("""
  CONCLUSIÓN: con 64 pulsos y QBER teórico de 0.0625 (Eve al 25%),
  puede que no haya ningún error en la muestra sifted pequeña.
  Con 8192 pulsos el QBER converge a ≈0.0625. La clave: más pulsos = más
  confianza estadística. En QKD real se usan millones de pulsos.
""")


# ═════════════════════════════════════════════════════════════════════════════
# EXPERIMENTO 14
# "El secreto de la clave vacía: abort por QBER alto pero sifted≠0"
# ═════════════════════════════════════════════════════════════════════════════
def exp14_abort_vs_zero_key():
    header("EXP 14 – Abort ≠ clave cero: distinguir aborto de clave vacía legítima")

    print("""
  HIPÓTESIS INGENUA: secret_key_rate_bps=0 siempre significa que algo salió mal.
  REALIDAD: puede ocurrir de dos formas muy distintas:
  (a) ABORT: QBER > umbral → protocolo abortado por seguridad.
  (b) QBER alto pero < umbral → secret_fraction ≤ 0 matemáticamente.
  (c) Sifted=0 → no hay bits con los que trabajar.
  Estos tres casos son físicamente distintos pero dan el mismo resultado.
""")

    base_kwargs = dict(
        pulses=4_000,
        clock_rate_hz=1_000_000.0,
        seed=1300,
    )

    print(f"\n  {'escenario':<40} | {'QBER':>8} | {'sifted':>8} | "
          f"{'secret_bps':>12} | {'abort':>6}")
    print(f"  {'-'*40} | {'-'*8} | {'-'*8} | {'-'*12} | {'-'*6}")

    cases = [
        ("ideal (clave normal)", Scenario(
            **base_kwargs,
            post_processing=PostProcessingConfig(qber_abort_threshold=0.11),
        )),
        ("Eve 100% (ABORT por QBER)", Scenario(
            **base_kwargs,
            eavesdropper=EveConfig(kind="intercept_resend", intercept_probability=1.0),
            post_processing=PostProcessingConfig(qber_abort_threshold=0.11),
        )),
        ("prep_err=0.09 (QBER<thr, sk≈0)", Scenario(
            **base_kwargs,
            source=SourceConfig(preparation_error_probability=0.09),
            post_processing=PostProcessingConfig(
                qber_abort_threshold=0.11,
                error_correction_efficiency=1.16,
            ),
        )),
        ("fiber 200km (sifted=0)", Scenario(
            **base_kwargs,
            channel=ChannelConfig(kind="fiber", distance_km=200.0, attenuation_db_km=0.2),
            detector=DetectorConfig(kind="threshold", efficiency=0.5),
            post_processing=PostProcessingConfig(qber_abort_threshold=0.11),
        )),
        ("umbral=None (nunca aborta)", Scenario(
            **base_kwargs,
            eavesdropper=EveConfig(kind="intercept_resend", intercept_probability=1.0),
            post_processing=PostProcessingConfig(qber_abort_threshold=None),
        )),
    ]

    for label, scenario in cases:
        r = run(scenario)
        abort_str = "   YES" if r["abort"] else "    no"
        print(
            f"  {label:<40} | {qber_text(r)} | {r['sifted']:8d} | "
            f"{rate_text(r)} | {abort_str}"
        )

    print("""
  CONCLUSIÓN: el caso "umbral=None" es instructivo: un protocolo sin umbral
  de aborto nunca detecta a Eve → sigue generando "clave" aunque todo esté
  comprometido. La clave generada con Eve al 100% y sin aborto es completamente
  conocida por Eve, aunque parezca que el protocolo funcionó.
""")


# ═════════════════════════════════════════════════════════════════════════════
# EXPERIMENTO 15
# "Decoy vacuum: el pulso vacío revela información sobre Eve"
# ═════════════════════════════════════════════════════════════════════════════
def exp15_decoy_vacuum_gain():
    header("EXP 15 – Decoy vacuum: el pulso sin fotones detecta 'clicks fantasma'")

    print("""
  HIPÓTESIS INGENUA: un pulso vacío (μ=0) no puede generar ninguna detección.
  REALIDAD: dark counts y background radiation generan clicks incluso sin señal.
  El gain del vacuum state estima la probabilidad de clic de fondo por ventana.
  Eve no puede reducir el dark count local de Bob limitándose a «bloquear» un
  pulso que ya estaba vacío; una inyección de luz sí podría elevar este gain.
""")

    base_kwargs = dict(
        pulses=2_000,
        clock_rate_hz=1_000_000.0,
        seed=1400,
        channel=ChannelConfig(kind="fiber", distance_km=5.0, attenuation_db_km=0.2),
        post_processing=PostProcessingConfig(qber_abort_threshold=None),
    )

    print(f"\n  {'dark_count_hz':>14} | {'bg_hz':>10} | "
          f"{'vac_gain':>10} | {'sig_gain':>10} | {'vac_detected':>13}")
    print(f"  {'-'*14} | {'-'*10} | {'-'*10} | {'-'*10} | {'-'*13}")

    for dark_hz, bg_hz in [
        (0,       0),
        (100,     0),
        (1_000,   0),
        (10_000,  0),
        (100_000, 0),
        (0,       100_000),
        (50_000,  50_000),
    ]:
        scenario = Scenario(
            **base_kwargs,
            source=SourceConfig(
                kind="weak_coherent",
                decoy_intensities=(
                    DecoyIntensity("signal", mean_photon_number=0.6,
                                  selection_probability=0.7),
                    DecoyIntensity("decoy",  mean_photon_number=0.1,
                                  selection_probability=0.2),
                    DecoyIntensity("vacuum", mean_photon_number=0.0,
                                  selection_probability=0.1),
                ),
            ),
            channel=ChannelConfig(
                kind="fiber",
                distance_km=5.0,
                attenuation_db_km=0.2,
                background_count_rate_hz=bg_hz,
            ),
            detector=DetectorConfig(
                kind="threshold",
                efficiency=0.7,
                dark_count_rate_hz=dark_hz,
                gate_width_s=1e-9,
            ),
        )
        result = run_result(scenario)
        vac = result.decoy.get("vacuum", {})
        sig = result.decoy.get("signal", {})
        vac_gain = vac.get("gain", 0.0)
        sig_gain = sig.get("gain", 0.0)
        vac_det = vac.get("detected", 0)
        print(
            f"  {dark_hz:14.0f} | {bg_hz:10.0f} | "
            f"{vac_gain:10.6f} | {sig_gain:10.6f} | {vac_det:13d}"
        )

    print("""
  CONCLUSIÓN: para probabilidades pequeñas, el gain de vacío se aproxima por
  (dark_count_rate + background_rate) * gate_width; la expresión exacta del
  modelo combina las probabilidades de no-clic. Este observable permite
  estimar el fondo, pero no identifica por sí solo su causa.
""")


# ═════════════════════════════════════════════════════════════════════════════
# EXPERIMENTO 16
# "Depolarizing completo: tras el cribado, QBER tiende a 50%"
# ═════════════════════════════════════════════════════════════════════════════
def exp16_full_depolar_qber():
    header("EXP 16 – Depolarizing total: QBER post-cribado cercana a 50%")

    print("""
  HIPÓTESIS INGENUA: si el canal despolariza completamente (p=1), todos los
  bits serán erróneos → QBER=1.0.
  REALIDAD: el canal despolarizante con p=1 produce una mezcla completa:
  ρ → I/2 (mezcla máxima). Medir I/2 en cualquier base da 50/50 aleatoriamente.
  Después de conservar únicamente las bases coincidentes, la mitad de esos
  resultados discrepa de Alice → QBER post-cribado ≈ 0.5.

  (Esto se observa en el simulador Aer. En el modelo clásico el efecto puede
   diferir ligeramente según la implementación.)
""")

    base_kwargs = dict(
        pulses=2_000,
        clock_rate_hz=1_000_000.0,
        seed=1600,
        post_processing=PostProcessingConfig(qber_abort_threshold=None),
    )

    print(f"\n  {'depolar_prob':>13} | {'QBER':>8} | {'sifted':>8} | {'secret_bps':>12}")
    print(f"  {'-'*13} | {'-'*8} | {'-'*8} | {'-'*12}")

    for p in [0.0, 0.1, 0.25, 0.5, 0.75, 1.0]:
        scenario = Scenario(
            **base_kwargs,
            channel=ChannelConfig(depolarizing_probability=p),
        )
        r = run(scenario)
        show(f"depolarizing={p:.2f}", r)

    print("""
  CONCLUSIÓN: con depolarizing_probability=1.0 el estado es completamente
  mixto → probabilidad 1/2 en cada medición → QBER post-cribado ≈ 0.5. Esto no
  es equivalente a interceptar y reenviar todos los pulsos: ese ataque produce
  aproximadamente 0.25 de QBER y, además, deja información y metadatos de Eve.
""")


# ═════════════════════════════════════════════════════════════════════════════
# EXPERIMENTO 17
# "Readout error vs depolarizing: mismo QBER, distinto mecanismo"
# ═════════════════════════════════════════════════════════════════════════════
def exp17_readout_vs_channel_noise():
    header("EXP 17 – Readout error del detector vs ruido del canal: mismo QBER, distinto origen")

    print("""
  HIPÓTESIS INGENUA: si el QBER es el mismo, el origen del error no importa.
  REALIDAD: el readout_error se aplica DESPUÉS de la medición cuántica
  (inversión clásica del bit), mientras el depolarizing ocurre DURANTE el
  transporte cuántico. Sus parámetros pueden ajustarse para producir una QBER
  agregada parecida, pero las distribuciones condicionadas y los metadatos no
  son idénticos. Una fórmula asintótica que solo recibe la QBER puede devolver
  el mismo diagnóstico; eso no hace equivalentes los procesos físicos.
""")

    base_kwargs = dict(
        pulses=2_000,
        clock_rate_hz=1_000_000.0,
        seed=1700,
        post_processing=PostProcessingConfig(qber_abort_threshold=None),
    )

    print(f"\n  {'origen_ruido':<35} | {'param':>6} | {'QBER':>8} | {'secret_bps':>12}")
    print(f"  {'-'*35} | {'-'*6} | {'-'*8} | {'-'*12}")

    for p in [0.0, 0.05, 0.10, 0.15, 0.20]:
        # Canal depolarizing
        s = Scenario(**base_kwargs,
                      channel=ChannelConfig(depolarizing_probability=p * 4))
        r = run(s)
        show(f"canal depolarizing (p={p*4:.2f})", r)

        # Readout error del detector
        s = Scenario(**base_kwargs,
                      detector=DetectorConfig(readout_error_probability=p))
        r = run(s)
        show(f"readout_error (p={p:.2f})", r)

        if p > 0:
            print()

    print("""
  CONCLUSIÓN: readout_error=0.05 ≈ depolarizing_prob=0.20 en términos de QBER.
  Esto se debe a que el readout_error afecta a los bits ya medidos, mientras
  el depolarizing rota el estado antes de medir. La equivalencia numérica es
  accidental: readout_error_prob p → QBER=p*(1-0)+... depende de la base.
""")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "artifacts" / "experimentos_inesperados",
        help="directorio para el artefacto reproducible JSON/CSV",
    )
    parser.add_argument("--no-artifacts", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    _ARTIFACT_ROWS.clear()
    _ARTIFACT_SCENARIOS.clear()
    if args.no_artifacts:
        print(
            "WARNING: --no-artifacts opt-out disables the reproducibility "
            "manifest and CSV for this run.",
            file=sys.stderr,
        )
    _configure_console_output()
    print(SEPARATOR)
    print("  SUITE DE EXPERIMENTOS BB84 – RESULTADOS INESPERADOS PERO EXPLICABLES")
    print(f"  {17} experimentos – protocolo QKD con Qiskit")
    print(SEPARATOR)

    experiments = [
        ("EXP 01", exp1_high_mu_kills_key),
        ("EXP 02", exp2_eve_qber_math),
        ("EXP 03", exp3_prep_error_mimics_eve),
        ("EXP 04", exp4_efficiency_dark_count_tradeoff),
        ("EXP 05", exp5_dead_time_saturation),
        ("EXP 06", exp6_afterpulse_ghost_clicks),
        ("EXP 07", exp7_polarization_rotation_surprise),
        ("EXP 08", exp8_timing_jitter_kills_gain),
        ("EXP 09", exp9_clock_drift_accumulates),
        ("EXP 10", exp10_no_sifting),
        ("EXP 11", exp11_background_radiation),
        ("EXP 12", exp12_phase_vs_depolar),
        ("EXP 13", exp13_statistical_variance),
        ("EXP 14", exp14_abort_vs_zero_key),
        ("EXP 15", exp15_decoy_vacuum_gain),
        ("EXP 16", exp16_full_depolar_qber),
        ("EXP 17", exp17_readout_vs_channel_noise),
    ]

    for tag, fn in experiments:
        try:
            fn()
        except Exception as exc:
            print(f"\n  [{tag}] ERROR: {exc}\n")

    print(f"\n{SEPARATOR}")
    print("  FIN DE LA SUITE DE EXPERIMENTOS")
    print(SEPARATOR)
    if not args.no_artifacts:
        try:
            paths = write_artifact(
                args.output_dir,
                name="experimentos_inesperados",
                rows=_ARTIFACT_ROWS,
                scenarios=_ARTIFACT_SCENARIOS,
                generator_path=__file__,
                command=[sys.executable, __file__, *sys.argv[1:]],
            )
            print(f"\nArtifact: {paths.manifest}")
            print(f"CSV: {paths.csv}")
        except OSError as exc:
            print(f"\nNo se pudo escribir el artefacto: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
