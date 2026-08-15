import { describe, expect, test } from 'vitest'

import { resultPresentation, visibleResultTabs } from './resultSemantics'

const availableAssessment = {
  data_status: 'available',
  qber_defined: true,
  qber_value: 0,
  sample_size: 32,
}

describe('resultPresentation', () => {
  test.each([
    ['no_key_insufficient_data', 'SIN MUESTRA'],
    ['no_key_threshold_exceeded', 'ABORTADO POR UMBRAL'],
    ['no_key_verification_failed', 'CLAVE DESCARTADA'],
    ['no_extractable_key', 'SIN CLAVE ESTIMADA'],
    ['estimated_key_available', 'CLAVE ESTIMADA'],
    ['unknown', 'RESULTADO DIAGNÓSTICO'],
  ])('maps assessment key_status %s to %s', (keyStatus, expectedLabel) => {
    const presentation = resultPresentation({
      assessment: { ...availableAssessment, key_status: keyStatus },
      classical: { final_key_length: 0, verification_passed: false },
      metrics: { abort: true, secure: true, secret_key_rate_bps: 10, sifted: 32 },
    })

    expect(presentation.label).toBe(expectedLabel)
  })

  test.each([
    [{ sifted: 0, qber: 0, abort: false, secure: true }, {}, 'SIN MUESTRA'],
    [{ sifted: 10, qber: 0.2, abort: true }, {}, 'ABORTADO POR UMBRAL'],
    [{ sifted: 10, qber: 0.02, abort: false }, { verification_passed: false }, 'CLAVE DESCARTADA'],
    [{ sifted: 10, qber: 0.02, abort: false, secret_key_rate_bps: 12 }, {}, 'CLAVE ESTIMADA'],
    [{ sifted: 10, qber: 0.02, abort: false, secret_key_rate_bps: 0 }, {}, 'SIN CLAVE ESTIMADA'],
    [{ sifted: 10, qber: 0.02, abort: false, secure: true }, {}, 'RESULTADO DIAGNÓSTICO'],
  ])('uses a conservative legacy fallback', (metrics, classical, expectedLabel) => {
    expect(resultPresentation({ metrics, classical }).label).toBe(expectedLabel)
  })

  test.each([
    [
      { assessment: { ...availableAssessment, qber_defined: false } },
      false,
      null,
      32,
    ],
    [
      { assessment: { ...availableAssessment, qber_value: 0.04, sample_size: 0 } },
      false,
      null,
      0,
    ],
    [{ metrics: { qber: 0, sifted: 0 } }, false, null, 0],
    [{ metrics: { qber: 0, sifted: 32 } }, true, 0, 32],
  ])(
    'defines QBER only with an explicit non-empty sample',
    (summary, expectedDefined, expectedValue, expectedSampleSize) => {
      const presentation = resultPresentation(summary)

      expect(presentation.qberDefined).toBe(expectedDefined)
      expect(presentation.qberValue).toBe(expectedValue)
      expect(presentation.sampleSize).toBe(expectedSampleSize)
    },
  )

  test('does not fall back to optimistic legacy fields when assessment is malformed', () => {
    const presentation = resultPresentation({
      assessment: {},
      metrics: { abort: false, secret_key_rate_bps: 100, secure: true, sifted: 10 },
    })

    expect(presentation.label).toBe('RESULTADO DIAGNÓSTICO')
    expect(presentation.qberDefined).toBe(false)
    expect(presentation.rateEstimateBps).toBeNull()
  })

  test('prioritizes an explicit legacy classical threshold decision', () => {
    const presentation = resultPresentation({
      classical: { threshold_exceeded: false },
      metrics: {
        abort: true,
        qber: 0.02,
        secret_key_rate_bps: 0,
        sifted: 10,
      },
    })

    expect(presentation.label).toBe('SIN CLAVE ESTIMADA')
  })

  test('keeps a legacy CHSH sample size unknown instead of coercing it to zero', () => {
    const presentation = resultPresentation({
      metrics: { chsh_s: 2.5, qber: 0.02, sifted: 10 },
    })

    expect(presentation.observedChshS).toBe(2.5)
    expect(presentation.chshSampleSize).toBeNull()
  })

  test('localizes structured scientific reasons and assumptions from the API', () => {
    const presentation = resultPresentation({
      assessment: {
        ...availableAssessment,
        assumptions: [
          'pedagogical simulation model',
          'not a composable security proof',
        ],
        key_status: 'no_key_insufficient_data',
        reasons: [
          'No sifted bits were observed.',
          'QBER is undefined because its denominator is zero.',
        ],
      },
    })

    expect(presentation.reasons).toEqual([
      'No se observaron bits cribados.',
      'El QBER no está definido porque su denominador es cero.',
    ])
    expect(presentation.assumptions).toEqual([
      'modelo de simulación pedagógico',
      'no constituye una prueba de seguridad componible',
    ])
  })
})

describe('visibleResultTabs', () => {
  test('omits empty optional result tabs', () => {
    expect(
      visibleResultTabs(
        { bell: {}, classical: {}, correlations: {}, decoy: {}, event_sample: [] },
        { bell: {}, classical: {}, decoy_security: {} },
      ),
    ).toEqual(['summary', 'provenance'])
  })

  test('shows each optional tab only when it has content', () => {
    expect(
      visibleResultTabs(
        {
          bell: { chsh_s: 2.5 },
          classical: { final_key_length: 4 },
          decoy: { signal: { gain: 0.1 } },
          event_sample: [{ timing_status: 'ok' }],
        },
        {},
      ),
    ).toEqual(['summary', 'decoy', 'bell', 'events', 'classical', 'provenance'])
  })

  test('uses non-empty summary-only payloads from the additive result contract', () => {
    expect(
      visibleResultTabs(
        {},
        {
          bell: { chsh_s: 2.4 },
          classical: { verification_passed: true },
          decoy: { signal: { pulses: 1 } },
        },
      ),
    ).toEqual(['summary', 'decoy', 'bell', 'classical', 'provenance'])
  })
})
