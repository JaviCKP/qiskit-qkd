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

import math
from dataclasses import replace

from qiskit_qkd import (
    BB84Protocol,
    ChannelConfig,
    DecoyIntensity,
    DetectorConfig,
    EveConfig,
    PostProcessingConfig,
    QiskitSamplerBackend,
    Scenario,
    SourceConfig,
    TimingConfig,
)

SEPARATOR = "=" * 72
SUBSEP = "-" * 72

# ─────────────────────────────────────────────────────────────────────────────
# Utilidades
# ─────────────────────────────────────────────────────────────────────────────

def run(scenario: Scenario) -> dict:
    backend = QiskitSamplerBackend(
        seed=scenario.seed,
        max_circuits_per_job=512,
        max_recorded_results=0,
    )
    result = BB84Protocol().run(scenario, backend=backend)
    m = result.metrics
    return {
        "pulses":           m.pulses,
        "emitted":          m.emitted,
        "transmitted":      m.transmitted,
        "detected":         m.detected,
        "sifted":           m.sifted,
        "errors":           m.errors,
        "qber":             m.qber,
        "gain":             m.gain,
        "loss_db":          m.loss_db,
        "secret_bps":       m.secret_key_rate_bps,
        "sifted_bps":       m.sifted_key_rate_bps,
        "abort":            m.abort,
        "dead_discards":    m.dead_time_discards,
        "afterpulse":       m.afterpulse_clicks,
        "eve_frac":         m.eve_intercepted_fraction,
        "eve_info":         m.eve_information_estimate,
    }


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
    print(
        f"  {label:<38} | "
        f"QBER={r['qber']:6.4f} | "
        f"secret={r['secret_bps']:10.2f} bps | "
        f"sifted={r['sifted']:5d} | "
        f"gain={r['gain']:.5f}{abort_str}"
    )
    if notes:
        print(f"    ↳ {notes}")


