# Plan de implementación: Panel Visual QKD (React + FastAPI)

> **Para agentes de IA:** REQUIRED SUB-SKILL: usar `superpowers:executing-plans`
> o `superpowers:subagent-driven-development` para implementar este plan tarea a
> tarea. Las tareas usan checkboxes para seguimiento. La sección "Decisiones
> cerradas" no se renegocia. Si una tarea contradice el código actual de
> `src/qiskit_qkd`, prevalece el código y se anota la discrepancia.

**Objetivo:** aplicación web local (sin despliegue, sin autenticación) para
diseñar, caracterizar, ejecutar y comparar simulaciones QKD sobre `qiskit-qkd`:

- Editar visualmente **todo** lo configurable de un `Scenario` (protocolo,
  fuente, canal, detector, timing, Eve, post-proceso, E91, dinámica temporal).
- **Caracterizar todo el enlace**: emisión (fuente), canal, receptor
  (detector + gating temporal), con tablas y curvas analíticas sin necesidad de
  ejecutar el protocolo.
- Ejecutar simulaciones y barridos con progreso, y ver estadísticos completos.
- **Estudio de curvas universal**: generar una curva de *cualquier* métrica
  frente a *cualquier* parámetro barrible, con repeticiones, bandas de error,
  series comparativas y export SVG/PNG/CSV listo para la memoria del TFG.
- Biblioteca de experimentos persistente (JSON) con digest reproducible.

**Arquitectura (3 capas):**

1. **Librería** (`src/qiskit_qkd`) — única fuente de verdad de física y
   validación. Se amplía de forma **aditiva** con: caracterización de
   fuente/detector/timing (siguiendo el patrón `ChannelState`), un sweep
   genérico por target y el registro de targets barribles.
2. **API** (`panel/api`, FastAPI) — capa fina: valida construyendo objetos de
   la librería, orquesta ejecuciones en un pool de procesos, persiste
   experimentos como JSON y expone el catálogo de parámetros/métricas.
3. **Web** (`panel/web`, React + Vite + TypeScript) — formularios generados
   desde el catálogo, gráficas Plotly, tema oscuro de laboratorio.

**Stack técnico (fijado):**

- Backend: FastAPI, uvicorn, pydantic v2 (solo envolturas de API),
  `concurrent.futures.ProcessPoolExecutor` para ejecuciones, sin base de datos
  (JSON en `panel/store/`).
- Frontend: Vite + React 18 + TypeScript, Tailwind CSS + shadcn/ui (Radix),
  TanStack Query (estado servidor), Zustand (estado del diseñador),
  react-plotly.js (curvas/heatmaps con export nativo a SVG/PNG), lucide-react
  (iconos), KaTeX (fórmulas).
- Cliente TS generado desde OpenAPI con `openapi-typescript` (script npm).
- Tests: pytest para librería y API (httpx `TestClient`); vitest mínimo para el
  renderizador de formularios; ruff como hasta ahora.

---

## Decisiones cerradas

1. **La librería valida; nadie más.** La API construye `Scenario.from_dict()`
   y mapea `ValueError`/`TypeError` a HTTP 422 con el path del campo
   (`{"loc": "channel.distance_km", "msg": "..."}`). Prohibido duplicar reglas
   físicas en pydantic o en el frontend; el frontend solo aplica los rangos
   informativos del catálogo como UX (clamps de slider), nunca como verdad.
2. **Formularios dirigidos por catálogo.** `GET /api/catalog` describe
   secciones y campos (tipo, unidad, rango sugerido, default, texto de ayuda,
   visibilidad condicional, `sweepable`). El frontend renderiza el formulario
   genéricamente desde el catálogo y NO hardcodea campos. Añadir un campo a la
   librería = añadir una entrada al catálogo, cero cambios de UI.
3. **Targets de sweep** reutilizan la sintaxis `section.field` y la validación
   de `qiskit_qkd/config/dynamics.py` (`validate_parameter_target`), ampliada
   con un registro `SWEEPABLE_TARGETS` en la librería.
