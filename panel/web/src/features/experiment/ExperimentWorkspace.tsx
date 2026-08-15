import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'

import {
  ApiError,
  createExperiment,
  replaceExperiment,
  type ApiValidationIssue,
  type CatalogSection,
  type ScenarioInspection,
} from '@/api/client'
import { queryClient } from '@/app/queryClient'
import { ApiErrorSummary, Button, Dialog, LoadingBlock, ValidationSummary } from '@/components/ui'
import type { CurveRecipeId } from '@/features/curves/recipes'
import {
  curveToJson,
  runToJson,
  useDesignerStore,
} from '@/features/designer/scenarioStore'
import { LinkCockpit } from '@/features/lab/LinkCockpit'
import { MediumGallery } from '@/features/lab/MediumGallery'
import { mediumOptions, type MediumId } from '@/features/lab/mediums'
import { FocusedInspector } from '@/features/designer/FocusedInspector'
import { ExecutionView } from '@/features/results/ExecutionView'
import { QuickAnalysis } from '@/features/results/QuickAnalysis'
import { downloadJson, safeFileName } from '@/lib/download'

import { ExperimentHeader } from './ExperimentHeader'
import { PhysicalFlowBuilder } from './PhysicalFlowBuilder'
import type { WorkflowStepId, WorkflowStepState } from './WorkflowStepper'

