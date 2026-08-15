import { useCallback, useEffect, useId, useRef, type ButtonHTMLAttributes, type ReactNode } from 'react'
import { AlertTriangle, CircleHelp, Inbox } from 'lucide-react'

import {
  ApiError,
  type ApiValidationIssue,
  type JsonObject,
  type ResultAssessment,
} from '@/api/client'
import { resultPresentation, type ResultStatusTone } from '@/features/results/resultSemantics'

export function StatusPill({
  label,
  detail,
  tone = 'cyan',
}: {
  label: string
  detail: string
  tone?: 'cyan' | 'success' | 'danger' | 'warning'
}) {
  const toneClass = {
    cyan: 'text-cyan',
    success: 'text-success',
    warning: 'text-warning',
    danger: 'text-danger',
  }[tone]
  return (
    <div className="rounded-control border border-border bg-surface px-3 py-2 text-right">
      <p className={`text-xs font-semibold ${toneClass}`}>{label}</p>
      <p className="mt-0.5 max-w-48 truncate font-mono text-[11px] text-slate-500" title={detail}>
        {detail}
      </p>
    </div>
  )
}

export function ValidationSummary({ issues }: { issues: ApiValidationIssue[] }) {
  const hasErrors = issues.some((issue) => issue.severity !== 'warning')
  return (
    <section
      aria-live="polite"
      className={`rounded-panel border px-4 py-3 ${
        hasErrors ? 'border-danger/50 bg-danger/5' : 'border-warning/50 bg-warning/5'
      }`}
    >
      <p className={`text-sm font-medium ${hasErrors ? 'text-danger' : 'text-warning'}`}>
        {hasErrors ? 'Validación pendiente' : 'Advertencias de aplicabilidad'}
      </p>
      <IssueList issues={issues} />
    </section>
  )
}

export function ApiErrorSummary({
  error,
  recoveryHint = 'Revisa la conexión con la API y valida el escenario antes de reintentar.',
}: {
  error: Error
  recoveryHint?: string
}) {
  const issues = error instanceof ApiError ? error.issues : []
  return (
    <section aria-live="assertive" className="mt-3 rounded-panel border border-danger/50 bg-danger/5 px-3 py-2">
      <p className="text-sm text-danger">{error.message}</p>
      {issues.length > 0 ? (
        <IssueList issues={issues} />
      ) : (
        <p className="mt-1 text-xs text-slate-400">{recoveryHint}</p>
      )}
    </section>
  )
}

function IssueList({ issues }: { issues: ApiValidationIssue[] }) {
  return (
    <ul className="mt-2 space-y-2">
      {issues.slice(0, 8).map((issue) => (
        <li
          className="rounded-control border border-border bg-background px-2 py-1 text-xs text-slate-200"
          key={`${issue.code ?? 'issue'}-${issue.loc}-${issue.msg}`}
        >
          <p>
            <span className="font-mono text-slate-500">{issue.loc}</span>: {localizeIssueMessage(issue.msg)}
          </p>
          {issue.suggestion ? <p className="mt-1 text-cyan">Sugerencia: {localizeSuggestion(issue.suggestion)}</p> : null}
        </li>
      ))}
    </ul>
  )
}

function localizeIssueMessage(message: string): string {
  const greaterOrEqual = message.match(/^(?:[\w.]+ )?must be greater than or equal to (.+)$/i)
  if (greaterOrEqual) return `El valor debe ser mayor o igual que ${greaterOrEqual[1]}.`
  const greaterThan = message.match(/^(?:[\w.]+ )?must be greater than (.+)$/i)
  if (greaterThan) return `El valor debe ser mayor que ${greaterThan[1]}.`
  const lessThan = message.match(/^(?:[\w.]+ )?must be less than (.+)$/i)
  if (lessThan) return `El valor debe ser menor que ${lessThan[1]}.`
  if (/^field required$/i.test(message)) return 'Este valor es obligatorio.'
  return message
}

