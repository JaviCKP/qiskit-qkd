/**
 * Categorical series palette for every chart in the panel.
 *
 * These hex values mirror `--chart-1..--chart-6` in `src/index.css`; keep the
 * two in sync. CSS-driven marks (the stacked bars and meters) read the custom
 * properties, while SVG traces built in TypeScript need literal hex because
 * they compose alpha suffixes (`${color}33`) for confidence bands.
 *
 * The slot ORDER is the colour-blind-safety mechanism, not decoration: this
 * sequence was validated on the panel surface (#0E141B) for the adjacent-pair
 * list — lightness band, chroma floor, CVD separation, normal-vision floor and
 * contrast all pass. Re-validate before reordering or substituting a hue.
 */
export const seriesPalette = [
  '#3987e5', // blue
  '#d95926', // orange
  '#199e70', // aqua
  '#c98500', // yellow
  '#d55181', // magenta
  '#008300', // green
] as const

/**
 * The same slots as CSS custom properties, for marks coloured through
 * `style`/`backgroundColor` rather than an SVG attribute.
 */
export const chartSlots = [
  'var(--chart-1)',
  'var(--chart-2)',
  'var(--chart-3)',
  'var(--chart-4)',
  'var(--chart-5)',
  'var(--chart-6)',
] as const

/** `rgb()` string for categorical slot `index` (0-based), at `alpha` opacity. */
export function chartColor(index: number, alpha = 1): string {
  const slot = chartSlots[index] ?? chartSlots[chartSlots.length - 1]
  return alpha === 1 ? `rgb(${slot})` : `rgb(${slot} / ${alpha})`
}

/** Dash patterns used as the secondary channel once hues run out. */
const dashCycle = [undefined, 'dash', 'dot'] as const

export type SeriesStyle = {
  color: string
  dash?: string
}

/**
 * Style for series `index`, assigned in fixed order and never cycled on hue
 * alone: past the sixth series the palette repeats but pairs each hue with a
 * different dash pattern, so identity stays unique (composite encoding) instead
 * of two unrelated series silently sharing a colour.
 */
export function seriesStyle(index: number): SeriesStyle {
  const safeIndex = Math.max(0, index)
  const color = seriesPalette[safeIndex % seriesPalette.length]
  const dash = dashCycle[Math.floor(safeIndex / seriesPalette.length) % dashCycle.length]
  return dash ? { color, dash } : { color }
}
