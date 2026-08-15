import { Copy, Download, Save } from 'lucide-react'

import type { ApiValidationIssue, CostEstimate, ScenarioInspection } from '@/api/client'
import { Button } from '@/components/ui'
import { useDesignerStore } from '@/features/designer/scenarioStore'
import { mediumDefinitions } from '@/features/lab/mediums'
import { WorkflowStepper, type WorkflowStepId, type WorkflowStepState } from './WorkflowStepper'

export function ExperimentHeader({
  inspection,
  validationIssues,
  isValidating,
  dirty,
  draftModified,
  unsavedChanges,
  saving,
  onSave,
  onDuplicate,
  onExport,
  workflowStates,
  onWorkflowSelect,
}: {
  inspection?: ScenarioInspection
  validationIssues: ApiValidationIssue[]
  isValidating: boolean
  dirty: boolean
  draftModified: boolean
  unsavedChanges: boolean
  saving: boolean
  onSave: () => void
  onDuplicate: () => void
  onExport: () => void
  workflowStates: { [step in WorkflowStepId]: WorkflowStepState }
  onWorkflowSelect: (step: WorkflowStepId) => void
}) {
  const scenario = useDesignerStore((state) => state.scenario)
  const experimentName = useDesignerStore((state) => state.experimentName)
  const setExperimentName = useDesignerStore((state) => state.setExperimentName)
  const activeMediumId = useDesignerStore((state) => state.activeMediumId)
  const sourceExperimentId = useDesignerStore((state) => state.sourceExperimentId)
  const medium = mediumDefinitions[activeMediumId]
  const hasErrors = validationIssues.some((issue) => issue.severity !== 'warning')

  return (
    <section className="border-b border-border bg-surface/55 px-4 py-5 backdrop-blur sm:px-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0 flex-1">
          <label className="block max-w-2xl">
            <span className="sr-only">Nombre del experimento</span>
            <input
              aria-label="Nombre del experimento"
              className="w-full border-0 bg-transparent p-0 text-2xl font-semibold tracking-tight text-white outline-none placeholder:text-slate-600 focus:text-cyan sm:text-3xl"
              maxLength={200}
              onChange={(event) => setExperimentName(event.target.value)}
              value={experimentName}
            />
          </label>
          <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-slate-400">
            <span className="font-medium text-slate-300">{medium.label}</span>
            <span aria-hidden="true" className="text-slate-700">•</span>
            <span>{scenario.protocol.name.toUpperCase()}</span>
            <span aria-hidden="true" className="text-slate-700">•</span>
            <span className={hasErrors ? 'text-danger' : isValidating ? 'text-warning' : 'text-success'}>
              {hasErrors ? 'Validación errónea' : isValidating ? 'Validación pendiente' : 'Configuración válida'}
            </span>
            {draftModified ? (
              <>
                <span aria-hidden="true" className="text-slate-700">•</span>
                <span className="text-warning">Borrador modificado</span>
              </>
            ) : null}
            {unsavedChanges ? (
              <>
                <span aria-hidden="true" className="text-slate-700">-</span>
                <span className="text-warning">Cambios sin guardar</span>
              </>
            ) : null}
            {dirty ? (
              <>
                <span aria-hidden="true" className="text-slate-700">-</span>
                <span className="text-warning">Cambios sin ejecutar</span>
              </>
            ) : null}
          </div>
        </div>
        <div className="flex flex-wrap gap-2 lg:justify-end">
          <Button onClick={onDuplicate} size="sm" tone="ghost" type="button">
            <Copy aria-hidden="true" size={14} /> Duplicar
          </Button>
          <Button onClick={onExport} size="sm" tone="neutral" type="button">
            <Download aria-hidden="true" size={14} /> Exportar
          </Button>
          <Button disabled={saving || !experimentName.trim()} onClick={onSave} size="sm" tone="success" type="button">
            <Save aria-hidden="true" size={14} /> {sourceExperimentId ? 'Guardar cambios' : 'Guardar'}
          </Button>
        </div>
      </div>
      <div className="mt-4 flex flex-wrap gap-2 text-xs text-slate-500">
        <span className="rounded-full border border-border bg-background/60 px-3 py-1.5">
          {costLabel(inspection?.cost_estimate)}
        </span>
        <span className="max-w-full truncate rounded-full border border-border bg-background/60 px-3 py-1.5 font-mono" title={inspection?.digest}>
          snapshot {inspection?.digest ? inspection.digest.slice(0, 12) : 'pendiente'}
        </span>
        {validationIssues.filter((issue) => issue.severity === 'warning').length ? (
          <span className="rounded-full border border-warning/30 bg-warning/5 px-3 py-1.5 text-warning">
            {validationIssues.filter((issue) => issue.severity === 'warning').length} avisos
          </span>
        ) : null}
      </div>
      <div className="mt-4 overflow-x-auto border-t border-border pt-3">
        <WorkflowStepper onSelect={onWorkflowSelect} states={workflowStates} />
      </div>
    </section>
  )
}

function costLabel(cost?: CostEstimate): string {
  if (!cost) return 'Calculando coste…'
  return `${cost.total_pulse_events.toLocaleString('es-ES')} señales · ${cost.estimated_max_shots.toLocaleString('es-ES')} shots máx.`
}
