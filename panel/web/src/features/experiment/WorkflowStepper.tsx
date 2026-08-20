import { AlertTriangle, Check, Circle, Dot } from 'lucide-react'

export type WorkflowStepId = 'configure' | 'validate' | 'execute' | 'analyse' | 'save'
export type WorkflowStepState = 'complete' | 'current' | 'pending' | 'attention'

export function WorkflowStepper({
  states,
  onSelect,
}: {
  states: { [step in WorkflowStepId]: WorkflowStepState }
  onSelect: (step: WorkflowStepId) => void
}) {
  const steps: Array<{ id: WorkflowStepId; label: string }> = [
    { id: 'configure', label: 'Configurar' },
    { id: 'validate', label: 'Validar' },
    { id: 'execute', label: 'Ejecutar' },
    { id: 'analyse', label: 'Analizar' },
    { id: 'save', label: 'Guardar' },
  ]

  return (
    <ol aria-label="Flujo del experimento" className="flex min-w-max items-center gap-0.5">
      {steps.map((step, index) => {
        const state = states[step.id]
        const Icon = state === 'complete' ? Check : state === 'attention' ? AlertTriangle : state === 'current' ? Dot : Circle
        return (
          <li className="flex items-center" key={step.id}>
            {index > 0 ? (
              <span
                aria-hidden="true"
                className={`h-px w-4 sm:w-8 ${states[steps[index - 1].id] === 'complete' ? 'bg-success/40' : 'bg-border'}`}
              />
            ) : null}
            <button
              aria-current={state === 'current' ? 'step' : undefined}
              className={`flex items-center gap-2 rounded-control border px-2.5 py-2 text-sm font-medium transition-colors ${stepTone(state)}`}
              onClick={() => onSelect(step.id)}
              type="button"
            >
              <span className="flex h-4 w-4 shrink-0 items-center justify-center">
                <Icon aria-hidden="true" size={state === 'current' ? 18 : 14} />
              </span>
              <span>{step.label}</span>
            </button>
          </li>
        )
      })}
    </ol>
  )
}

function stepTone(state: WorkflowStepState): string {
  if (state === 'complete') return 'border-transparent text-success hover:border-success/30 hover:bg-success/10'
  if (state === 'current') return 'border-cyan/40 bg-cyan/10 text-cyan'
  if (state === 'attention') return 'border-warning/40 bg-warning/5 text-warning hover:bg-warning/10'
  return 'border-transparent text-slate-500 hover:bg-white/5 hover:text-slate-300'
}
