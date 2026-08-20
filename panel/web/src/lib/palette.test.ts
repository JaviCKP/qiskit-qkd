import { expect, test } from 'vitest'

import { chartColor, seriesPalette, seriesStyle } from './palette'

test('assigns categorical hues in fixed slot order', () => {
  expect(seriesStyle(0).color).toBe(seriesPalette[0])
  expect(seriesStyle(2).color).toBe(seriesPalette[2])
  expect(seriesStyle(0).dash).toBeUndefined()
})

test('keeps identity unique past the palette with a second channel', () => {
  const first = seriesStyle(0)
  const seventh = seriesStyle(seriesPalette.length)

  // The hue repeats — but the dash pattern does not, so the two series are
  // still distinguishable instead of silently sharing an appearance.
  expect(seventh.color).toBe(first.color)
  expect(seventh.dash).toBe('dash')
  expect(seriesStyle(seriesPalette.length * 2).dash).toBe('dot')
})

test('colour depends only on the slot index, never on neighbouring series', () => {
  const styles = [0, 1, 2, 3].map((index) => seriesStyle(index).color)

  // Dropping a series must not repaint the survivors: slot 2 stays slot 2.
  expect(seriesStyle(2).color).toBe(styles[2])
  expect(new Set(styles).size).toBe(4)
})

test('exposes CSS-variable colours for style-driven marks', () => {
  expect(chartColor(0)).toBe('rgb(var(--chart-1))')
  expect(chartColor(1, 0.4)).toBe('rgb(var(--chart-2) / 0.4)')
})

test('clamps an out-of-range slot to the last hue instead of returning undefined', () => {
  expect(chartColor(99)).toBe('rgb(var(--chart-6))')
})
