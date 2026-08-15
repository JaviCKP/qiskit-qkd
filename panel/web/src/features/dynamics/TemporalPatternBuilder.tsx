import { useMemo, useState } from 'react'
import { Clock3 } from 'lucide-react'

import type { ScenarioPayload } from '@/api/client'
import { readTarget } from '@/features/shared/scenarioPaths'

import {
  buildTemporalSchedule,
  describeTemporalSchedule,
  temporalPatternOptions,
  type TemporalDirection,
  type TemporalDuration,
  type TemporalPatternId,
  type TemporalPhenomenon,
  type TemporalSeverity,
} from './temporalPatterns'

type TemporalPatternBuilderProps = {
  scenario: ScenarioPayload
  onChange: (target: string, value: unknown) => void
}

const phenomenonTargets: Record<TemporalPhenomenon, string> = {
  alignment: 'channel.polarization_rotation_y_rad',
  background: 'channel.background_count_rate_hz',
  error: 'channel.depolarizing_probability',
  eve: 'eavesdropper.intercept_probability',
  loss: 'channel.fixed_loss_db',
  timing: 'timing.clock_offset_s',
}

const patternLabels: Record<TemporalPatternId, string> = {
  burst: 'Pulso de ruido',
  degradation: 'Degradacion gradual',
  drift: 'Deriva',
  recovery: 'Recuperacion',
  stable: 'Estable',
}

const phenomenonOptions: Array<{ id: TemporalPhenomenon; label: string }> = [
  { id: 'loss', label: 'Perdida' },
  { id: 'error', label: 'Error' },
  { id: 'alignment', label: 'Alineacion' },
  { id: 'background', label: 'Fondo' },
  { id: 'timing', label: 'Timing' },
  { id: 'eve', label: 'Eve' },
]

const severityOptions: Array<{ id: TemporalSeverity; label: string }> = [
  { id: 'mild', label: 'Suave' },
  { id: 'moderate', label: 'Media' },
  { id: 'severe', label: 'Severa' },
]

const durationOptions: Array<{ id: TemporalDuration; label: string }> = [
  { id: 'short', label: 'Corta' },
  { id: 'medium', label: 'Media' },
  { id: 'long', label: 'Larga' },
]

const directionLabels: Record<TemporalDirection, string> = {
  decreasing: 'Bajando',
  increasing: 'Subiendo',
  spike: 'Pico',
}

export function TemporalPatternBuilder({ scenario, onChange }: TemporalPatternBuilderProps) {
  const [pattern, setPattern] = useState<TemporalPatternId>('stable')
  const [phenomenon, setPhenomenon] = useState<TemporalPhenomenon>('loss')
  const [severity, setSeverity] = useState<TemporalSeverity>('mild')
  const [duration, setDuration] = useState<TemporalDuration>('short')
  const [direction, setDirection] = useState<TemporalDirection>('increasing')
  const allowedDirections = useMemo<TemporalDirection[]>(
    () => (pattern === 'burst' ? ['spike'] : ['increasing', 'decreasing']),
    [pattern],
  )

  const safeDirection = allowedDirections.includes(direction) ? direction : allowedDirections[0]
  const currentValue = Number(readTarget(scenario, phenomenonTargets[phenomenon]) ?? 0)
  const schedule = useMemo(
    () =>
      buildTemporalSchedule({
        currentValue,
        direction: safeDirection,
        duration,
        pattern,
        phenomenon,
        severity,
      }),
    [currentValue, duration, pattern, phenomenon, safeDirection, severity],
  )
  const technicalDescription = describeTemporalSchedule(schedule)

  return (
    <section className="rounded border border-border bg-surface p-4">
      <div className="flex flex-col gap-2 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-xs uppercase tracking-normal text-slate-500">Dinamica temporal</p>
          <h2 className="mt-1 text-lg font-semibold text-white">Patron temporal</h2>
          <p className="mt-1 text-sm text-slate-400">
            Construye una agenda coherente sin combinar modos temporales incompatibles.
          </p>
        </div>
        <button
          className="flex h-9 items-center justify-center gap-2 rounded border border-cyan px-3 text-sm text-cyan hover:bg-cyan/10"
          onClick={() => onChange('dynamic.parameter_schedules', [schedule])}
          type="button"
        >
          <Clock3 aria-hidden="true" size={16} />
          Aplicar patron
        </button>
      </div>
      <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-5">
        <SelectControl
          label="Modo"
          onChange={(value) => setPattern(value as TemporalPatternId)}
          options={temporalPatternOptions.map((option) => ({
            id: option.id,
            label: patternLabels[option.id],
          }))}
          value={pattern}
        />
        <SelectControl
          label="Fenomeno"
          onChange={(value) => setPhenomenon(value as TemporalPhenomenon)}
          options={phenomenonOptions}
          value={phenomenon}
        />
        <SelectControl
          label="Severidad"
          onChange={(value) => setSeverity(value as TemporalSeverity)}
          options={severityOptions}
          value={severity}
        />
        <SelectControl
          label="Duracion"
          onChange={(value) => setDuration(value as TemporalDuration)}
          options={durationOptions}
          value={duration}
        />
        <SelectControl
          label="Direccion"
          onChange={(value) => setDirection(value as TemporalDirection)}
          options={allowedDirections.map((item) => ({ id: item, label: directionLabels[item] }))}
          value={safeDirection}
        />
      </div>
      <div
        className="mt-4 rounded border border-border bg-background/60 p-3 text-sm text-slate-300"
        title={technicalDescription}
      >
        <span className="text-slate-500">Agenda:</span> {scheduleLabel(schedule.target)} con perfil{' '}
        {schedule.profile.kind}.
      </div>
    </section>
  )
}

function SelectControl({
  label,
  options,
  value,
  onChange,
}: {
  label: string
  options: Array<{ id: string; label: string }>
  value: string
  onChange: (value: string) => void
}) {
  return (
    <label className="block">
      <span className="text-xs text-slate-500">{label}</span>
      <select
        className="mt-1 h-9 w-full rounded border border-border bg-background px-3 text-sm text-white outline-none focus:border-cyan"
        onChange={(event) => onChange(event.target.value)}
        value={value}
      >
        {options.map((option) => (
          <option key={option.id} value={option.id}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  )
}

function scheduleLabel(target: string): string {
  const labels: Record<string, string> = {
    'channel.background_count_rate_hz': 'fondo del canal',
    'channel.depolarizing_probability': 'error de canal',
    'channel.fixed_loss_db': 'perdida fija',
    'channel.polarization_rotation_y_rad': 'alineacion',
    'eavesdropper.intercept_probability': 'interceptacion',
    'timing.clock_offset_s': 'offset de reloj',
  }
  return labels[target] ?? 'parametro seleccionado'
}
