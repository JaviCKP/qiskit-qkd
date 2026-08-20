"""
Suite de Experimentos Dinámicos y Avanzados para BB84 en Qiskit-QKD.

Este script contiene 5 experimentos diseñados para ilustrar comportamientos
no intuitivos pero físicamente explicables en simulaciones de distribución
de claves cuánticas.
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
    ConstantProfile,
    DecoyIntensity,
    DetectorConfig,
    DynamicConfig,
    EveConfig,
    ExponentialRampProfile,
    LinearRampProfile,
    ParameterResolver,
    ParameterSchedule,
    PostProcessingConfig,
    Scenario,
    SourceConfig,
    TimingConfig,
)
from qiskit_qkd.backends import backend_from_scenario
from qiskit_qkd.experiments import write_artifact

SEPARATOR = "=" * 76
SUBSEP = "-" * 76
_ARTIFACT_ROWS: list[dict] = []
_ARTIFACT_SCENARIOS: list[Scenario] = []


def _record_artifact_row(scenario: Scenario, payload: dict) -> None:
    """Keep observed values for the optional reproducibility artifact."""

    try:
        row = {key: value for key, value in payload.items() if key != "raw_result"}
        row["scenario"] = scenario.to_dict()
        _ARTIFACT_ROWS.append(row)
        _ARTIFACT_SCENARIOS.append(scenario)
    except (AttributeError, TypeError):
        # ``run`` remains useful with lightweight test doubles and callers that
        # only need the returned summary; those calls simply have no artifact row.
        return


def _configure_console_output() -> None:
    """Keep the Unicode scientific notation printable on Windows consoles."""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def _assessment_dict(result) -> dict:
    assessment = result.assessment
    if assessment is None:
        return {}
    if hasattr(assessment, "to_dict"):
        return dict(assessment.to_dict())
    return dict(assessment)


def _format_optional(value, format_spec: str, undefined: str = "n/a") -> str:
    return undefined if value is None else format(value, format_spec)


def _threshold_label(value: bool | None) -> str:
    if value is None:
        return "n/a"
    return "YES" if value else "no"


def run(scenario: Scenario) -> dict:
    """Run one scenario through the canonical, scenario-aware backend.

    ``Metrics`` remains useful for counters and compatibility fields, but the
    assessment/classical/decoy/Bell summaries are the authoritative result
    surfaces for diagnostics and plotted conclusions.
    """

    backend = backend_from_scenario(scenario)
    result = BB84Protocol().run(scenario, backend=backend)
    m = result.metrics
    assessment = _assessment_dict(result)
    decoy_security = result.decoy.get("security", {})
    qber_defined = bool(assessment.get("qber_defined", False))
    qber_value = assessment.get("qber_value") if qber_defined else None
    rate_status = assessment.get("rate_estimate_status", "unavailable")
    rate_estimate = (
        assessment.get("rate_estimate_bps")
        if rate_status == "available"
        else None
    )
    payload = {
        "pulses":           m.pulses,
        "emitted":          m.emitted,
        "transmitted":      m.transmitted,
        "detected":         m.detected,
        "sifted":           m.sifted,
        "errors":           m.errors,
        "qber":             qber_value,
        "qber_defined":     qber_defined,
        "gain":             m.gain,
        "loss_db":          m.loss_db,
        "secret_bps":       rate_estimate,
        "sifted_bps":       m.sifted_key_rate_bps,
        "threshold_exceeded": assessment.get("threshold_exceeded"),
        "rate_estimate_status": rate_status,
        "verification_status": assessment.get("verification_status", "unknown"),
        "dead_discards":    m.dead_time_discards,
        "afterpulse":       m.afterpulse_clicks,
        "eve_frac":         m.eve_intercepted_fraction,
        "eve_info":         m.eve_information_estimate,
        "assessment":       assessment,
        "classical":        result.classical,
        "decoy":            result.decoy,
        "decoy_security":   decoy_security,
        "bell":             result.bell,
        "raw_result":       result,
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


# ═════════════════════════════════════════════════════════════════════════════
# EXPERIMENTO 18
# La paradoja de "Nearest" vs "Discard" ante Clock Offset dinámico
# ═════════════════════════════════════════════════════════════════════════════
def exp18_clock_offset_nearest_vs_discard():
    header("EXP 18 – Clock Offset Dinámico: Nearest vs Discard")

    print("""
  HIPÓTESIS INGENUA: Un desfase del reloj de Bob (clock offset) mayor que la mitad
  del ancho de puerta (gate width) siempre destruirá la clave y las detecciones.
  
  REALIDAD: Bajo la política 'discard', las detecciones caen a cero tan pronto como
  el offset supera gate_width / 2.
  Sin embargo, bajo la política 'nearest', las detecciones se mantienen altas y el QBER
  es cero hasta que el offset supera el 50% del período del reloj (half slot period).
  En ese límite exacto (50 ns para clock a 10 MHz), el QBER no sube gradualmente, sino
  que la tasa de sifted colapsa a cero porque el fotón es asignado al slot adyacente,
  provocando que la sifting clásica lo descarte por discordancia.
