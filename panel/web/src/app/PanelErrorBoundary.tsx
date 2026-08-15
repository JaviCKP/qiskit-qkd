import { Component, type ErrorInfo, type ReactNode } from 'react'

type ErrorBoundaryState = { error: Error | null }

export class PanelErrorBoundary extends Component<
  { children: ReactNode },
  ErrorBoundaryState
> {
  state: ErrorBoundaryState = { error: null }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('QKD panel render failure', error, info.componentStack)
  }

  render(): ReactNode {
    if (!this.state.error) {
      return this.props.children
    }
    return (
      <main className="flex min-h-screen items-center justify-center bg-background p-6 text-slate-100">
        <section className="w-full max-w-xl rounded-panel border border-danger/50 bg-surface p-6">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-danger">
            Error de interfaz
          </p>
          <h1 className="mt-2 text-xl font-semibold">No se pudo mostrar el panel</h1>
          <p className="mt-3 text-sm text-slate-300">
            Recarga la aplicación. Si el problema continúa, revisa la consola y el estado de la API.
          </p>
          <pre className="mt-4 max-h-40 overflow-auto rounded-control border border-border bg-background p-3 text-xs text-slate-400">
            {this.state.error.message}
          </pre>
          <button
            className="mt-4 rounded-control border border-cyan px-4 py-2 text-sm font-medium text-cyan hover:bg-cyan/10"
            onClick={() => window.location.reload()}
            type="button"
          >
            Recargar panel
          </button>
        </section>
      </main>
    )
  }
}
