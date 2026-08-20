import { ArrowRight, LineChart, Sparkles } from 'lucide-react'

import type { ScenarioPayload } from '@/api/client'
import { Button } from '@/components/ui'
import {
  buildCurveRequest,
  curveMetricLabel,
  curveRecipes,
  isCurveRequestApplicable,
  type CurveRecipeId,
} from '@/features/curves/recipes'
import type { RunSnapshot } from '@/features/designer/scenarioStore'
import { inferMediumFromScenario, mediumDefinitions } from '@/features/lab/mediums'

export function QuickAnalysis({
  latestRun,
  scenario,
  onOpen,
}: {
  latestRun: RunSnapshot | null
  scenario: ScenarioPayload
  onOpen: (recipeId?: CurveRecipeId, baseRunId?: string) => void
}) {
  const baseScenario = latestRun?.scenario ?? scenario
  const mediumId = inferMediumFromScenario(baseScenario)
  const preferredId = mediumDefinitions[mediumId].defaultCurveRecipeId
  const recipes = curveRecipes
    .filter((recipe) => mediumId === 'custom' || recipe.preferredMedia.includes(mediumId))
    .map((recipe) => ({
      recipe,
      request: buildCurveRequest(recipe.id, mediumId),
    }))
    .filter(({ request }) => isCurveRequestApplicable(request, baseScenario).applicable)
    .sort((left, right) => Number(right.recipe.id === preferredId) - Number(left.recipe.id === preferredId))
    .slice(0, 3)

  return (
    <section className="overflow-hidden rounded-panel border border-border bg-gradient-to-br from-surface to-background">
      <div className="flex flex-col gap-3 border-b border-border px-4 py-4 sm:flex-row sm:items-end sm:justify-between sm:px-5">
        <div>
          <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-violet">
            <Sparkles aria-hidden="true" size={14} /> Siguiente paso
          </p>
          <h2 className="mt-1 text-lg font-semibold text-white">Crea una curva desde este experimento</h2>
          <p className="mt-1 text-sm text-slate-400">
            {latestRun
              ? `El run ${latestRun.digest.slice(0, 10)} será el punto de partida: se mantienen sus ajustes y sólo se varía el eje de la curva.`
              : 'Ejecuta primero para fijar un snapshot reproducible, o prepara una curva desde el draft.'}
          </p>
          {latestRun ? <p className="mt-1 text-xs text-slate-500">Un run es un punto; una curva necesita calcular nuevos puntos alrededor de él.</p> : null}
        </div>
        <Button onClick={() => onOpen(undefined, latestRun?.jobId)} size="sm" tone="ghost" type="button">
          Personalizar curva <ArrowRight aria-hidden="true" size={14} />
        </Button>
      </div>
      <div className="grid gap-2 p-4 sm:grid-cols-3 sm:p-5">
        {recipes.map(({ recipe, request }) => (
          <button
            className="group rounded-panel border border-border bg-surface p-4 text-left transition-colors hover:border-violet/60 hover:bg-raised"
            key={recipe.id}
            onClick={() => onOpen(recipe.id, latestRun?.jobId)}
            type="button"
          >
            <span className="flex items-center justify-between gap-2 text-violet">
              <LineChart aria-hidden="true" size={17} />
              <ArrowRight aria-hidden="true" className="opacity-0 transition group-hover:translate-x-0.5 group-hover:opacity-100" size={15} />
            </span>
            <span className="mt-3 block text-sm font-semibold text-white">{recipe.label}</span>
            <span className="mt-1 block text-xs leading-5 text-slate-500">{recipe.question}</span>
            <span className="mt-3 block font-mono text-2xs text-slate-400">
              {curveMetricLabel(request.metric)} · {axisPointCount(request.axis.values)} puntos
            </span>
          </button>
        ))}
      </div>
    </section>
  )
}

function axisPointCount(values: ReturnType<typeof buildCurveRequest>['axis']['values']): number {
  return Array.isArray(values) ? values.length : values.steps
}