function localizeSuggestion(suggestion: string): string {
  return suggestion.replace(
    /^Use one of the supported channel kinds:/i,
    'Usa uno de los modelos de canal compatibles:',
  )
}

export function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <article className="border-l border-border px-3 py-1 first:border-l-0">
      <p className="text-[11px] uppercase tracking-[0.08em] text-slate-500">{label}</p>
      <p className="mt-1 font-mono text-base tabular-nums text-white">{value}</p>
    </article>
  )
}

export function StatusBadge({
  summary = {},
  metrics,
  assessment,
}: {
  summary?: JsonObject
  metrics?: JsonObject
  assessment?: ResultAssessment | null
}) {
  const normalizedSummary: JsonObject = {
    ...summary,
    ...(metrics ? { metrics } : {}),
    ...(assessment !== undefined ? { assessment: assessment as unknown as JsonObject } : {}),
  }
  const presentation = resultPresentation(normalizedSummary)
  const toneClasses: { [tone in ResultStatusTone]: string } = {
    cyan: 'border-cyan/70 text-cyan',
    danger: 'border-danger/70 text-danger',
    warning: 'border-warning/70 text-warning',
    neutral: 'border-border text-slate-300',
  }

  return (
    <span className={`rounded-control border px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.08em] ${toneClasses[presentation.tone]}`}>
      {presentation.label}
    </span>
  )
}

export function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre className="max-h-96 overflow-auto rounded-control border border-border bg-background p-3 text-xs text-slate-300">
      {JSON.stringify(value, null, 2)}
    </pre>
  )
}

export function InfoTip({ label, text }: { label: string; text: string }) {
  return (
    <span className="group relative inline-flex shrink-0 align-middle">
      <button
        aria-label={`Información sobre ${label}`}
        className="flex h-5 w-5 items-center justify-center rounded-full text-slate-500 transition-colors hover:bg-white/5 hover:text-cyan focus:bg-white/5 focus:text-cyan focus:outline-none"
        title={text}
        onClick={(event) => { event.preventDefault(); event.stopPropagation() }}
        type="button"
      >
        <CircleHelp aria-hidden="true" size={14} />
      </button>
      <span
        className="pointer-events-none absolute right-0 top-6 z-50 hidden w-64 rounded-lg border border-slate-600 bg-slate-950 px-3 py-2 text-left text-[11px] font-normal leading-5 text-slate-200 shadow-2xl group-hover:block group-focus-within:block"
        role="tooltip"
      >
        {text}
      </span>
    </span>
  )
}