export function ExperimentWorkspace({
  inspection,
  inspectionError,
  isValidating,
  validationIssues,
  sections,
  onOpenAnalysis,
  apiOffline = false,
}: {
  inspection?: ScenarioInspection
  inspectionError: Error | null
  isValidating: boolean
  validationIssues: ApiValidationIssue[]
  sections: CatalogSection[]
  onOpenAnalysis: (recipeId?: CurveRecipeId, baseRunId?: string) => void
  apiOffline?: boolean
}) {
  const scenario = useDesignerStore((state) => state.scenario)
  const experimentName = useDesignerStore((state) => state.experimentName)
  const sourceExperimentId = useDesignerStore((state) => state.sourceExperimentId)
  const editedFields = useDesignerStore((state) => state.editedFields)
  const runs = useDesignerStore((state) => state.runs)
  const curves = useDesignerStore((state) => state.curves)
  const activeMediumId = useDesignerStore((state) => state.activeMediumId)
  const hasUnsavedChanges = useDesignerStore((state) => state.hasUnsavedChanges)
  const updateField = useDesignerStore((state) => state.updateField)
  const selectMedium = useDesignerStore((state) => state.selectMedium)
  const duplicateWorkspace = useDesignerStore((state) => state.duplicateWorkspace)
  const markSaved = useDesignerStore((state) => state.markSaved)
  const [pendingMedium, setPendingMedium] = useState<MediumId | null>(null)
  const [expertMode, setExpertMode] = useState(false)
  const latestRun = runs.at(-1) ?? null
  const offline = apiOffline || Boolean(inspectionError && !(inspectionError instanceof ApiError && inspectionError.issues.length))
  const dirty = Boolean(latestRun && inspection?.digest && inspection.digest !== latestRun.digest)
  const draftModified = hasUnsavedChanges || editedFields.length > 0
  const writePayload = () => ({
    name: experimentName.trim(),
    scenario,
    tags: [scenario.protocol.name, activeMediumId],
    schema_version: 2,
    runs: runs.map(runToJson),
    curves: curves.map(curveToJson),
    curve_recipes: curves.map((curve) => ({
      axis: curve.axis,
      series: curve.series,
      metric: curve.metric,
      repeats: curve.repeats,
      base_digest: curve.baseDigest,
    })),
    last_result: latestRun?.result ?? null,
    provenance: {
      created_by: 'qkd-panel',
      active_medium: activeMediumId,
      exported_at: new Date().toISOString(),
    },
  })
  const save = useMutation({
    mutationFn: () => sourceExperimentId
      ? replaceExperiment(sourceExperimentId, writePayload())
      : createExperiment(writePayload()),
    onSuccess: ({ experiment }) => {
      markSaved(experiment)
      void queryClient.invalidateQueries({ queryKey: ['experiments'] })
    },
  })
  const requestMedium = (mediumId: MediumId) => {
    if (mediumId === activeMediumId) return
    if (hasUnsavedChanges) {
      setPendingMedium(mediumId)
      return
    }
    selectMedium(mediumId)
  }
  const workflowStates: { [step in WorkflowStepId]: WorkflowStepState } = {
    configure: expertMode || draftModified ? 'current' : latestRun ? 'complete' : 'current',
    validate: validationIssues.some((issue) => issue.severity !== 'warning') ? 'attention' : isValidating ? 'current' : 'complete',
    execute: latestRun ? 'complete' : 'current',
    analyse: curves.length ? 'complete' : latestRun ? 'pending' : 'pending',
    save: sourceExperimentId && !hasUnsavedChanges ? 'complete' : hasUnsavedChanges ? 'attention' : 'pending',
  }
  const onWorkflowSelect = (step: WorkflowStepId) => {
    const ids: Partial<Record<WorkflowStepId, string>> = {
      configure: 'configuration-flow',
      validate: 'validation-summary',
      execute: 'execution-panel',
      analyse: 'analysis-panel',
    }
    const target = ids[step]
    if (target) document.getElementById(target)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    if (step === 'save') document.querySelector<HTMLInputElement>('[aria-label="Nombre del experimento"]')?.focus()
  }

  return (
    <div className="min-w-0">
      <ExperimentHeader
        dirty={dirty}
        draftModified={draftModified}
        inspection={inspection}
        isValidating={isValidating}
        onDuplicate={duplicateWorkspace}
        onExport={() => downloadJson(`${safeFileName(experimentName)}.qkd.json`, writePayload())}
        onSave={() => save.mutate()}
        onWorkflowSelect={onWorkflowSelect}
        saving={save.isPending}
        unsavedChanges={hasUnsavedChanges}
        validationIssues={validationIssues}
        workflowStates={workflowStates}
      />
      <div className="sticky bottom-3 z-20 mx-4 mt-3 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-cyan/25 bg-surface/95 px-3 py-2 shadow-2xl backdrop-blur sm:mx-6">
        <span className="text-xs text-slate-400">{hasUnsavedChanges ? 'Cambios pendientes de guardar' : dirty ? 'Draft distinto al último run' : 'Listo para ejecutar'}</span>
        <div className="flex flex-wrap gap-2">
          <Button disabled={save.isPending || !experimentName.trim()} onClick={() => save.mutate()} size="sm" tone="success" type="button">
            Guardar
          </Button>
          <Button disabled={offline} onClick={() => window.dispatchEvent(new Event('qkd:request-run'))} size="sm" tone="primary" type="button">
            Ejecutar
          </Button>
        </div>
      </div>
      <div className="space-y-6 px-4 py-5 sm:px-6 lg:py-7">
        {save.data ? (
          <p aria-live="polite" className="text-sm text-success">
            Experimento guardado como <span className="font-mono">{save.data.experiment.id}</span>.
          </p>
        ) : null}
        {save.error ? <ApiErrorSummary error={save.error} /> : null}
        {inspectionError && !(inspectionError instanceof ApiError && inspectionError.issues.length) ? (
          <ApiErrorSummary error={inspectionError} />
        ) : null}
        {!inspection && isValidating ? <LoadingBlock label="Validando escenario" /> : null}

        <MediumGallery activeMediumId={activeMediumId} media={mediumOptions} onOpen={requestMedium} />

        <div aria-label="Cockpit del enlace" id="link-cockpit">
          <LinkCockpit
            channelState={inspection?.characterizations.channel ?? {}}
            detectorState={inspection?.characterizations.detector ?? {}}
            effectiveScenario={inspection?.effective_scenario ?? scenario}
            mediumId={activeMediumId}
            sourceState={inspection?.characterizations.source ?? {}}
            timingState={inspection?.characterizations.timing ?? {}}
          />
        </div>

        <div id="configuration-flow">
          <PhysicalFlowBuilder
            editedFields={editedFields}
            errors={validationIssues}
            mediumId={activeMediumId}
            onChange={updateField}
            onSelectMedium={requestMedium}
            scenario={scenario}
            sections={sections}
          />
        </div>

        <section className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-surface/60 px-4 py-3" aria-label="Modo de edición">
          <div>
            <p className="text-sm font-medium text-white">Inspector técnico</p>
            <p className="mt-1 text-xs text-slate-400">Abre todos los controles del catálogo sin perder el cockpit.</p>
          </div>
          <Button aria-pressed={expertMode} onClick={() => setExpertMode((value) => !value)} size="sm" tone={expertMode ? 'primary' : 'neutral'} type="button">
            {expertMode ? 'Cerrar modo experto' : 'Abrir modo experto'}
          </Button>
        </section>
        {expertMode ? (
          <FocusedInspector
            editedFields={editedFields}
            errors={validationIssues}
            mediumId={activeMediumId}
            onChange={updateField}
            scenario={scenario}
            sections={sections}
          />
        ) : null}

        {validationIssues.length ? <div id="validation-summary"><ValidationSummary issues={validationIssues} /></div> : null}

        <div id="execution-panel">
          <ExecutionView
            apiOffline={offline}
            costEstimate={inspection?.cost_estimate}
            currentDigest={inspection?.digest ?? null}
            scenario={scenario}
            validationBlocked={validationIssues.some((issue) => issue.severity !== 'warning')}
          />
        </div>
        <div id="analysis-panel"><QuickAnalysis latestRun={latestRun} onOpen={onOpenAnalysis} scenario={scenario} /></div>
      </div>
      {pendingMedium ? (
        <Dialog
          description={`Cambiar a ${mediumOptions.find((medium) => medium.id === pendingMedium)?.label ?? pendingMedium} reemplaza los valores editados del borrador actual y reinicia su nombre y medio. Se conservan los runs y curvas ya completados.`}
          onClose={() => setPendingMedium(null)}
          open
          title="Confirmar cambio de medio"
        >
          <div className="space-y-4">
            <p className="text-sm leading-6 text-slate-300">Se conservarán los resultados y curvas guardados para poder compararlos. Se perderán los cambios de campos y el nombre del borrador que aún no hayas guardado.</p>
            <div className="flex flex-wrap justify-end gap-2">
              <Button onClick={() => setPendingMedium(null)} size="sm" tone="ghost" type="button">Seguir editando</Button>
              <Button onClick={() => { selectMedium(pendingMedium); setPendingMedium(null) }} size="sm" tone="warning" type="button">Cambiar y descartar borrador</Button>
            </div>
          </div>
        </Dialog>
      ) : null}
    </div>
  )
}