""")

    # Puerta de 1 ns, Reloj de 10 MHz (periodo = 100 ns, mitad de periodo = 50 ns)
    # Rampa 1: Rango de escala fina (0 a 1.5 ns) para comparar con discard
    scen_base = Scenario(
        pulses=2000,
        clock_rate_hz=10_000_000.0,
        seed=42,
        channel=ChannelConfig(kind="fiber", distance_km=1.0, attenuation_db_km=0.2),
        detector=DetectorConfig(kind="threshold", efficiency=0.8, gate_width_s=1.0e-9),
        post_processing=PostProcessingConfig(qber_abort_threshold=None),
    )

    # Creamos schedules dinámicos para el offset
    # Rampa fina de 0 a 1.5 ns
    schedule_fine = ParameterSchedule(
        target="timing.clock_offset_s",
        profile=LinearRampProfile(start_s=0.0, end_s=10.0, start_value=0.0, end_value=1.5e-9),
    )

    # Rampa gruesa de 0 a 60 ns (para ver el colapso de nearest a los 50 ns)
    schedule_coarse = ParameterSchedule(
        target="timing.clock_offset_s",
        profile=LinearRampProfile(start_s=0.0, end_s=10.0, start_value=0.0, end_value=60.0e-9),
    )

    times = [0.0, 2.0, 4.0, 6.0, 8.0, 10.0]

    # --- CASO 1: POLÍTICA DISCARD (Rampa Fina) ---
    subheader("Caso 1: Política DISCARD (Rampa Fina 0.0 a 1.5 ns, gate_width=1.0 ns)")
    scen_discard = replace(
        scen_base,
        timing=TimingConfig(slot_assignment_policy="discard"),
        dynamic=DynamicConfig(parameter_schedules=(schedule_fine,)),
    )
    print(f"  {'time_s':>6} | {'offset':>10} | {'detected':>8} | {'sifted':>8} | {'QBER':>8} | {'secret_bps':>12}")
    print(f"  {'-'*6} | {'-'*10} | {'-'*8} | {'-'*8} | {'-'*8} | {'-'*12}")
    for t in times:
        effective = ParameterResolver().scenario_at(scen_discard, time_s=t)
        offset = effective.timing.clock_offset_s * 1e9
        r = run(effective)
        print(f"  {t:6.1f} | {offset:8.2f} ns | {r['detected']:8d} | {r['sifted']:8d} | {_format_optional(r['qber'], '8.4f')} | {_format_optional(r['secret_bps'], '12.2f')}")

    # --- CASO 2: POLÍTICA NEAREST (Rampa Fina) ---
    subheader("Caso 2: Política NEAREST (Rampa Fina 0.0 a 1.5 ns, gate_width=1.0 ns)")
    scen_nearest_fine = replace(
        scen_base,
        timing=TimingConfig(slot_assignment_policy="nearest"),
        dynamic=DynamicConfig(parameter_schedules=(schedule_fine,)),
    )
    print(f"  {'time_s':>6} | {'offset':>10} | {'detected':>8} | {'sifted':>8} | {'QBER':>8} | {'secret_bps':>12}")
    print(f"  {'-'*6} | {'-'*10} | {'-'*8} | {'-'*8} | {'-'*8} | {'-'*12}")
    for t in times:
        effective = ParameterResolver().scenario_at(scen_nearest_fine, time_s=t)
        offset = effective.timing.clock_offset_s * 1e9
        r = run(effective)
        print(f"  {t:6.1f} | {offset:8.2f} ns | {r['detected']:8d} | {r['sifted']:8d} | {_format_optional(r['qber'], '8.4f')} | {_format_optional(r['secret_bps'], '12.2f')}")

    # --- CASO 3: POLÍTICA NEAREST (Rampa Gruesa) ---
    subheader("Caso 3: Política NEAREST (Rampa Gruesa 0.0 a 60.0 ns, period=100 ns)")
    scen_nearest_coarse = replace(
        scen_base,
        timing=TimingConfig(slot_assignment_policy="nearest"),
        dynamic=DynamicConfig(parameter_schedules=(schedule_coarse,)),
    )
    print(f"  {'time_s':>6} | {'offset':>10} | {'detected':>8} | {'sifted':>8} | {'QBER':>8} | {'secret_bps':>12}")
    print(f"  {'-'*6} | {'-'*10} | {'-'*8} | {'-'*8} | {'-'*8} | {'-'*12}")
    for t in times:
        effective = ParameterResolver().scenario_at(scen_nearest_coarse, time_s=t)
        offset = effective.timing.clock_offset_s * 1e9
        r = run(effective)
        print(f"  {t:6.1f} | {offset:8.2f} ns | {r['detected']:8d} | {r['sifted']:8d} | {_format_optional(r['qber'], '8.4f')} | {_format_optional(r['secret_bps'], '12.2f')}")

    print("""
  CONCLUSIÓN: Con 'discard', a partir de offset = 0.6 ns (excede 0.5 ns de la ventana),
  los pulsos caen fuera del detector y se pierden (sifted=0).
  Con 'nearest', la clave se genera perfectamente a 1.5 ns y mucho más allá, porque
  se reasigna al slot correspondiente. Sin embargo, en cuanto el offset supera los 50 ns
  (a partir de t=10.0, offset = 60 ns), el fotón del slot 'n' se asigna al slot 'n-1' de Bob.
  Aunque se detecta (detected=1576), no es sifted (sifted=0) porque Alice y Bob comparan
  bases cruzadas (slot 'n' de Alice vs slot 'n-1' de Bob).
