import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import {
  csvCell,
  downloadCsv,
  downloadCurveSvg,
  downloadJson,
  safeFileName,
} from './download'

let capturedBlobs: Array<{ parts: BlobPart[]; type: string | undefined }>

beforeEach(() => {
  capturedBlobs = []
  class CapturingBlob {
    constructor(parts: BlobPart[], options?: BlobPropertyBag) {
      capturedBlobs.push({ parts, type: options?.type })
    }
  }
  vi.stubGlobal('Blob', CapturingBlob)
  Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: vi.fn(() => 'blob:qkd-export') })
  Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() })
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

test('quotes CSV cells and leaves missing or non-finite numeric values empty', () => {
  expect(csvCell('uno,dos')).toBe('"uno,dos"')
  expect(csvCell('línea 1\nlínea "2"')).toBe('"línea 1\nlínea ""2"""')
  expect(csvCell(null)).toBe('')
  expect(csvCell(undefined)).toBe('')
  expect(csvCell(Number.NaN)).toBe('')
  expect(csvCell(Number.POSITIVE_INFINITY)).toBe('')
  expect(csvCell({ note: 'a,b', value: Number.NaN })).toBe('"{""note"":""a,b"",""value"":null}"')
})

test('builds a UTF-8 CSV with a stable union of headers and RFC-style line breaks', () => {
  downloadCsv([
    { x: 0, note: 'a,b' },
    { x: 1, missing: null, note: 'segunda\nlínea' },
  ], 'curva')

  expect(capturedBlobs).toHaveLength(1)
  expect(capturedBlobs[0].type).toBe('text/csv;charset=utf-8')
  expect(capturedBlobs[0].parts.join('')).toBe(
    '\uFEFFx,note,missing\r\n0,"a,b",\r\n1,"segunda\nlínea",',
  )
  expect(document.querySelector('a')).toBeNull()
})

test('normalizes non-finite JSON numbers instead of emitting invalid JSON tokens', () => {
  downloadJson('resultado.qkd.json', { finite: 1.5, nan: Number.NaN, infinite: Number.NEGATIVE_INFINITY, absent: undefined })

  expect(capturedBlobs[0].parts.join('')).toBe('{\n  "finite": 1.5,\n  "nan": null,\n  "infinite": null\n}')
  expect(capturedBlobs[0].type).toBe('application/json;charset=utf-8')
})

test('exports a finite, labelled and XML-escaped SVG and rejects an empty finite series', () => {
  downloadCurveSvg(
    [{ distance: 0, rate: 2 }, { distance: 10, rate: 1 }],
    'distance',
    'rate',
    { xLabel: 'Distancia <L>', xUnit: 'km', yLabel: 'Tasa & clave', yUnit: 'bit/s' },
  )

  const svg = capturedBlobs[0].parts.join('')
  expect(svg).toContain('<path d="M ')
  expect(svg).toContain('Distancia &lt;L&gt; [km]')
  expect(svg).toContain('Tasa &amp; clave [bit/s]')
  expect(svg).not.toContain('NaN')
  expect(() => downloadCurveSvg([{ distance: Number.NaN, rate: 1 }], 'distance', 'rate')).toThrow(/puntos finitos/)
})

test('sanitizes Unicode, traversal-like separators and empty names', () => {
  expect(safeFileName('Curva QKD — Málaga/../../final')).toBe('Curva_QKD_Malaga_.._.._final')
  expect(safeFileName('***')).toBe('experimento')
  expect(safeFileName('a'.repeat(200))).toHaveLength(120)
})
