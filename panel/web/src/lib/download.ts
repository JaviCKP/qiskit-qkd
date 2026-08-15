import type { JsonValue } from '@/api/client'

import { curvePointSegments } from './curveData'

export function downloadCsv(rows: Array<{ [key: string]: unknown }>, fileName: string): void {
  const headers = Array.from(new Set(rows.flatMap((row) => Object.keys(row))))
  const csv = [
    headers.map(csvCell).join(','),
    ...rows.map((row) => headers.map((header) => csvCell(row[header])).join(',')),
  ].join('\r\n')
  downloadBlob(ensureExtension(fileName, '.csv'), `\uFEFF${csv}`, 'text/csv;charset=utf-8')
}

export function downloadCurveSvg(
  rows: Array<{ [key: string]: unknown }>,
  xKey: string,
  yKey: string,
  labels: { xLabel: string; xUnit: string | null; yLabel: string; yUnit: string | null } = {
    xLabel: xKey,
    xUnit: null,
    yLabel: yKey,
    yUnit: null,
  },
): void {
  const width = 960
  const height = 560
  const margin = { top: 66, right: 36, bottom: 78, left: 92 }
  const segments = curvePointSegments(rows, xKey, yKey)
  const points = segments.flat()
  if (!points.length) throw new Error('No hay puntos finitos para exportar como SVG.')
  const xs = points.map(([x]) => x)
  const ys = points.map(([, y]) => y)
  const [minX, maxX] = paddedDomain(Math.min(...xs), Math.max(...xs))
  const [minY, maxY] = paddedDomain(Math.min(...ys), Math.max(...ys))
  const project = ([x, y]: readonly [number, number]) => ({
    x: margin.left + ((x - minX) / (maxX - minX)) * (width - margin.left - margin.right),
    y: height - margin.bottom - ((y - minY) / (maxY - minY)) * (height - margin.top - margin.bottom),
  })
  const path = segments.map((segment) => segment.map((point, index) => {
    const projected = project(point)
    return `${index === 0 ? 'M' : 'L'} ${projected.x.toFixed(2)} ${projected.y.toFixed(2)}`
  }).join(' ')).join(' ')
  const markers = points.map((point) => {
    const projected = project(point)
    return `<circle cx="${projected.x.toFixed(2)}" cy="${projected.y.toFixed(2)}" r="3" fill="#2fc8de"/>`
  }).join('')
  const title = `${labels.yLabel} frente a ${labels.xLabel}`
  const xLabel = `${labels.xLabel}${labels.xUnit ? ` [${labels.xUnit}]` : ''}`
  const yLabel = `${labels.yLabel}${labels.yUnit ? ` [${labels.yUnit}]` : ''}`
  const ticks = Array.from({ length: 6 }, (_, index) => {
    const ratio = index / 5
    const x = margin.left + ratio * (width - margin.left - margin.right)
    const y = height - margin.bottom - ratio * (height - margin.top - margin.bottom)
    const xValue = minX + ratio * (maxX - minX)
    const yValue = minY + ratio * (maxY - minY)
    return `<line x1="${x}" y1="${height - margin.bottom}" x2="${x}" y2="${height - margin.bottom + 6}" stroke="#64748b"/><text x="${x}" y="${height - margin.bottom + 24}" text-anchor="middle" fill="#64748b" font-size="12">${escapeXml(formatTick(xValue))}</text><line x1="${margin.left - 6}" y1="${y}" x2="${margin.left}" y2="${y}" stroke="#64748b"/><text x="${margin.left - 12}" y="${y + 4}" text-anchor="end" fill="#64748b" font-size="12">${escapeXml(formatTick(yValue))}</text>`
  }).join('')
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-labelledby="title desc"><title id="title">${escapeXml(title)}</title><desc id="desc">Curva exportada con ${points.length} puntos finitos.</desc><rect width="100%" height="100%" fill="#0b0f12"/><text x="${margin.left}" y="34" fill="#e2e8f0" font-family="system-ui" font-size="18" font-weight="600">${escapeXml(title)}</text><line x1="${margin.left}" y1="${height - margin.bottom}" x2="${width - margin.right}" y2="${height - margin.bottom}" stroke="#64748b"/><line x1="${margin.left}" y1="${margin.top}" x2="${margin.left}" y2="${height - margin.bottom}" stroke="#64748b"/>${ticks}<path d="${path}" fill="none" stroke="#2fc8de" stroke-width="2"/>${markers}<text x="${(margin.left + width - margin.right) / 2}" y="${height - 22}" text-anchor="middle" fill="#94a3b8" font-family="system-ui" font-size="13">${escapeXml(xLabel)}</text><text x="24" y="${height / 2}" text-anchor="middle" transform="rotate(-90 24 ${height / 2})" fill="#94a3b8" font-family="system-ui" font-size="13">${escapeXml(yLabel)}</text></svg>`
  downloadBlob(`${safeFileName(yKey)}-vs-${safeFileName(xKey)}.svg`, svg, 'image/svg+xml;charset=utf-8')
}

export function downloadJson(fileName: string, value: unknown): void {
  downloadBlob(ensureExtension(fileName, '.json'), JSON.stringify(normalizeFiniteJson(value), null, 2), 'application/json;charset=utf-8')
}

export function downloadBlob(fileName: string, value: string, type: string): void {
  const blob = new Blob([value], { type })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = safeDownloadName(fileName)
  link.hidden = true
  document.body.append(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1_000)
}

export function safeFileName(value: string): string {
  return value.normalize('NFKD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9._-]+/gi, '_').replace(/^_+|_+$/g, '').slice(0, 120) || 'experimento'
}

export function csvCell(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'number') return Number.isFinite(value) ? String(value) : ''
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  const text = typeof value === 'string' ? value : JSON.stringify(normalizeFiniteJson(value))
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text
}

function normalizeFiniteJson(value: unknown): JsonValue {
  if (value === null) return null
  if (typeof value === 'string') return value
  if (typeof value === 'boolean') return value
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  if (Array.isArray(value)) return value.map(normalizeFiniteJson)
  if (typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).filter(([, item]) => item !== undefined).map(([key, item]) => [key, normalizeFiniteJson(item)]))
  }
  return String(value)
}

function paddedDomain(minimum: number, maximum: number): [number, number] {
  if (minimum !== maximum) return [minimum, maximum]
  const padding = Math.max(1, Math.abs(minimum) * 0.05)
  return [minimum - padding, maximum + padding]
}

function formatTick(value: number): string {
  const absolute = Math.abs(value)
  return absolute !== 0 && (absolute < 0.001 || absolute >= 100_000) ? value.toExponential(2) : value.toFixed(2).replace(/\.00$/, '')
}

function ensureExtension(fileName: string, extension: string): string {
  return fileName.toLowerCase().endsWith(extension) ? fileName : `${fileName}${extension}`
}

function safeDownloadName(fileName: string): string {
  const lastDot = fileName.lastIndexOf('.')
  if (lastDot <= 0) return safeFileName(fileName)
  const base = safeFileName(fileName.slice(0, lastDot))
  const extension = fileName.slice(lastDot).replace(/[^a-z0-9.]/gi, '')
  return `${base}${extension}`
}

function escapeXml(value: string): string {
  return value.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&apos;')
}
