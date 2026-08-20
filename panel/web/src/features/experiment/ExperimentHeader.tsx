import type { ReactNode } from 'react'
import { AlertTriangle, Copy, Download, Fingerprint, Gauge, Save } from 'lucide-react'

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

  const warningCount = validationIssues.filter((issue) => issue.severity === 'warning').length
  const statusTone = hasErrors ? 'danger' : isValidating ? 'warning' : 'success'

  return (
    <section className="border-b border-border bg-surface/55 px-4 py-5 backdrop-blur sm:px-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0 flex-1">
          <label className="block max-w-2xl">
            <span className="sr-only">Nombre del experimento</span>
            <input
              aria-label="Nombre del experimento"
              className="w-full rounded-control border border-transparent bg-transparent px-2 py-1 -ml-2 text-2xl font-semibold tracking-tight text-white outline-none transition-colors placeholder:text-slate-600 hover:border-border hover:bg-background/40 focus:border-cyan/50 focus:bg-background/60 sm:text-3xl"
              maxLength={200}
              onChange={(event) => setExperimentName(event.target.value)}
              value={experimentName}
            />
          </label>
          <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
            <span className="font-medium text-slate-300">{medium.label}</span>
            <span aria-hidden="true" className="text-slate-700">•</span>
            <span className="font-mono text-xs uppercase text-slate-400">{scenario.protocol.name.toUpperCase()}</span>
            <span aria-hidden="true" className="text-slate-700">•</span>
            <StatusDot tone={statusTone}>
              {hasErrors ? 'Validación errónea' : isValidating ? 'Validación pendiente' : 'Configuración válida'}
            </StatusDot>
            {draftModified ? <><span aria-hidden="true" className="text-slate-700">•</span><StatusDot tone="warning">Borrador modificado</StatusDot></> : null}
            {unsavedChanges ? <><span aria-hidden="true" className="text-slate-700">•</span><StatusDot tone="warning">Cambios sin guardar</StatusDot></> : null}
            {dirty ? <><span aria-hidden="true" className="text-slate-700">•</span><StatusDot tone="warning">Cambios sin ejecutar</StatusDot></> : null}
          </div>
        </div>
        <div className="flex flex-wrap gap-2 lg:justify-end">
          <Button onClick={onDuplicate} size="sm" tone="ghost" type="button">
            <Copy aria-hidden="true" size={14} /> Duplicar
          </Button>
          <Button onClick={onExport} size="sm" tone="neutral" type="button">
            <Download aria-hidden="true" size={14} /> Exportar
          </Button>
          <Button disabled={!experimentName.trim()} loading={saving} onClick={onSave} size="sm" tone="success" type="button">
            <Save aria-hidden="true" size={14} /> {sourceExperimentId ? 'Guardar cambios' : 'Guardar'}
          </Button>
        </div>
      </div>
      <div className="mt-4 flex flex-wrap gap-2 text-xs text-slate-500">
        <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-background/60 px-3 py-1.5">
          <Gauge aria-hidden="true" size={13} />
          {costLabel(inspection?.cost_estimate)}
        </span>
        <span
          className="inline-flex max-w-full items-center gap-1.5 truncate rounded-full border border-border bg-background/60 px-3 py-1.5 font-mono"
          title={inspection?.digest}
        >
          <Fingerprint aria-hidden="true" className="shrink-0" size={13} />
          snapshot {inspection?.digest ? inspection.digest.slice(0, 12) : 'pendiente'}
        </span>
        {warningCount ? (
          <span className="inline-flex items-center gap-1.5 rounded-full border border-warning/30 bg-warning/5 px-3 py-1.5 text-warning">
            <AlertTriangle aria-hidden="true" size={13} />
            {warningCount} {warningCount === 1 ? 'aviso' : 'avisos'}
          </span>
        ) : null}
      </div>
      <div className="mt-4 overflow-x-auto border-t border-border pt-3">
        <WorkflowStepper onSelect={onWorkflowSelect} states={workflowStates} />
      </div>
    </section>
  )
}

/** Status text with a leading dot, so state never rides on colour alone. */
function StatusDot({ tone, children }: { tone: 'success' | 'warning' | 'danger'; children: ReactNode }) {
  const toneClass = { success: 'text-success', warning: 'text-warning', danger: 'text-danger' }[tone]
  return (
    <span className={`inline-flex items-center gap-1.5 ${toneClass}`}>
      <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-current" />
      {children}
    </span>
  )
}

function costLabel(cost?: CostEstimate): string {
  if (!cost) return 'Calculando coste…'
  return `${cost.total_pulse_events.toLocaleString('es-ES')} señales · ${cost.estimated_max_shots.toLocaleString('es-ES')} shots máx.`
}
