import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import { downloadPlotPng } from './plotExport'

beforeEach(() => {
  Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: vi.fn(() => 'blob:qkd-export') })
  Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() })
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(() => ({ drawImage: vi.fn() } as unknown as CanvasRenderingContext2D))
  vi.spyOn(HTMLCanvasElement.prototype, 'toBlob').mockImplementation((callback) => callback(new Blob(['png'], { type: 'image/png' })))
  vi.stubGlobal('Image', class {
    onload: (() => void) | null = null
    onerror: (() => void) | null = null
    set src(_value: string) {
      setTimeout(() => this.onload?.(), 0)
    }
  })
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

test('rejects an empty chart element instead of downloading a blank PNG', async () => {
  await expect(downloadPlotPng(document.createElement('div'), 'curve.png')).rejects.toThrow(/SVG/)
})

test('rasterizes a non-empty SVG and downloads a PNG blob', async () => {
  const element = document.createElement('div')
  element.innerHTML = '<svg viewBox="0 0 10 10"><path d="M0 0 L10 10" /></svg>'

  await downloadPlotPng(element, 'curve.png')

  expect(URL.createObjectURL).toHaveBeenCalledTimes(2)
  expect(URL.revokeObjectURL).toHaveBeenCalled()
  expect(document.querySelector('a')).toBeNull()
})
