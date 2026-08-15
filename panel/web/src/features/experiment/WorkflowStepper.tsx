import { Check, Circle, Dot } from 'lucide-react'

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
        const Icon = state === 'complete' ? Check : state === 'current' ? Dot : Circle
        return (
          <li className="flex items-center" key={step.id}>
            {index > 0 ? <span aria-hidden="true" className="h-px w-4 bg-border sm:w-8" /> : null}
            <button
              aria-current={state === 'current' ? 'step' : undefined}
              className={`flex items-center gap-2 rounded-control px-2.5 py-2 text-sm transition-colors ${stepTone(state)}`}
              onClick={() => onSelect(step.id)}
              type="button"
            >
              <Icon aria-hidden="true" size={14} />
              <span>{step.label}</span>
            </button>
          </li>
        )
      })}
    </ol>
  )
}

function stepTone(state: WorkflowStepState): string {
  if (state === 'complete') return 'text-success hover:bg-success/10'
  if (state === 'current') return 'bg-cyan/10 text-cyan'
  if (state === 'attention') return 'text-warning hover:bg-warning/10'
  return 'text-slate-500 hover:bg-white/5 hover:text-slate-300'
}