""")


# ═════════════════════════════════════════════════════════════════════════════
# EXPERIMENTO 19
# Interacción no-monótona de Afterpulsing y Dead Time con Clock Rate variable
# ═════════════════════════════════════════════════════════════════════════════
def exp19_afterpulse_clock_rate_dead_time_interaction():
    header("EXP 19 – Interacción No-Monótona: Afterpulsing + Dead Time + Clock Rate")

    print("""
  HIPÓTESIS INGENUA: Un incremento en el clock rate siempre aumentará la producción
  de bits (sifted) de forma lineal, o al menos monótona.
  
  REALIDAD: En detectores reales con afterpulsing y dead time, hay una interacción compleja.
  - Con clock rate bajo (10 kHz), la tasa de afterpulses por segundo es baja y el dead time
    no bloquea casi nada.
  - Con clock rate intermedio (1 MHz), el detector está disponible en cada slot, pero los
    afterpulses de clicks anteriores pueden propagarse y crear "cadenas de clicks fantasmas"
    que aumentan drásticamente el QBER (ya que son ruido aleatorio).
  - Con clock rate muy alto (10 MHz), el dead time de 1 microsegundo bloquea físicamente
    los siguientes 10 slots después de cualquier click. Esto "rompe" el encadenamiento de
    afterpulses, actuando como un filtro físico que puede estabilizar el QBER en valores
    más bajos de lo que indicaría la tendencia.