4. **No tocar la física existente.** Los números de seeds del TFG están
   congelados: no se modifica el stream RNG, ni `prepare_physical_round`, ni
   los protocolos, salvo adiciones estrictamente nuevas con tests.
5. **Resultados grandes**: las respuestas de la API limitan `event_sample` a
   200 eventos; el resultado completo se descarga como fichero JSON.
6. Herramienta local: uvicorn en `127.0.0.1`, sin auth, CORS solo para el
   puerto de Vite en desarrollo.
7. **Windows-first**: multiproceso con `spawn` → todos los módulos del panel
   deben ser import-safe (sin efectos colaterales a nivel de módulo); rutas y
   scripts probados en PowerShell.
8. Idioma de la UI: español. Identificadores, endpoints y código: inglés.

---

## Estructura de carpetas

```
qiskit-qkd/
  src/qiskit_qkd/            # librería (adiciones de Fase 1)
  panel/
    api/
      __init__.py
      __main__.py            # python -m panel.api  → modo demo (sirve build)
      app.py                 # factory FastAPI, CORS, static files
      catalog.py             # catálogo de parámetros y métricas
      jobs.py                # cola in-memory + ProcessPoolExecutor + progreso
      store.py               # experimentos/recetas JSON en panel/store/
      errors.py              # ValueError → 422 con field path
      routes/
        scenarios.py         # POST /api/scenarios/validate
        runs.py              # POST /api/runs, GET /api/runs/{id}...
        sweeps.py            # POST /api/sweeps (1D, series, temporal)
        characterize.py      # POST /api/characterize/{source|channel|detector|timing}
        dynamics.py          # POST /api/dynamics/preview
        experiments.py       # CRUD biblioteca + import/export
        presets.py           # GET /api/presets
    web/
      src/
        api/                 # cliente generado + hooks TanStack Query
        components/          # MetricCard, StatusBadge, DigestChip, UnitInput,
                             # LogSlider, SchemaForm, PlotPanel...
        features/
          library/           # vista Biblioteca
          designer/          # vista Diseñador (+ tab Dinámica)
          characterize/      # vista Caracterización
          results/           # vista Ejecución y Resultados
          curves/            # vista Estudio de Curvas
        lib/                 # theme, format (unidades), utils
        routes/              # router
    store/                   # *.json (gitignored)
    README.md                # arranque en 2 comandos + modo demo
```

---

## Contratos API (ejemplos normativos)

`POST /api/runs` — cuerpo y respuesta:

```json
{"scenario": { ...Scenario.to_dict()... }, "label": "fibra 50 km"}
→ {"job_id": "r_01HX...", "status": "queued", "digest": "ab12..."}
```

`GET /api/runs/{id}`:

```json
{"job_id": "r_01HX...", "status": "running", "progress": {"done": 0, "total": 1},
 "elapsed_s": 3.2}
→ al terminar: {"status": "done", "result_summary": {"qber": 0.021,
 "secret_key_rate_bps": 31400.0, "abort": false, "chsh_s": null, ...}}
```

`POST /api/sweeps` — el corazón del Estudio de Curvas:

```json
{
  "scenario": { ... },
  "axis":   {"target": "channel.distance_km",
             "values": {"start": 0, "stop": 150, "steps": 16, "scale": "linear"}},
  "series": {"target": "detector.efficiency", "values": [0.6, 0.8, 0.95]},
  "repeats": 5,
  "time_axis": false
}
→ {"job_id": "s_01HX..."}   // progreso = puntos completados / totales
→ resultado: {"rows": [...metric rows...], "summary": [...mean/std/p05/p95...]}
```

`POST /api/characterize/detector`:

```json
{"scenario": { ... }, "axis": {"target": "channel.distance_km",
                                "values": {"start": 0, "stop": 100, "steps": 21}}}
→ {"rows": [ {"distance_km": 0.0, "p_dark_per_gate": 1e-6, ...}, ... ]}
```

