import type { JsonObject, ResultAssessment } from '@/api/client'
import { isRecord } from '@/features/shared/scenarioPaths'

export type ResultStatus =
  | 'no-sample'
  | 'threshold-abort'
  | 'verification-failed'
  | 'no-key-estimate'
  | 'key-estimate'
  | 'diagnostic'

export type ResultStatusLabel =
  | 'SIN MUESTRA'
  | 'ABORTADO POR UMBRAL'
  | 'CLAVE DESCARTADA'
  | 'SIN CLAVE ESTIMADA'
  | 'CLAVE ESTIMADA'
  | 'RESULTADO DIAGNÓSTICO'

export type ResultStatusTone = 'cyan' | 'danger' | 'warning' | 'neutral'

export type ResultPresentation = {
  status: ResultStatus
  label: ResultStatusLabel
  tone: ResultStatusTone
  assessment: ResultAssessment | null
  qberDefined: boolean
  qberValue: number | null
  sampleSize: number
  rateEstimateBps: number | null
  rateEstimateStatus: string | null
  rateEstimateMethod: string | null
  securityScope: string | null
  reasons: string[]
  assumptions: string[]
  observedChshS: number | null
  chshSampleSize: number | null
  conclusionScope: string | null
}

export type ResultTab =
  | 'summary'
  | 'decoy'
  | 'bell'
  | 'events'
  | 'classical'
  | 'provenance'

const STATUS_PRESENTATION: Record<
  ResultStatus,
  { label: ResultStatusLabel; tone: ResultStatusTone }
> = {
  'no-sample': { label: 'SIN MUESTRA', tone: 'warning' },
  'threshold-abort': { label: 'ABORTADO POR UMBRAL', tone: 'danger' },
  'verification-failed': { label: 'CLAVE DESCARTADA', tone: 'danger' },
  'no-key-estimate': { label: 'SIN CLAVE ESTIMADA', tone: 'warning' },
  'key-estimate': { label: 'CLAVE ESTIMADA', tone: 'cyan' },
  diagnostic: { label: 'RESULTADO DIAGNÓSTICO', tone: 'neutral' },
}