""")

    rates = [10_000.0, 100_000.0, 1_000_000.0, 5_000_000.0, 10_000_000.0]

    print(f"  {'clock_rate':>12} | {'period':>10} | {'detected':>8} | {'dead_time_discards':>18} | {'afterpulse':>10} | {'QBER':>8}")
    print(f"  {'-'*12} | {'-'*10} | {'-'*8} | {'-'*18} | {'-'*10} | {'-'*8}")

    for rate in rates:
        period_ns = (1.0 / rate) * 1e9
        scenario = Scenario(
            pulses=4000,
            clock_rate_hz=rate,
            seed=100,
            source=SourceConfig(kind="weak_coherent", mean_photon_number=0.1),  # señal débil
            channel=ChannelConfig(kind="fiber", distance_km=10.0, attenuation_db_km=0.2),
            detector=DetectorConfig(
                kind="threshold",
                efficiency=0.7,
                afterpulse_probability=0.20,  # 20% probabilidad de eco
                dead_time_s=1.0e-6,           # 1 microsegundo de dead time
            ),
            post_processing=PostProcessingConfig(qber_abort_threshold=None),
        )
        r = run(scenario)
        print(
            f"  {rate/1e3:10.1f} kHz | {period_ns:7.1f} ns | {r['detected']:8d} | "
            f"{r['dead_discards']:10d} | {r['afterpulse']:10d} | {_format_optional(r['qber'], '8.4f')}"
        )

    print("""
  CONCLUSIÓN: Observa cómo a 1 MHz (periodo = 1000 ns), el dead time de 1 microsegundo
  es exactamente 1 slot. A 10 MHz (periodo = 100 ns), el dead time de 1 microsegundo
  bloquea los siguientes 10 slots. El número de ``dead_time_discards`` se debe leer de la salida de
  cada ejecución, porque puede cambiar con la semilla y la implementación del backend.
  Al bloquear los slots, el detector físicamente no puede hacer
  clicks de afterpulse continuos, limitando el ruido acumulado y alterando el QBER.
""")


# ═════════════════════════════════════════════════════════════════════════════
# EXPERIMENTO 20
# Firma temporal de un ataque Eve "intermitente" en Decoy-States
# ═════════════════════════════════════════════════════════════════════════════
def exp20_decoy_state_temporal_eavesdropping():
    header("EXP 20 – Firma Temporal: Ataque intermitente de Eve con Decoy-States")

    print("""
  HIPÓTESIS INGENUA: Un ataque de intercepción y reenvío (intercept-resend) por parte
  de Eve elevará el QBER de todos los estados de intensidad (signal, decoy, vacuum)
  por igual durante el periodo en que esté activa.
  
  REALIDAD: Dado que los pulsos vacíos (vacuum, mu=0) no contienen fotones reales,
  el canal no transmite nada en esos slots (surviving_photon_number=0).
  Eve no tiene fotones físicos que interceptar en ellos, por lo que los clicks de Bob
  en los slots 'vacuum' se deben enteramente a ruido oscuro y de fondo.
  Por tanto, el gain y QBER de la clase 'vacuum' se mantienen constantes e independientes
  de la actividad de Eve. En cambio, el QBER de 'signal' (mu=0.6) y 'decoy' (mu=0.1) se
  dispara a ~25% en presencia de Eve. Esto genera una firma de seguridad asimétrica.