Error de validación (formato único):

```json
HTTP 422 → {"errors": [{"loc": "channel.distance_km",
                        "msg": "distance_km must be greater than or equal to 0"}]}
```

---

## Catálogo de parámetros y métricas

- **Parámetros**: una entrada por campo de `ProtocolConfig`, `SourceConfig`
  (incluida la tabla de `DecoyIntensity`), `ChannelConfig` (con
  `visible_when: channel.kind in [...]` para cada familia), `DetectorConfig`,
  `TimingConfig`, `EveConfig` (`visible_when: protocol == bb84`),
  `PostProcessingConfig`, `E91Config` (`visible_when: protocol == e91`) y
  básicos del `Scenario` (pulses, clock_rate_hz, seed, event_sample_size).
  Cada entrada: `{key, section, label_es, type, unit, default, min, max, step,
  scale (lin|log), help_es, visible_when, sweepable}`.
- **Métricas** (eje Y del Estudio de Curvas), con label y unidad:
  - De `Metrics`: qber, gain, secret_key_rate_bps, sifted_key_rate_bps,
    raw_detection_rate_hz, loss_db, emitted, transmitted, detected, sifted,
    errors, timing_discards, dead_time_discards, afterpulse_clicks,
    eve_intercepted_fraction, eve_information_estimate, chsh_s, abort.
  - Derivadas (`analysis.add_derived_metrics`): emission_fraction,
    transmission_fraction, detected_fraction, sifted_fraction, error_fraction,
    timing_discard_fraction, privacy_efficiency, qber_margin, chsh_margin,
    secure.
  - De `classical`: estimated_qber, leak_ec, corrected_key_length,
    final_key_length, residual_mismatches, verification_passed.
  - De `decoy.security` (si existe): secret_key_rate_bps,
    single_photon_yield_lower_bound, single_photon_error_rate_upper_bound.
- Los labels reutilizan/espejan `visualization/style.py` para que panel y
  memoria sean coherentes.

---

## Caracterización completa (requisito central)

Nuevo módulo siguiendo el patrón existente de `ChannelState`
(`dataclass frozen` + `to_dict()` + `*_state_from_scenario(scenario, time_s,
resolver)`, resoluble en el tiempo con `ParameterResolver`):

- **`SourceState`** (emisión): kind, emission_probability,
  preparation_error_probability; por intensidad decoy: μ, p_selección y las
  probabilidades analíticas de Poisson `P(0)=e^-μ`, `P(1)=μe^-μ`,
  `P(≥2)=1-e^-μ(1+μ)`, fracción multifotón condicionada a emisión (exposición a
  PNS) y tasa media de fotones. Para `entangled_pair`: tasa de pares.
- **`DetectorState`** (receptor): efficiency, `p_dark_per_gate`
  (ya existe `ThresholdDetector.dark_count_probability`), `p_background_per_gate`
  efectiva usando `effective_background_count_rate_hz` (incluye Raman),
  dead_time → tasa máxima de cuentas `1/τ`, afterpulse_probability,
  double_click_policy, readout_error_probability, gate_width.
- **`TimingState`** (gating del receptor): σ de jitter efectiva
  (`effective_jitter_std_s`, incluye broadenings del canal), probabilidad
  analítica de caer en gate `erf(g / (2√2 σ))`, walk-off por drift de reloj
  (primer slot donde la desalineación supera `gate/2`), propagation_delay,
  clock_offset.
- **Curvas de caracterización** (endpoint acepta `axis` opcional): cualquiera
  de los campos anteriores frente a distancia, tiempo o un target barrible.
  Ejemplos canónicos en UI: `P(n)` vs μ; `p_click = 1-(1-η)^n` vs n; QBER
  floor por dark counts vs distancia; prob. in-gate vs jitter; loss_db y η vs
  distancia por familia de canal.

---

## Vistas de la UI