const SCIENTIFIC_TEXT_ES: Record<string, string> = {
  NO_SIFTED_BITS: 'No se observaron bits cribados.',
  'No sifted bits were observed.': 'No se observaron bits cribados.',
  QBER_UNDEFINED: 'El QBER no está definido porque su denominador es cero.',
  'QBER is undefined because its denominator is zero.': 'El QBER no está definido porque su denominador es cero.',
  QBER_THRESHOLD_EXCEEDED: 'La estimación de QBER observada supera el umbral configurado.',
  'The observed QBER estimate exceeds the configured threshold.': 'La estimación de QBER observada supera el umbral configurado.',
  CLASSICAL_QBER_EVIDENCE_MISMATCH: 'Los campos clásicos de QBER no concuerdan con la evidencia agregada de errores.',
  'The stored classical QBER fields disagree with aggregate error evidence.': 'Los campos clásicos de QBER no concuerdan con la evidencia agregada de errores.',
  METRICS_CLASSICAL_ABORT_MISMATCH: 'El indicador agregado de aborto no concuerda con la decisión clásica.',
  'The legacy aggregate abort flag disagrees with the classical decision.': 'El indicador agregado de aborto no concuerda con la decisión clásica.',
  CLASSICAL_THRESHOLD_EVIDENCE_MISMATCH: 'La decisión clásica de umbral no concuerda con el QBER observado.',
  'The stored classical threshold decision disagrees with the observed QBER.': 'La decisión clásica de umbral no concuerda con el QBER observado.',
  METRICS_THRESHOLD_EVIDENCE_MISMATCH: 'La decisión agregada de umbral no concuerda con el QBER observado.',
  'The legacy aggregate threshold decision disagrees with the observed QBER.': 'La decisión agregada de umbral no concuerda con el QBER observado.',
  CLASSICAL_THRESHOLD_CONFIG_MISMATCH: 'El umbral clásico almacenado no concuerda con el escenario serializado.',
  'The stored classical threshold disagrees with the serialized scenario.': 'El umbral clásico almacenado no concuerda con el escenario serializado.',
  VERIFICATION_FAILED: 'La verificación clásica de la clave encontró discrepancias residuales.',
  'Classical key verification found residual mismatches.': 'La verificación clásica de la clave encontró discrepancias residuales.',
  NO_EXTRACTABLE_KEY: 'El procesamiento modelado no produjo una clave extraíble.',
  'No extractable key was produced by the modeled processing.': 'El procesamiento modelado no produjo una clave extraíble.',
  LEGACY_RATE_INCONSISTENT_WITH_KEY_STATUS: 'La tasa asintótica heredada es positiva aunque la clave evaluada no está disponible.',
  'The legacy asymptotic rate is positive although the assessed key is unavailable.': 'La tasa asintótica heredada es positiva aunque la clave evaluada no está disponible.',
  CHSH_UNAVAILABLE: 'Ningún valor CHSH observado está respaldado por muestras de coincidencias.',
  'No observed CHSH value is supported by coincidence samples.': 'Ningún valor CHSH observado está respaldado por muestras de coincidencias.',
  CHSH_DISABLED: 'La estimación CHSH estaba desactivada para este escenario.',
  'CHSH estimation was disabled for this scenario.': 'La estimación CHSH estaba desactivada para este escenario.',
  BELL_CHSH_EVIDENCE_MISMATCH: 'El resumen de Bell no concuerda con el CHSH recalculado a partir de los conteos por ajuste.',
  'The stored Bell summary disagrees with CHSH recomputed from setting counts.': 'El resumen de Bell no concuerda con el CHSH recalculado a partir de los conteos por ajuste.',
  METRICS_CHSH_EVIDENCE_MISMATCH: 'El valor CHSH agregado no concuerda con el recalculado a partir de los conteos por ajuste.',
  'The aggregate CHSH value disagrees with CHSH recomputed from setting counts.': 'El valor CHSH agregado no concuerda con el recalculado a partir de los conteos por ajuste.',
  'pedagogical simulation model': 'modelo de simulación pedagógico',
  'asymptotic rate formula; no finite-key correction': 'fórmula de tasa asintótica, sin corrección finite-key',
  'not a composable security proof': 'no constituye una prueba de seguridad componible',
  'revealed QBER sample; no confidence interval': 'muestra de QBER revelada, sin intervalo de confianza',
  'QBER uses the full sifted key as a simulator-only diagnostic': 'el QBER usa toda la clave cribada como diagnóstico exclusivo del simulador',
  'CHSH diagnostic assumes fair sampling of detected coincidences': 'el diagnóstico CHSH supone un muestreo justo de las coincidencias detectadas',
  'no statistical significance or confidence interval is computed': 'no se calcula significación estadística ni intervalo de confianza',
  'detected-coincidence post-selection does not close detection or locality loopholes': 'la postselección de coincidencias detectadas no cierra las lagunas de detección o localidad',
  'not a device-independent security certification': 'no constituye una certificación de seguridad independiente del dispositivo',
}

function localizeScientificText(value: string): string {
  return SCIENTIFIC_TEXT_ES[value] ?? value
}