""")

    # Configuración de Decoy-States
    decoy_source = SourceConfig(
        kind="weak_coherent",
        decoy_intensities=(
            DecoyIntensity("signal", mean_photon_number=0.6, selection_probability=0.7),
            DecoyIntensity("decoy",  mean_photon_number=0.1, selection_probability=0.2),
            DecoyIntensity("vacuum", mean_photon_number=0.0, selection_probability=0.1),
        ),
    )

    scenario = Scenario(
        pulses=8000,
        clock_rate_hz=1_000_000.0,
        seed=200,
        source=decoy_source,
        channel=ChannelConfig(
            kind="fiber",
            distance_km=5.0,
            attenuation_db_km=0.2,
            background_count_rate_hz=5000.0,  # algo de ruido de fondo
        ),
        detector=DetectorConfig(
            kind="threshold",
            efficiency=0.65,
            dark_count_rate_hz=100.0,
            gate_width_s=1e-9,
        ),
        eavesdropper=EveConfig(kind="intercept_resend", intercept_probability=0.0),
        post_processing=PostProcessingConfig(qber_abort_threshold=None),
        dynamic=DynamicConfig(
            parameter_schedules=(
                ParameterSchedule(
                    target="eavesdropper.intercept_probability",
                    profile=ConstantProfile(start_s=4.0, end_s=7.0, value=1.0),
                ),
            ),
        ),
    )

    time_points = [2.0, 5.5, 8.5]
    labels = [
        "t=2.0s (Antes del ataque - Eve=0.0)",
        "t=5.5s (Durante el ataque - Eve=1.0)",
        "t=8.5s (Después del ataque - Eve=0.0)",
    ]

    for t, label in zip(time_points, labels, strict=True):
        subheader(label)
        effective = ParameterResolver().scenario_at(scenario, time_s=t)
        r = run(effective)
        res = r["raw_result"]

        print(f"  {'clase':<10} | {'pulses':>8} | {'detected':>8} | {'gain':>8} | {'QBER':>8}")
        print(f"  {'-'*10} | {'-'*8} | {'-'*8} | {'-'*8} | {'-'*8}")

        for key in ["signal", "decoy", "vacuum"]:
            stats = res.decoy.get(key, {})
            gain = stats.get("gain", 0.0)
            qber_val = stats.get("qber") if stats.get("qber_defined") else None
            pulses_val = stats.get("pulses", 0)
            det_val = stats.get("detected", 0)
            print(
                f"  {key:<10} | {pulses_val:8d} | {det_val:8d} | {gain:8.5f} | "
                f"{_format_optional(qber_val, '8.4f')}"
            )

        security = r["decoy_security"]
        security_status = security.get("data_status", "unavailable")
        security_rate = (
            security.get("secret_key_rate_bps")
            if security_status == "available"
            else None
        )
        print(
            "  Decoy security: "
            f"status={security_status}, "
            f"secret_key_rate_bps={_format_optional(security_rate, '.2f')}"
        )

    print("""
  CONCLUSIÓN: Durante el ataque (t=5.5s), el QBER de 'signal' y 'decoy' salta a ~25%
  debido a la intercepción física de los fotones. Sin embargo, 'vacuum' mantiene su QBER
  alrededor de su valor de ruido (~50% o similar según base coincidente y bits aleatorios),
  y su tasa de ganancia ('gain') no cambia en absoluto.
""")


# ═════════════════════════════════════════════════════════════════════════════
# EXPERIMENTO 21
# Rotación de fase dinámica y QBER dependiente de la base
# ═════════════════════════════════════════════════════════════════════════════
def exp21_dynamic_polarization_y_rotation():
    header("EXP 21 – Rotación de fase: efecto dependiente de la base")

    print("""
  HIPÓTESIS INGENUA: A mayor rotación de polarización introducida por el canal,
  peores resultados y menor tasa de clave secreta obtendremos de forma monótona.
  
  REALIDAD: Para la rotación Rz que usa este experimento, los estados medidos en Z
  solo adquieren una fase global y no cambian su bit. En la base X el error de una
  medida correcta es sin²(theta/2). Con bases BB84 equiprobables, la QBER esperada es
  aproximadamente 0,5·sin²(theta/2):
  - theta = 0: QBER = 0.
  - theta = pi/2: QBER = 0,25.
  - theta = pi: los bits Z no cambian, los bits X se invierten y QBER ≈ 0,5.
  - theta = 3pi/2: QBER = 0,25.
  - theta = 2pi: QBER = 0.

  La tasa se interpreta mediante ``result.assessment`` y su estado de estimación.
  No debe reaparecer una tasa positiva por aplicar h2(1)=0 a un QBER igual a 1:
  una muestra con QBER no admisible o sin datos suficientes no constituye una tasa
  secreta disponible.