1. **Biblioteca** — grid de tarjetas de experimentos: nombre, badge de
   protocolo, digest corto, tags, mini-métricas del último run, fecha.
   Acciones: cargar en el diseñador, duplicar, borrar, exportar/importar JSON.
2. **Diseñador** — sidebar con secciones; formulario generado del catálogo con
   unidades en los labels, sliders log donde toque y visibilidad condicional
   (familia de canal, protocolo). Panel lateral fijo de **link budget en
   vivo**: loss_dB, η, p_dark, σ_jitter efectiva, fracción multifotón —
   recalculado con los endpoints de caracterización a cada cambio (debounce).
   Validación inline con los mensajes 422. Tab **Dinámica**: constructor de
   schedules (target + perfil + ventana) con **timeline Plotly** del guion
   temporal (vía `/api/dynamics/preview`).
3. **Caracterización** — tabs Fuente | Canal | Detector | Timing: tarjetas con
   los valores del estado + fórmula KaTeX + mini-curva; selector de eje para
   regenerar cualquier curva frente a distancia/tiempo/target.
4. **Ejecución y Resultados** — botón Ejecutar (con aviso si Aer activo y
   pulses > 1e5), barra de progreso del job, tiempo transcurrido. Al terminar:
   fila de tarjetas grandes (QBER, SKR, gain, sifted, CHSH S) **con delta
   respecto al run anterior del mismo experimento**, badge
   SEGURO / ABORT / VERIFICACIÓN FALLIDA. Sub-tabs auto-detectadas según el
   contenido: Decoy (tabla por intensidad + Y₁/e₁/Q₁), Bell (heatmap de
   correlaciones por settings), Eventos (histograma de timing_status sobre la
   muestra), Clásico (reconciliación, leak_ec, PA, verificación), Provenance
   (versiones, seeds, digest, modelo de ruido).
5. **Estudio de Curvas** — selector de: experimento base (de la biblioteca o el
   actual), eje X (cualquier target `sweepable` o tiempo), métricas Y (1–3,
   multi-panel), serie opcional (otro target con ≤6 valores, o varios
   experimentos guardados, o la familia de canal), repeats (bandas mean±std con
   p05/p95), escalas lin/log, líneas de umbral (QBER abort, CHSH=2). Botones:
   ejecutar barrido (job con progreso por puntos), export SVG/PNG/CSV, y
   **guardar como receta** (`CurveRecipe` JSON re-ejecutable en la biblioteca).
   Atajos one-click: SKR vs distancia (log, con `secure_distance_limit`
   marcado), QBER vs distancia con umbral, CHSH vs depolarizing, QBER vs
   prob. de intercepción de Eve, gain/QBER por intensidad decoy, métricas vs
   tiempo con schedules activos.

---

## Guía estética

- Tema oscuro de laboratorio: fondo `#0b0f17`, superficie `#121826`, borde
  `#1f2937`; acento primario cian `#22d3ee`, secundario violeta `#8b5cf6`;
  estados verde `#34d399` / ámbar `#fbbf24` / rojo `#f87171`. Las series de
  curvas usan la paleta `QKD_COLORS` de `visualization/style.py` espejada en
  TS, para coherencia exacta panel ↔ figuras de la memoria.
- Tipografía: Inter para UI; JetBrains Mono para números, digests y unidades.
- Componentes con personalidad: `MetricCard` (valor grande + delta coloreado),
  `StatusBadge`, `DigestChip` (copia al click), `UnitInput` (sufijo de unidad),
  `LogSlider`. Microinteracciones discretas (transiciones 150 ms); nada de
  animaciones aparatosas.
- Fórmulas con KaTeX donde aporten (fracción secreta, h₂(Q), P(n), erf del
  gate). Tooltips de ayuda desde `help_es` del catálogo.
- Plotly con template oscuro propio: grid sutil, hover unificado, ejes con
  unidades, export nativo a SVG con fondo transparente.

---

## Fases

