import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { Activity, FlaskConical, Gauge, Library, RadioTower } from 'lucide-react'

import { fetchHealthStatus } from './api/health'

const queryClient = new QueryClient()

function PanelShell() {
  const health = useQuery({
    queryKey: ['health'],
    queryFn: fetchHealthStatus,
    retry: false,
  })

  const statusText =
    health.data?.status === 'ok' ? 'API ok' : health.isError ? 'API error' : 'Conectando'

  return (
    <main className="min-h-screen bg-background text-slate-100">
      <div className="grid min-h-screen grid-cols-[240px_1fr]">
        <aside className="border-r border-border bg-surface px-5 py-6">
          <div className="mb-8 flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded bg-cyan/10 text-cyan">
              <RadioTower size={22} aria-hidden="true" />
            </div>
            <div>
              <p className="text-sm font-semibold text-white">QKD Panel</p>
              <p className="font-mono text-xs text-slate-400">laboratorio local</p>
            </div>
          </div>
          <nav className="space-y-1 text-sm text-slate-300">
            {[
              ['Biblioteca', Library],
              ['Diseñador', FlaskConical],
              ['Caracterización', Activity],
              ['Curvas', Gauge],
            ].map(([label, Icon]) => (
              <div
                className="flex items-center gap-3 rounded px-3 py-2 hover:bg-white/5"
                key={label as string}
              >
                <Icon size={16} aria-hidden="true" />
                <span>{label as string}</span>
              </div>
            ))}
          </nav>
        </aside>
        <section className="px-8 py-6">
          <header className="mb-6 flex items-center justify-between border-b border-border pb-5">
            <div>
              <h1 className="text-2xl font-semibold tracking-normal text-white">
                Banco de simulación QKD
              </h1>
              <p className="mt-1 text-sm text-slate-400">
                Panel React + FastAPI conectado a la librería qiskit-qkd.
              </p>
            </div>
            <div className="rounded border border-border bg-surface px-4 py-3 text-right">
              <p className="text-sm font-medium text-cyan">{statusText}</p>
              <p className="font-mono text-xs text-slate-400">
                {health.data?.service ?? '/api/health'}
              </p>
            </div>
          </header>
          <div className="grid grid-cols-3 gap-4">
            {[
              ['Escenario', 'BB84 decoy sobre fibra metropolitana'],
              ['Estado', 'Preparado para catalogar parámetros'],
              ['Servidor', health.isError ? 'Sin respuesta' : 'FastAPI local'],
            ].map(([label, value]) => (
              <article className="rounded border border-border bg-surface p-4" key={label}>
                <p className="text-xs uppercase text-slate-500">{label}</p>
                <p className="mt-3 text-lg font-medium text-white">{value}</p>
              </article>
            ))}
          </div>
        </section>
      </div>
    </main>
  )
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <PanelShell />
    </QueryClientProvider>
  )
}

export default App