# ═════════════════════════════════════════════════════════════════════════════
# EXPERIMENTO 1
# "Más fotones emitidos NO significa más clave secreta"
# Fuente coherente débil (WCS) con μ alto vs μ bajo
# ═════════════════════════════════════════════════════════════════════════════
def exp1_high_mu_kills_key():
    header("EXP 1 – μ alto destruye la clave (ataque PNS implícito)")

    print("""
  HIPÓTESIS INGENUA: cuantos más fotones enviemos, más clave obtendremos.
  REALIDAD: μ > 1 genera pulsos multi-fotón que Eve puede robar (PNS attack).
  La tasa de clave DISMINUYE con μ creciente aunque el gain sube.
""")

    base = dict(pulses=8_000, clock_rate_hz=1_000_000.0, seed=42)

    for mu in [0.05, 0.1, 0.3, 0.5, 0.7, 1.0, 2.0, 5.0]:
        scenario = Scenario(
            **base,
            source=SourceConfig(
                kind="weak_coherent",
                decoy_intensities=(
                    DecoyIntensity("signal", mean_photon_number=mu,
                                  selection_probability=1.0),
                ),
            ),
            channel=ChannelConfig(
                kind="fiber", distance_km=20.0, attenuation_db_km=0.2
            ),
            detector=DetectorConfig(kind="threshold", efficiency=0.85),
            post_processing=PostProcessingConfig(qber_abort_threshold=None),
        )
        r = run(scenario)
        multi_frac = 1 - math.exp(-mu) * (1 + mu)  # fracción multi-fotón Poisson
        show(
            f"μ={mu:.2f}",
            r,
            f"fracción multi-fotón≈{multi_frac:.3f}, gain={r['gain']:.4f}",
        )

    print("""
  CONCLUSIÓN: Aunque gain aumenta con μ, la fracción de pulsos multi-fotón
  que puede espiar Eve crece exponencialmente. El óptimo está en μ ≈ 0.1-0.5.
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
            f"  {p:12.2f} | {r['qber']:9.4f} | {teorico:13.4f} | "
            f"{abs(r['qber'] - teorico):10.4f}"
        )

    print("""
  CONCLUSIÓN: El QBER sigue exactamente Q = p_int/4 (ruido de fondo cero).
  Esto es sorprendente: interceptar el 100% solo introduce 25% de error.
  Por eso el umbral de aborto se fija en 11% (≡ p_int ≈ 44%).
""")


# ═════════════════════════════════════════════════════════════════════════════
# EXPERIMENTO 3
# "Ruido de preparación vs ruido de Eve: son indistinguibles"
# ═════════════════════════════════════════════════════════════════════════════
def exp3_prep_error_mimics_eve():
    header("EXP 3 – Error de preparación es indistinguible de ataque de Eve")

    print("""
  HIPÓTESIS INGENUA: Si Alice comete errores de preparación, Bob lo detecta.
  REALIDAD: preparation_error_probability produce EXACTAMENTE el mismo QBER
  que un ataque Eve con p_int = 4 * prep_error (ambos ~aleatorios por defecto).
  Alice no puede distinguir si sus errores son de equipo o de Eve.
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
        show(f"Eve p={p_eve:.2f} (equiv a prep={prep_err:.2f})", r)

    print("""
  CONCLUSIÓN: Alice y Bob no pueden distinguir errores de hardware de un
  ataque Eve. Necesitan un canal clásico autenticado para comparar paridades
  (reconciliación) y luego privacy amplification para eliminar la información
  que pudiera tener Eve de los errores de equipo.
""")


# ═════════════════════════════════════════════════════════════════════════════
# EXPERIMENTO 4
# "Detector más eficiente puede empeorar la clave con ruido oscuro"
# ═════════════════════════════════════════════════════════════════════════════
def exp4_efficiency_dark_count_tradeoff():
    header("EXP 4 – Eficiencia alta con dark counts eleva el QBER: la paradoja del detector")

    print("""
  HIPÓTESIS INGENUA: un detector con eficiencia 90% siempre es mejor que uno de 20%.
  REALIDAD: si la dark_count_rate_hz es alta, el ancho de puerta necesario para
  capturar fotones también sube la probabilidad de dark counts espúreos.
  Con eficiencia alta y dark counts altos, el QBER puede SUPERAR el umbral.
""")

    base_kwargs = dict(
        pulses=4_000,
        clock_rate_hz=1_000_000.0,
        seed=300,
        channel=ChannelConfig(kind="fiber", distance_km=50.0, attenuation_db_km=0.2),
        post_processing=PostProcessingConfig(qber_abort_threshold=0.11),
    )

    print(f"\n  {'efficiency':>11} | {'dark_hz':>10} | {'gate_ns':>7} | "
          f"{'QBER':>8} | {'secret_bps':>12} | {'abort':>5}")
    print(f"  {'-'*11} | {'-'*10} | {'-'*7} | {'-'*8} | {'-'*12} | {'-'*5}")

    configs = [
        (0.20, 100.0,        1e-9),
        (0.50, 100.0,        1e-9),
        (0.90, 100.0,        1e-9),
        (0.90, 10_000.0,     1e-9),
        (0.90, 100_000.0,    1e-9),
        (0.90, 1_000_000.0,  1e-9),
        (0.90, 1_000_000.0,  1e-8),   # ventana 10x más ancha = 10x más dark counts
    ]

    for eff, dark, gate in configs:
        scenario = Scenario(
            **base_kwargs,
            detector=DetectorConfig(
                kind="threshold",
                efficiency=eff,
                dark_count_rate_hz=dark,
                gate_width_s=gate,
            ),
        )
        r = run(scenario)
        abort_str = "  YES" if r["abort"] else "   no"
        print(
            f"  {eff:11.2f} | {dark:10.0f} | {gate*1e9:7.1f} | "
            f"{r['qber']:8.4f} | {r['secret_bps']:12.2f} | {abort_str}"
        )

    print("""
  CONCLUSIÓN: el gate_width_s importa tanto como la eficiencia. Doblar la
  ventana equivale a doblar el ruido oscuro efectivo. Hay un punto óptimo de
  compromiso entre detectar señales tardías y aceptar más ruido.
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
          f"{'gain':>8} | {'dead_discards':>14} | {'secret_bps':>12}")
    print(f"  {'-'*12} | {'-'*12} | {'-'*8} | {'-'*14} | {'-'*12}")

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
            f"{r['gain']:8.5f} | {r['dead_discards']:14d} | "
            f"{r['secret_bps']:12.2f}"
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
            f"  {ap:16.2f} | {r['qber']:8.4f} | {r['afterpulse']:11d} | "
            f"{r['sifted']:8d} | {r['secret_bps']:12.2f} | {abort_str}"
        )

    print("""
  CONCLUSIÓN: afterpulse_probability=0.80 puede parecer poco realista, pero
  incluso al 5-10% el QBER ya aumenta significativamente. Este es un efecto
  real en detectores de avalancha (SPAD/APD) a bajas temperaturas.
""")


# ═════════════════════════════════════════════════════════════════════════════
# EXPERIMENTO 7
# "La rotación de polarización π/2 (90°) destruye la clave, pero π (180°) NO"
# ═════════════════════════════════════════════════════════════════════════════
def exp7_polarization_rotation_surprise():
    header("EXP 7 – Rotación de polarización: π/2 destroys key, pero π es inofensiva!")

    print("""
  HIPÓTESIS INGENUA: cualquier rotación de polarización introduce errores.
  REALIDAD: una rotación de π (180°) en Y invierte todos los bits → QBER=0.5.
  PERO una rotación de π (180°) en Z solo cambia la fase global → QBER≈0.
  La rotación Y de π/4 (45°) mezcla las bases Z y X → QBER máximo.

  (polarization_rotation_y_rad rota sobre eje Y del bloch sphere)
""")

    base_kwargs = dict(
        pulses=4_000,
        clock_rate_hz=1_000_000.0,
        seed=600,
        post_processing=PostProcessingConfig(qber_abort_threshold=None),
    )

    print(f"\n  {'rotación Y (rad)':>17} | {'QBER':>8} | {'descripción'}")
    print(f"  {'-'*17} | {'-'*8} | {'-'*40}")

    angles = [
        (0.0,           "sin rotación (ideal)"),
        (math.pi/8,     "π/8 = 22.5° (débil)"),
        (math.pi/4,     "π/4 = 45° (mezcla máxima)"),
        (math.pi/2,     "π/2 = 90° (rotación cuarto)"),
        (math.pi,       "π = 180° (inversión total)"),
        (3*math.pi/2,   "3π/2 = 270°"),
        (2*math.pi,     "2π = 360° (vuelta completa ≈ ideal)"),
    ]

    for angle, desc in angles:
        scenario = Scenario(
            **base_kwargs,
            channel=ChannelConfig(polarization_rotation_y_rad=angle),
        )
        r = run(scenario)
        print(f"  {angle:17.4f} | {r['qber']:8.4f} | {desc}")

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
        print(f"  {angle:17.4f} | {r['qber']:8.4f} | {desc}")

    print("""
  CONCLUSIÓN: La rotación Z introduce fase global → no afecta probabilidades
  de medición en las bases Z y X usadas en BB84. La rotación Y de π/2 es
  la más dañina porque transforma |0⟩→|1⟩ y |+⟩→|-⟩ simultáneamente.
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
          f"{'gain':>8} | {'timing_disc':>12} | {'sifted':>8}")
    print(f"  {'-'*13} | {'-'*9} | {'-'*8} | {'-'*12} | {'-'*8}")

    for jitter_ns in [0, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 50.0]:
        jitter_s = jitter_ns * 1e-9
        scenario = Scenario(
            **base_kwargs,
            timing=TimingConfig(jitter_std_s=jitter_s),
        )
        r = run(scenario)
        print(
            f"  {jitter_s:13.2e} | {jitter_ns:9.1f} | "
            f"{r['gain']:8.5f} | {r['dead_discards']:12d} | "
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
                f"{r['secret_bps']:12.2f}"
            )

    print("""
  CONCLUSIÓN: drift de 100 ppm a 1 MHz = desplazamiento de 100 ns/s.
  Con 10k pulsos (10 ms de sesión) el desfase es 1 ns, ya comparable
  con gate_width. Con 1M pulsos (1 s de sesión) → 100 ns de desfase →
  todos los fotones fuera de ventana.
""")


# ═════════════════════════════════════════════════════════════════════════════
# EXPERIMENTO 10
# "Sifting desactivado: QBER se va a 50%"
# ═════════════════════════════════════════════════════════════════════════════
def exp10_no_sifting():
    header("EXP 10 – Sin sifting: el 50% de las bases no coinciden → QBER→50%")

    print("""
  HIPÓTESIS INGENUA: si Alice y Bob miden en bases distintas, solo se introduce
  algo de ruido extra.
  REALIDAD: medir en base X cuando Alice preparó en Z da un bit COMPLETAMENTE
  aleatorio. Con sifting_enabled=False, la mitad de los bits son random →
  QBER ≈ 50% independientemente del canal. La clave es basura.
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
  NOTA: QBER con sifting desactivado ≈ 0.25, no 0.50. Esto se debe a que
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
            f"{r['gain']:8.5f} | {r['qber']:8.4f} | "
            f"{r['detected']:9d} | {r['secret_bps']:12.2f}"
        )

    print("""
  CONCLUSIÓN: con emission=0.0 y solo background, el gain puede ser alto pero
  el QBER ≈ 0.25 (bits completamente aleatorios). Con emission=1.0, la señal
  domina y el background apenas afecta. El ratio señal/ruido importa.
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
        pulses=8_000,
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
                f"  {n_pulses:8d} | {seed:5d} | {r['qber']:8.4f} | "
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
            f"  {label:<40} | {r['qber']:8.4f} | {r['sifted']:8d} | "
            f"{r['secret_bps']:12.2f} | {abort_str}"
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
  El gain del vacuum state mide exactamente la tasa de ruido del detector.
  Si Eve bloquea pulsos vacíos, el gain del vacuum cae abruptamente (detectable).
""")

    base_kwargs = dict(
        pulses=8_000,
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
        from qiskit_qkd import QiskitSamplerBackend
        backend = QiskitSamplerBackend(
            seed=scenario.seed, max_circuits_per_job=512, max_recorded_results=0
        )
        result = BB84Protocol().run(scenario, backend=backend)
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
  CONCLUSIÓN: el gain del vacuum state = (dark_count_rate * gate_width) +
  (background_rate * gate_width). Este número permite a Alice y Bob estimar
  el ruido real del sistema. Si Eve bloquea pulsos vacíos y los reenvía,
  el vacuum gain sería 0 → anomalía detectable.
""")


# ═════════════════════════════════════════════════════════════════════════════
# EXPERIMENTO 16
# "Depolarizing completo: QBER fijo en 25%, NO en 50% como se esperaría"
# ═════════════════════════════════════════════════════════════════════════════
def exp16_full_depolar_qber():
    header("EXP 16 – Depolarizing total: QBER=0.25, no 0.50 como intuye la gente")

    print("""
  HIPÓTESIS INGENUA: si el canal despolariza completamente (p=1), todos los
  bits serán erróneos → QBER=1.0 o al menos 0.5.
  REALIDAD: el canal despolarizante con p=1 produce una mezcla completa:
  ρ → I/2 (mezcla máxima). Medir I/2 en cualquier base da 50/50 aleatoriamente.
  Solo la mitad de esos resultados aleatorios discrepan de Alice → QBER=0.25.

  (Esto se observa en el simulador Aer. En el modelo clásico el efecto puede
   diferir ligeramente según la implementación.)
""")

    base_kwargs = dict(
        pulses=8_000,
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
  mixto → probabilidad 1/2 en cada medición → QBER = 0.25 (igual que Eve
  al 100%). El canal totalmente ruidoso es equivalente a un ataque de escucha.
  Esto es un resultado fundamental de la teoría de información cuántica.
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
  transporte cuántico. Aunque el QBER sea idéntico, las correlaciones entre
  errores son distintas y afectan la reconciliación de distinta manera.
  Para la tasa de clave secreta (asintótica) son idénticos, pero para bloques
  finitos la corrección de errores puede diferir.
""")

    base_kwargs = dict(
        pulses=8_000,
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
def main() -> None:
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


if __name__ == "__main__":
    main()