### Fase 0 — Viabilidad y esqueleto

- [x] Verificar deps backend en el venv del proyecto (Python 3.14):
      `..\.venv\Scripts\python.exe -m pip install fastapi "uvicorn[standard]" "pydantic>=2" httpx`.
      Plan B si pydantic no tiene wheels para 3.14: crear `panel/.venv-api` con
      Python 3.12 solo para la API (la librería soporta ≥3.12).
- [x] Verificar Node ≥ 20 (`node --version`); si falta:
      `winget install OpenJS.NodeJS.LTS`.
- [x] Scaffolding `panel/web` con Vite (react-ts), Tailwind, shadcn/ui,
      TanStack Query, react-plotly.js, lucide-react, KaTeX.
- [x] `panel/api/app.py` con FastAPI hello + CORS para el puerto de Vite +
      proxy `/api` en `vite.config.ts`.
- [x] `pyproject.toml`: extra `panel = ["fastapi", "uvicorn[standard]", "httpx"]`;
      `.gitignore`: `panel/store/`, `panel/web/node_modules/`, `panel/web/dist/`.
- [x] `panel/README.md`: arranque en 2 comandos (uvicorn --reload + npm run dev).
- **Hecho cuando:** ambos servidores arrancan y la web muestra "API ok" leyendo
  un endpoint real.

### Fase 1 — Adiciones a la librería (sin UI, con tests)

- [x] `SourceState` + `source_state_from_scenario()` (patrón `ChannelState`,
      resolver-aware) con las probabilidades Poisson analíticas por intensidad.
- [x] `DetectorState` + `detector_state_from_scenario()`.
- [x] `TimingState` + `timing_state_from_scenario()` (in-gate analítico con
      `math.erf`, walk-off por drift).
- [x] `SWEEPABLE_TARGETS` en la librería (targets de dynamics + `scenario.pulses`,
      `scenario.clock_rate_hz`) y
      `analysis.sweep_scenario_parameter(protocol, scenario, target, values, *,
      repeats, backend_factory)` genérico que devuelve metric rows (reutiliza
      `metric_rows_from_results`/`summarize_metric_rows`).
- [x] Tests pytest de todo lo anterior (mismo rigor que el resto del repo);
      exportar en `__init__` correspondientes.
- **Hecho cuando:** `pytest -q` verde y los nuevos helpers devuelven filas
  JSON-safe documentadas.

### Fase 2 — API completa

- [x] `catalog.py` (parámetros + métricas, según la sección Catálogo).
- [x] `errors.py`: handler que convierte excepciones de la librería en 422 con
      `loc` (path del campo cuando sea inferible).
- [x] `jobs.py`: ProcessPoolExecutor (spawn-safe), estados
      queued/running/done/error/cancelled, progreso por puntos en sweeps,
      cancelación, límite de 1 job concurrente pesado.
- [x] Rutas: scenarios/validate, runs, sweeps (1D + series + temporal vía
      `sweep_bb84_time`), characterize (4 endpoints), dynamics/preview,
      experiments CRUD (+ import/export y `CurveRecipe`), presets (4 escenarios:
      "Fibra metropolitana", "Satélite LEO", "PNS sobre decoy débil",
      "E91 con scintillation").
- [x] Tests httpx: validación con error de campo, run BB84 pequeño end-to-end,
      sweep 3 puntos con repeats, characterize de las 4 secciones, CRUD.
- **Hecho cuando:** `pytest tests/panel_api -q` verde y `/docs` (OpenAPI)
  refleja todos los contratos.

### Fase 3 — Web: base + Diseñador

- [x] Tema (tokens de la Guía estética), layout con sidebar de navegación,
      template Plotly oscuro, generación del cliente TS desde OpenAPI (script
      `npm run gen:api`).
- [x] `SchemaForm`: renderizador genérico desde `/api/catalog` (tipos, unidades,
      condicionales, sliders log) + editor de tabla decoy con check Σp=1 +
      editor de listas de ángulos E91.