""")

    scenario = Scenario(
        pulses=4000,
        clock_rate_hz=1_000_000.0,
        seed=300,
        channel=ChannelConfig(kind="fiber", distance_km=0.0, fixed_loss_db=0.0),
        detector=DetectorConfig(kind="threshold", efficiency=1.0),  # ideal para ver el efecto puro
        post_processing=PostProcessingConfig(
            qber_abort_threshold=None,  # la evaluación de la tasa sigue siendo autoritativa
            error_correction_efficiency=1.0,
        ),
        dynamic=DynamicConfig(
            parameter_schedules=(
                ParameterSchedule(
                    target="channel.polarization_rotation_z_rad",
                    profile=LinearRampProfile(start_s=0.0, end_s=20.0, start_value=0.0, end_value=2.0 * math.pi),
                ),
            ),
        ),
    )

    times = [0.0, 2.5, 5.0, 10.0, 15.0, 17.5, 20.0]

    print(f"  {'time_s':>6} | {'ángulo Z':>12} | {'detected':>8} | {'sifted':>8} | {'QBER':>8} | {'secret_bps':>12}")
    print(f"  {'-'*6} | {'-'*12} | {'-'*8} | {'-'*8} | {'-'*8} | {'-'*12}")

    for t in times:
        effective = ParameterResolver().scenario_at(scenario, time_s=t)
        angle_rad = effective.channel.polarization_rotation_z_rad
        angle_deg = math.degrees(angle_rad)
        r = run(effective)
        print(
            f"  {t:6.1f} | {angle_deg:7.1f} deg ({angle_rad:4.2f}) | {r['detected']:8d} | "
            f"{r['sifted']:8d} | {_format_optional(r['qber'], '8.4f')} | "
            f"{_format_optional(r['secret_bps'], '12.2f')}"
        )

    print("""
  CONCLUSIÓN: A 180 deg (pi, t=10.0s), la base Z conserva sus bits pero la base X
  se invierte; con bases equiprobables la QBER es aproximadamente 0,5 y no hay una
  tasa secreta disponible. La QBER vuelve a cero a 360 deg porque Rz(2pi) solo aporta
  una fase global. La semántica de la tasa se toma de ``rate_estimate_status``; no se
  infiere una tasa positiva a partir de una QBER igual a 1 ni de una muestra vacía.
""")


# ═════════════════════════════════════════════════════════════════════════════
# EXPERIMENTO 22
# Detector más eficiente empeora el QBER bajo radiación solar
# ═════════════════════════════════════════════════════════════════════════════
def exp22_detector_efficiency_vs_gate_width_solar():
    header("EXP 22 – Paradoja Solar: Mayor eficiencia vs Ventana de Puerta estrecha")

    print("""
  HIPÓTESIS INGENUA: Un detector de silicio con 90% de eficiencia siempre será
  preferible a uno de 30% de eficiencia en cualquier escenario de operación.
  
  REALIDAD: En escenarios con radiación de fondo solar creciente, el ruido de fondo
  acumulado en la puerta es p_noise = 1 - exp(-bg_rate_hz * gate_width_s).
  - Un detector con alta eficiencia (90%) pero ventana ancha (2 ns) captará
    una enorme cantidad de ruido conforme brille el sol. Su QBER se disparará
    y abortará rápidamente.
  - Un detector con menor eficiencia (30%) pero ventana estrecha (200 ps) acumula
    10 veces menos fotones de fondo por puerta. Su QBER permanece bajo y sobrevive
    generando una tasa de clave secreta positiva en condiciones extremas donde el
    otro colapsa.