export function resultPresentation(summary: JsonObject): ResultPresentation {
  const assessmentRecord = isRecord(summary.assessment) ? summary.assessment : null
  const assessment = assessmentRecord as ResultAssessment | null
  const metrics = isRecord(summary.metrics) ? summary.metrics : summary
  const classical = isRecord(summary.classical) ? summary.classical : {}
  const rateEstimateStatus = assessmentRecord
    ? stringValue(assessmentRecord.rate_estimate_status)
    : finiteNumber(metrics.secret_key_rate_bps) === null
      ? 'unavailable'
      : 'available'

  const sampleSize = assessmentRecord
    ? nonNegativeCount(assessmentRecord.sample_size)
    : nonNegativeCount(metrics.sifted)
  const assessmentQber = finiteNumber(assessmentRecord?.qber_value)
  const legacyQber = finiteNumber(metrics.qber)
  const qberDefined = assessmentRecord
    ? assessmentRecord.qber_defined === true && sampleSize > 0 && assessmentQber !== null
    : sampleSize > 0 && legacyQber !== null
  const status = assessmentRecord
    ? statusFromAssessment(assessmentRecord)
    : statusFromLegacy(metrics, classical, sampleSize)
  const statusPresentation = STATUS_PRESENTATION[status]

  return {
    status,
    ...statusPresentation,
    assessment,
    qberDefined,
    qberValue: qberDefined ? (assessmentRecord ? assessmentQber : legacyQber) : null,
    sampleSize,
    rateEstimateBps: assessmentRecord
      ? rateEstimateStatus === 'available' ||
        rateEstimateStatus === 'inconsistent_with_key_status'
        ? finiteNumber(assessmentRecord.rate_estimate_bps)
        : null
      : finiteNumber(metrics.secret_key_rate_bps),
    rateEstimateStatus,
    rateEstimateMethod: stringValue(assessmentRecord?.rate_estimate_method),
    securityScope: stringValue(assessmentRecord?.security_scope),
    reasons: firstNonEmptyStringArray(
      assessmentRecord?.reasons,
      assessmentRecord?.reason_codes,
    ).map(localizeScientificText),
    assumptions: stringArray(assessmentRecord?.assumptions).map(localizeScientificText),
    observedChshS: assessmentRecord
      ? finiteNumber(assessmentRecord.observed_chsh_s)
      : finiteNumber(metrics.chsh_s),
    chshSampleSize: assessmentRecord
      ? nonNegativeCount(assessmentRecord.chsh_sample_size)
      : null,
    conclusionScope: stringValue(assessmentRecord?.conclusion_scope),
  }
}

export function visibleResultTabs(
  result: JsonObject,
  summary: JsonObject,
): ResultTab[] {
  const tabs: ResultTab[] = ['summary']

  if (
    hasEntries(result.decoy) ||
    hasEntries(summary.decoy) ||
    hasEntries(summary.decoy_security)
  ) {
    tabs.push('decoy')
  }
  if (hasEntries(result.bell) || hasEntries(result.correlations) || hasEntries(summary.bell)) {
    tabs.push('bell')
  }
  if (Array.isArray(result.event_sample) && result.event_sample.length > 0) {
    tabs.push('events')
  }
  if (hasEntries(result.classical) || hasEntries(summary.classical)) {
    tabs.push('classical')
  }

  tabs.push('provenance')
  return tabs
}

function statusFromAssessment(assessment: JsonObject): ResultStatus {
  if (
    assessment.data_status === 'insufficient_data' ||
    assessment.key_status === 'no_key_insufficient_data'
  ) {
    return 'no-sample'
  }

  switch (assessment.key_status) {
    case 'no_key_threshold_exceeded':
      return 'threshold-abort'
    case 'no_key_verification_failed':
      return 'verification-failed'
    case 'no_extractable_key':
      return 'no-key-estimate'
    case 'estimated_key_available':
      return 'key-estimate'
    case 'unknown':
      return 'diagnostic'
    default:
      return 'diagnostic'
  }
}

function statusFromLegacy(
  metrics: JsonObject,
  classical: JsonObject,
  sampleSize: number,
): ResultStatus {
  if (sampleSize === 0) {
    return 'no-sample'
  }
  const classicalThresholdDecision = classical.threshold_exceeded
  if (
    classicalThresholdDecision === true ||
    (typeof classicalThresholdDecision !== 'boolean' && metrics.abort === true)
  ) {
    return 'threshold-abort'
  }
  if (classical.verification_passed === false || classical.verification_status === 'failed') {
    return 'verification-failed'
  }

  const rate = finiteNumber(metrics.secret_key_rate_bps)
  const finalKeyLength = finiteNumber(classical.final_key_length)
  if ((rate !== null && rate > 0) || (finalKeyLength !== null && finalKeyLength > 0)) {
    return 'key-estimate'
  }
  if (rate === 0 || finalKeyLength === 0) {
    return 'no-key-estimate'
  }
  return 'diagnostic'
}

function finiteNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function nonNegativeCount(value: unknown): number {
  const number = finiteNumber(value)
  return number !== null && number > 0 ? Math.trunc(number) : 0
}

function stringValue(value: unknown): string | null {
  return typeof value === 'string' && value.trim() !== '' ? value : null
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
}

function firstNonEmptyStringArray(...values: unknown[]): string[] {
  for (const value of values) {
    const items = stringArray(value)
    if (items.length > 0) {
      return items
    }
  }
  return []
}

function hasEntries(value: unknown): boolean {
  return isRecord(value) && Object.keys(value).length > 0
}