- [x] Validación inline conectada a `/api/scenarios/validate` (debounce) y
      DigestChip con estado ejecutado/modificado.
- [x] Panel de link budget vivo (characterize con debounce).
- [x] Tab Dinámica: constructor de schedules + timeline de `/api/dynamics/preview`.
- **Hecho cuando:** se puede construir desde cero un escenario BB84 decoy con
  fibra + un schedule, sin tocar JSON, con validación visible.

### Fase 4 — Web: Ejecución y Resultados

- [x] Lanzar runs, polling de jobs, barra de progreso y cancelar.
- [x] MetricCards con delta vs run anterior + StatusBadge
      (incluye VERIFICACIÓN FALLIDA con `verification_passed=false`).
- [x] Sub-tabs auto-detectadas: Decoy, Bell (heatmap), Eventos (histograma de
      timing_status), Clásico, Provenance.
- [x] Biblioteca: guardar/cargar/duplicar/borrar/exportar experimentos con
      resultado adjunto.
- **Hecho cuando:** flujo completo Diseñador → Ejecutar → Resultados →
  Guardar → Recargar funciona para BB84 y E91.

### Fase 5 — Estudio de Curvas + Caracterización UI

- [x] Vista Estudio de Curvas completa (X/Y/serie/repeats/escala/umbral),
      progreso por puntos, bandas mean±std, export SVG/PNG/CSV.
- [x] Recetas de curva guardables y re-ejecutables desde la Biblioteca.
- [x] Atajos one-click (las 6 curvas canónicas de la sección Vistas).
- [x] Vista Caracterización (4 tabs con tarjetas + fórmulas KaTeX + curvas con
      selector de eje).
- **Hecho cuando:** se puede generar y exportar "SKR vs distancia con 3
  eficiencias de detector y 5 repeats" en menos de 5 clicks desde un
  experimento guardado.

### Fase 6 — Pulido y modo demo

- [x] `python -m panel.api` sirve el build estático de `panel/web/dist` y abre
      el navegador: demo de defensa con un solo comando y sin Node.
- [x] Deltas, tooltips de ayuda, estados vacíos cuidados, manejo de errores de
      job visibles, avisos de coste (Aer + pulses altos).
- [x] README final con capturas; sección nueva en el README raíz del repo.
- [x] Opcional: smoke E2E con Playwright (diseñar → ejecutar → curva).
- **Hecho cuando:** una persona sin contexto arranca la demo con un comando y
  reproduce un experimento guardado con su digest.

---

## Verificación

```powershell
# librería + API
..\.venv\Scripts\python.exe -m pytest -q
..\.venv\Scripts\python.exe -m ruff check .
# web
cd panel/web; npm run lint; npm run build
# demo
..\.venv\Scripts\python.exe -m panel.api
```

## Riesgos y mitigaciones

- **pydantic/uvicorn sin wheels en Python 3.14** → Fase 0 lo verifica primero;
  plan B: venv 3.12 dedicado a la API (la librería declara ≥3.12).
- **Runs largos con Aer** (1e6 pulsos = minutos) → pool de procesos, progreso,
  cancelación y aviso de coste en UI; cache opcional de resultados por digest.
- **Windows + multiprocessing (spawn)** → módulos import-safe; los workers
  reciben el escenario serializado (`Scenario.to_json`) y lo reconstruyen.
- **Tamaño de resultados** → cap de event_sample en API; descarga completa
  como fichero.
- **Deriva de esquema** entre librería y catálogo → test que compara los campos
  del catálogo con los `to_dict()` de cada config (falla si alguien añade un
  campo sin catalogarlo).

## Extensiones futuras (fuera de alcance)

Sweeps de ángulos E91 como target, comparador de modelos de ruido Aer lado a
lado, export directo de figuras matplotlib (recetas de `visualization/`) para
la memoria, modo informe PDF automático, websockets para progreso (el polling
basta), multi-usuario/despliegue.