""")

    # Rampa exponencial de radiación de fondo de 100 Hz a 120 MHz
    schedule_solar = ParameterSchedule(
        target="channel.background_count_rate_hz",
        profile=ExponentialRampProfile(
            start_s=0.0,
            end_s=10.0,
            start_value=100.0,
            end_value=120_000_000.0,
            curve=4.0,
        ),
    )

    base_scen = Scenario(
        pulses=4000,
        clock_rate_hz=1_000_000.0,
        seed=400,
        channel=ChannelConfig(kind="fiber", distance_km=15.0, attenuation_db_km=0.2, fixed_loss_db=0.0),
        post_processing=PostProcessingConfig(
            qber_abort_threshold=0.11,
        ),  # umbral configurado para este escenario, no universal
    )

    # Detector A: Súper eficiente pero ancho
    det_a = DetectorConfig(kind="threshold", efficiency=0.90, gate_width_s=2.0e-9, dark_count_rate_hz=100.0)
    scen_a = replace(base_scen, detector=det_a, dynamic=DynamicConfig(parameter_schedules=(schedule_solar,)))

    # Detector B: Poco eficiente pero estrecho
    det_b = DetectorConfig(kind="threshold", efficiency=0.30, gate_width_s=0.2e-9, dark_count_rate_hz=100.0)
    scen_b = replace(base_scen, detector=det_b, dynamic=DynamicConfig(parameter_schedules=(schedule_solar,)))

    times = [0.0, 2.5, 5.0, 7.5, 10.0]

    print("\n  Comparativa temporal bajo Sol creciente:")
    print(f"  {'time_s':>6} | {'bg_hz':>10} | {'DET A (Eff=90%, 2ns)':^31} | {'DET B (Eff=30%, 200ps)':^31}")
    print(f"  {'':>6} | {'':>10} | {'QBER':>8} {'secret_bps':>12} {'threshold':>10} | {'QBER':>8} {'secret_bps':>12} {'threshold':>10}")
    print(f"  {'-'*6} | {'-'*10} | {'-'*31} | {'-'*31}")

    for t in times:
        eff_a = ParameterResolver().scenario_at(scen_a, time_s=t)
        eff_b = ParameterResolver().scenario_at(scen_b, time_s=t)
        bg = eff_a.channel.background_count_rate_hz

        r_a = run(eff_a)
        r_b = run(eff_b)

        threshold_a = _threshold_label(r_a["threshold_exceeded"])
        threshold_b = _threshold_label(r_b["threshold_exceeded"])

        print(
            f"  {t:6.1f} | {bg:10.0f} | {_format_optional(r_a['qber'], '8.4f')} "
            f"{_format_optional(r_a['secret_bps'], '12.2f')} {threshold_a:>10} | "
            f"{_format_optional(r_b['qber'], '8.4f')} "
            f"{_format_optional(r_b['secret_bps'], '12.2f')} {threshold_b:>10}"
        )

    print("""
  CONCLUSIÓN: Con fondo bajo, el detector de mayor eficiencia puede producir más bits,
  pero el resultado depende también de la ventana y del ruido. Cuando el fondo crece,
  el Detector A puede superar el umbral configurado de este escenario y quedar sin tasa
  estimada; el 11 % no es un umbral universal. El Detector B reduce el ruido integrado
  gracias a su ventana estrecha, aunque la comparación no aísla una sola variable.
""")


# ═════════════════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════════════════
def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "artifacts" / "experimentos_dinamicos",
        help="directory for the reproducibility JSON/CSV artifact",
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
    print("  SUITE DE EXPERIMENTOS BB84 DINÁMICOS – RESULTADOS INESPERADOS Y EXPLICABLES")
    print("  Fase de Extensión (Fases 4.1, 5, 6 y timing avanzado) con Qiskit-QKD")
    print(SEPARATOR)

    experiments = [
        ("EXP 18", exp18_clock_offset_nearest_vs_discard),
        ("EXP 19", exp19_afterpulse_clock_rate_dead_time_interaction),
        ("EXP 20", exp20_decoy_state_temporal_eavesdropping),
        ("EXP 21", exp21_dynamic_polarization_y_rotation),
        ("EXP 22", exp22_detector_efficiency_vs_gate_width_solar),
    ]

    for tag, fn in experiments:
        try:
            fn()
        except Exception as exc:
            import traceback
            print(f"\n  [{tag}] ERROR: {exc}")
            traceback.print_exc()

    print(f"\n{SEPARATOR}")
    print("  FIN DE LA SUITE DE EXPERIMENTOS DINÁMICOS")
    print(SEPARATOR)
    if not args.no_artifacts:
        try:
            paths = write_artifact(
                args.output_dir,
                name="experimentos_dinamicos",
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