export function Button({
  children,
  className = '',
  tone = 'neutral',
  size = 'md',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  children: ReactNode
  tone?: 'primary' | 'neutral' | 'success' | 'warning' | 'danger' | 'ghost'
  size?: 'sm' | 'md'
}) {
  const tones = {
    primary: 'border-cyan bg-cyan text-background hover:bg-cyan/90',
    neutral: 'border-border bg-raised text-slate-200 hover:border-slate-400 hover:text-white',
    success: 'border-success/70 text-success hover:bg-success/10',
    warning: 'border-warning/70 text-warning hover:bg-warning/10',
    danger: 'border-danger/70 text-danger hover:bg-danger/10',
    ghost: 'border-transparent text-slate-300 hover:bg-white/5 hover:text-white',
  }
  const sizes = size === 'sm' ? 'h-8 px-2.5 text-xs' : 'h-10 px-3.5 text-sm'
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 rounded-control border font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${tones[tone]} ${sizes} ${className}`}
      {...props}
    >
      {children}
    </button>
  )
}

export function Panel({
  children,
  className = '',
  as: Element = 'section',
}: {
  children: ReactNode
  className?: string
  as?: 'section' | 'article' | 'div'
}) {
  return (
    <Element className={`rounded-panel border border-border bg-surface ${className}`}>
      {children}
    </Element>
  )
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string
  description: string
  action?: ReactNode
}) {
  return (
    <div className="flex min-h-44 flex-col items-center justify-center rounded-panel border border-dashed border-border bg-background/40 px-5 py-8 text-center">
      <Inbox aria-hidden="true" className="text-slate-600" size={24} />
      <p className="mt-3 text-sm font-medium text-slate-200">{title}</p>
      <p className="mt-1 max-w-lg text-sm text-slate-500">{description}</p>
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  )
}

export function LoadingBlock({ label = 'Cargando' }: { label?: string }) {
  return (
    <div aria-label={label} aria-live="polite" className="space-y-3 rounded-panel border border-border bg-surface p-4">
      <div className="h-3 w-28 animate-pulse rounded bg-raised" />
      <div className="h-8 animate-pulse rounded bg-raised" />
      <div className="h-8 w-3/4 animate-pulse rounded bg-raised" />
    </div>
  )
}

export function ConfirmPanel({
  title,
  description,
  confirmLabel,
  onConfirm,
  onCancel,
  pending = false,
}: {
  title: string
  description: string
  confirmLabel: string
  onConfirm: () => void
  onCancel: () => void
  pending?: boolean
}) {
  return (
    <div className="mt-3 flex flex-col gap-3 rounded-panel border border-warning/50 bg-warning/5 p-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex gap-3">
        <AlertTriangle aria-hidden="true" className="mt-0.5 shrink-0 text-warning" size={18} />
        <div>
          <p className="text-sm font-medium text-white">{title}</p>
          <p className="mt-1 text-xs text-slate-400">{description}</p>
        </div>
      </div>
      <div className="flex shrink-0 gap-2">
        <Button disabled={pending} onClick={onCancel} size="sm" tone="ghost" type="button">
          Volver
        </Button>
        <Button disabled={pending} onClick={onConfirm} size="sm" tone="warning" type="button">
          {confirmLabel}
        </Button>
      </div>
    </div>
  )
}

type DialogProps = {
  open: boolean
  title: string
  description?: string
  onClose: () => void
  children: ReactNode
  className?: string
  labelledBy?: string
  closeOnBackdrop?: boolean
}

/**
 * Small, dependency-free modal primitive used by the panel drawers and
 * confirmations. It owns focus while open and puts it back on the trigger
 * when closed, so callers do not have to duplicate keyboard plumbing.
 */
export function Dialog({
  open,
  title,
  description,
  onClose,
  children,
  className = '',
  labelledBy,
  closeOnBackdrop = true,
}: DialogProps) {
  const dialogRef = useRef<HTMLDivElement>(null)
  const overlayRef = useRef<HTMLDivElement>(null)
  const generatedTitleId = useId()
  const titleId = labelledBy ?? generatedTitleId
  const previousFocus = useRef<HTMLElement | null>(null)
  const onCloseRef = useRef(onClose)
  useEffect(() => {
    onCloseRef.current = onClose
  }, [onClose])
  const restoreFocus = useCallback(() => {
    const target = previousFocus.current
    if (target && target.isConnected) target.focus()
  }, [])
  const requestClose = useCallback(() => {
    restoreFocus()
    onCloseRef.current()
  }, [restoreFocus])

  useEffect(() => {
    if (!open) return undefined
    previousFocus.current = document.activeElement as HTMLElement | null
    const dialog = dialogRef.current
    if (!dialog) return undefined
    const focusable = getFocusable(dialog)
    const preferred = dialog.querySelector<HTMLElement>('[data-dialog-autofocus], [autofocus]')
    ;(preferred ?? focusable[0] ?? dialog).focus()

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        requestClose()
        return
      }
      if (event.key !== 'Tab') return
      const elements = getFocusable(dialog)
      if (!elements.length) {
        event.preventDefault()
        dialog.focus()
        return
      }
      const currentIndex = elements.indexOf(document.activeElement as HTMLElement)
      const nextIndex = event.shiftKey
        ? currentIndex <= 0 ? elements.length - 1 : currentIndex - 1
        : currentIndex < 0 || currentIndex === elements.length - 1 ? 0 : currentIndex + 1
      event.preventDefault()
      elements[nextIndex].focus()
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      restoreFocus()
    }
  }, [open, requestClose, restoreFocus])

  useEffect(() => {
    if (!open) return undefined
    const overlay = overlayRef.current
    if (!overlay) return undefined
    const affected = collectBackgroundElements(overlay)
    const previous = affected.map((element) => ({
      element,
      ariaHidden: element.getAttribute('aria-hidden'),
      inert: element.hasAttribute('inert'),
    }))
    affected.forEach((element) => {
      element.setAttribute('aria-hidden', 'true')
      element.setAttribute('inert', '')
    })
    return () => {
      previous.forEach(({ element, ariaHidden, inert }) => {
        if (ariaHidden === null) element.removeAttribute('aria-hidden')
        else element.setAttribute('aria-hidden', ariaHidden)
        if (!inert) element.removeAttribute('inert')
      })
    }
  }, [open])

  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-stretch justify-center p-0 sm:items-center sm:p-4" ref={overlayRef}>
      <button
        aria-hidden="true"
        className="absolute inset-0 h-full w-full cursor-default bg-black/70"
        onClick={closeOnBackdrop ? requestClose : undefined}
        tabIndex={-1}
        type="button"
      />
      <div
        aria-describedby={description ? `${titleId}-description` : undefined}
        aria-labelledby={titleId}
        aria-modal="true"
        className={`relative z-10 flex max-h-[min(90vh,760px)] w-full min-w-0 flex-col overflow-hidden rounded-none border border-border bg-surface shadow-2xl sm:rounded-panel ${className}`}
        ref={dialogRef}
        role="dialog"
        tabIndex={-1}
      >
        <header className="flex shrink-0 items-start justify-between gap-4 border-b border-border px-4 py-4 sm:px-5">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-cyan">Opciones</p>
            <h2 className="mt-1 text-lg font-semibold text-white" id={titleId}>{title}</h2>
            {description ? <p className="mt-1 text-sm leading-5 text-slate-400" id={`${titleId}-description`}>{description}</p> : null}
          </div>
          <button
            aria-label={`Cerrar ${title}`}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-control border border-border text-slate-400 hover:border-slate-500 hover:text-white"
            onClick={requestClose}
            type="button"
          >
            <span aria-hidden="true" className="text-lg leading-none">×</span>
          </button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto p-4 sm:p-5">{children}</div>
      </div>
    </div>
  )
}

export function Drawer({
  open,
  title,
  description,
  onClose,
  children,
  side = 'right',
}: Omit<DialogProps, 'className'> & { side?: 'left' | 'right' }) {
  return (
    <Dialog
      className={`sm:items-stretch sm:rounded-none sm:p-0 ${side === 'left' ? 'sm:mr-auto sm:max-w-xl sm:border-r sm:border-l-0' : 'sm:ml-auto sm:max-w-xl sm:border-l'}`}
      description={description}
      onClose={onClose}
      open={open}
      title={title}
    >
      {children}
    </Dialog>
  )
}

function getFocusable(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>(
    'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
  )).filter((element) => !element.hasAttribute('aria-hidden'))
}

function collectBackgroundElements(overlay: HTMLElement): HTMLElement[] {
  const result: HTMLElement[] = []
  let current: HTMLElement | null = overlay
  while (current?.parentElement && current.parentElement !== document.body) {
    const parent = current.parentElement
    Array.from(parent.children).forEach((child) => {
      if (child !== current && child instanceof HTMLElement && !child.contains(overlay)) result.push(child)
    })
    current = parent
  }
  return result
}
