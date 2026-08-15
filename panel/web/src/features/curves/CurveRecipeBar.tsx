import { useEffect, useMemo, useState } from 'react'
import { ChevronDown, LineChart } from 'lucide-react'

import type { ScenarioPayload } from '@/api/client'
import type { MediumId } from '@/features/lab/mediums'

import {
  buildCurveRequest,
  curveMetricLabel,
  curveRecipes,
  describeCurveRequest,
  isCurveRequestApplicable,
  type CurveRecipeId,
  type CurveRequest,
} from './recipes'

type CurveRecipeBarProps = {
  mediumId: MediumId
  activeRecipeId: CurveRecipeId
  onChange: (request: CurveRequest) => void
  scenario: ScenarioPayload
}

export function CurveRecipeBar({
  mediumId,
  activeRecipeId,
  onChange,
  scenario,
}: CurveRecipeBarProps) {
  const [previewOpen, setPreviewOpen] = useState(false)
  const availableRecipes = useMemo(
    () =>
      curveRecipes.filter(
        (recipe) => mediumId === 'custom' || recipe.preferredMedia.includes(mediumId),
      ),
    [mediumId],
  )
  const fallbackRecipeId = availableRecipes[0]?.id ?? 'custom-axis'
  const activeAvailableId = availableRecipes.some((recipe) => recipe.id === activeRecipeId)
    ? activeRecipeId
    : fallbackRecipeId
  const selectedRecipeId = activeAvailableId

  const request = useMemo(
    () => buildCurveRequest(selectedRecipeId, mediumId),
    [mediumId, selectedRecipeId],
  )
  const selectedRecipe =
    availableRecipes.find((recipe) => recipe.id === selectedRecipeId) ?? availableRecipes[0]
  const applicability = isCurveRequestApplicable(request, scenario)

  useEffect(() => {
    onChange(request)
  }, [onChange, request])

  if (!selectedRecipe) {
    return null
  }

  return (
    <section className="rounded border border-border bg-surface p-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-xs uppercase tracking-normal text-slate-500">Curvas guiadas</p>
          <h2 className="mt-1 text-lg font-semibold text-white">{selectedRecipe.label}</h2>
          <p className="mt-1 text-sm text-slate-400">{selectedRecipe.question}</p>
        </div>
        <button
          className="flex h-9 items-center justify-center gap-2 rounded border border-border px-3 text-sm text-slate-300 hover:border-cyan hover:text-cyan"
          onClick={() => setPreviewOpen((open) => !open)}
          type="button"
        >
          <LineChart aria-hidden="true" size={16} />
          Avanzado
          <ChevronDown
            aria-hidden="true"
            className={previewOpen ? 'rotate-180 transition' : 'transition'}
            size={15}
          />
        </button>
      </div>
      <div className="mt-4 flex gap-2 overflow-x-auto pb-1">
        {availableRecipes.map((recipe) => {
          const active = recipe.id === selectedRecipeId
          return (
            <button
              className={`min-w-[190px] rounded border px-3 py-2 text-left text-sm ${
                active
                  ? 'border-cyan bg-cyan/10 text-cyan'
                  : 'border-border bg-background/50 text-slate-300 hover:border-slate-500'
              }`}
              key={recipe.id}
              onClick={() => onChange(buildCurveRequest(recipe.id, mediumId))}
              type="button"
            >
              <span className="block font-medium">{recipe.label}</span>
              <span className="mt-1 block text-xs text-slate-500">
                {curveMetricLabel(recipe.metric)}
              </span>
            </button>
          )
        })}
      </div>
      <p className="mt-3 text-sm text-slate-300">{describeCurveRequest(request)}</p>
      <p className={`mt-2 text-xs ${applicability.applicable ? 'text-cyan' : 'text-warning'}`}>
        {applicability.applicable
          ? 'Aplicable al escenario efectivo.'
          : applicability.reasons.join(' ')}
      </p>
      {previewOpen ? (
        <div className="mt-4 rounded border border-border bg-background/60 p-3 text-xs">
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-4">
            <PreviewItem label="Métrica" value={curveMetricLabel(request.metric)} />
            <PreviewItem label="Eje" value={targetLabel(request.axis.target)} />
            <PreviewItem label="Muestras" value={axisValuesLabel(request)} />
            <PreviewItem label="Ajuste de escenario" value={request.scenarioPatch ? 'sí' : 'no'} />
          </div>
          <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
            <PreviewList items={request.changes} label="Qué cambia" />
            <PreviewList items={request.fixed} label="Qué queda fijo" />
            <PreviewList items={request.requirements} label="Condiciones" />
          </div>
        </div>
      ) : null}
    </section>
  )
}

function PreviewList({ items, label }: { items: string[]; label: string }) {
  return (
    <div>
      <p className="text-slate-500">{label}</p>
      <ul className="mt-1 space-y-1 text-slate-300">
        {items.map((item) => (
          <li key={item}>· {item}</li>
        ))}
      </ul>
    </div>
  )
}

function PreviewItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-slate-500">{label}</p>
      <p className="mt-1 break-words font-mono text-slate-200">{value}</p>
    </div>
  )
}

function axisValuesLabel(request: CurveRequest): string {
  const values = request.axis.values
  if (Array.isArray(values)) {
    return `${values.length} valores`
  }
  return `${values.steps} puntos`
}

function targetLabel(target: string): string {
  const labels: Record<string, string> = {
    'scenario.pulses': 'pulsos',
    'channel.distance_km': 'distancia',
    'detector.dark_count_rate_hz': 'ruido oscuro',
    'source.mean_photon_number': 'fotones medios',
    'eavesdropper.intercept_probability': 'interceptacion',
    'channel.depolarizing_probability': 'despolarizacion',
    'channel.pointing_jitter_rad': 'apuntamiento',
    'channel.atmospheric_extinction_db_km': 'atmosfera',
    'channel.underwater_extinction_m_inv': 'extincion submarina',
    'time_s': 'tiempo',
  }
  return labels[target] ?? 'parametro'
}
