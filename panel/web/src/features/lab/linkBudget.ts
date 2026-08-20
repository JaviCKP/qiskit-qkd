import type { JsonObject } from '@/api/client'
import type { StackSegment } from '@/components/dataviz'
import { isRecord } from '@/features/shared/scenarioPaths'
import { formatNumber, percent } from '@/lib/format'

export type PhotonRow = {
  id: string
  label: string
  caption?: string
  segments: StackSegment[]
}

/**
 * Decompose the channel loss into the terms the characterisation reports
 * explicitly, attributing whatever is left to the medium's own attenuation.
 *
 * Deliberately does NOT rebuild the total from a formula: which terms apply
 * depends on the channel kind — a free-space link ignores `attenuation_db_km`
 * entirely, for instance — and that rule lives in the library. Taking the
 * residual against the reported `loss_db` keeps the bar exact for every kind.
 */
export function lossBudget(channelState: JsonObject): StackSegment[] {
  const total = numberOr(channelState.loss_db, null)
  if (total === null || total <= 0) return []

  const geometricTransmittance = numberOr(channelState.geometric_transmittance, 1)
  const geometricLoss = geometricTransmittance > 0 && geometricTransmittance < 1
    ? -10 * Math.log10(geometricTransmittance)
    : 0

  const known: StackSegment[] = [
    { id: 'geometric', label: 'Divergencia del haz', value: geometricLoss, slot: 0 },
    { id: 'atmospheric', label: 'Extinción del medio', value: numberOr(channelState.atmospheric_loss_db, 0), slot: 1 },
    { id: 'fixed', label: 'Pérdidas fijas', value: numberOr(channelState.fixed_loss_db, 0), slot: 3 },
    { id: 'pdl', label: 'Pérdida por polarización', value: numberOr(channelState.polarization_dependent_loss_db, 0), slot: 4 },
  ]
  const accounted = known.reduce((sum, segment) => sum + Math.max(0, segment.value), 0)
  const residual = total - accounted

  // A negative residual would mean this attribution disagrees with the library;
  // show the total as one opaque bar rather than assert a wrong split.
  if (residual < -1e-9) {
    return [{ id: 'total', label: 'Pérdida del canal', value: total, slot: 0 }]
  }

  return [
    { id: 'medium', label: 'Atenuación del medio', value: residual, slot: 2 },
    ...known,
  ].filter((segment) => segment.value > 1e-9)
}

/**
 * Per-intensity photon-number statistics. Only weak-coherent style sources
 * report `decoy_probabilities`; anything else has no meaningful split and the
 * caller falls back to the transmission-chain meters.
 */
export function decoyPhotonRows(sourceState: JsonObject): PhotonRow[] | null {
  const intensities = sourceState.decoy_probabilities
  if (!Array.isArray(intensities) || !intensities.length) return null

  const rows = intensities.filter(isRecord).map((intensity, index) => {
    const name = typeof intensity.name === 'string' ? intensity.name : `mu-${index + 1}`
    const mu = numberOr(intensity.mean_photon_number, 0)
    const selection = numberOr(intensity.selection_probability, 0)
    return {
      id: `${name}-${index}`,
      label: decoyLabel(name),
      caption: `μ = ${formatNumber(mu)} · ${percent(selection)}`,
      segments: [
        { id: `${name}-zero`, label: 'Vacío (0 fotones)', value: numberOr(intensity.p_zero, 0), slot: 5 },
        { id: `${name}-one`, label: '1 fotón', value: numberOr(intensity.p_one, 0), slot: 0 },
        { id: `${name}-multi`, label: '≥2 fotones', value: numberOr(intensity.p_multi, 0), slot: 1 },
      ],
    }
  })
  return rows.length ? rows : null
}

function decoyLabel(name: string): string {
  const labels: Record<string, string> = {
    signal: 'Señal',
    decoy: 'Decoy',
    vacuum: 'Vacío',
  }
  return labels[name] ?? name.replaceAll('_', ' ')
}

export function numberOr<T extends number | null>(value: unknown, fallback: T): number | T {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}
