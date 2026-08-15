import type { ChangeEvent } from 'react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Copy, Download, FlaskConical, Pencil, Search, Trash2, Upload } from 'lucide-react'

import {
  createExperiment,
  deleteExperiment,
  type BuiltinPreset,
  type ExperimentSummary,
  type JsonObject,
  exportExperiment,
  getExperiment,
  importExperiment,
  listExperiments,
  listPresets,
  updateExperiment,
} from '@/api/client'
import { queryClient } from '@/app/queryClient'
import { ApiErrorSummary, Button, Dialog, EmptyState, LoadingBlock } from '@/components/ui'
import { useDesignerStore } from '@/features/designer/scenarioStore'
import { inferMediumFromScenario, mediumDefinitions, type MediumId } from '@/features/lab/mediums'
import { isRecord } from '@/features/shared/scenarioPaths'
import { downloadJson, safeFileName } from '@/lib/download'

const PAGE_SIZE = 50

type LibraryItem =
  | { kind: 'user'; experiment: ExperimentSummary }
  | { kind: 'preset'; preset: BuiltinPreset }

type SortId = 'updated_desc' | 'updated_asc' | 'name_asc' | 'name_desc'

export function LibraryView({ onOpenExperiment }: { onOpenExperiment: () => void }) {
  const [search, setSearch] = useState('')
  const [protocol, setProtocol] = useState('all')
  const [medium, setMedium] = useState<'all' | MediumId>('all')
  const [date, setDate] = useState('all')
  const [sort, setSort] = useState<SortId>('updated_desc')
  const [page, setPage] = useState(0)
  const [deleteTarget, setDeleteTarget] = useState<ExperimentSummary | null>(null)
  const [renameTarget, setRenameTarget] = useState<ExperimentSummary | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const [importError, setImportError] = useState<Error | null>(null)
  const [openError, setOpenError] = useState<Error | null>(null)
  const [openingId, setOpeningId] = useState<string | null>(null)
  const openController = useRef<AbortController | null>(null)
  const loadScenario = useDesignerStore((state) => state.loadScenario)
  const loadExperiment = useDesignerStore((state) => state.loadExperiment)
  const setExperimentName = useDesignerStore((state) => state.setExperimentName)

  const experiments = useQuery({
    queryKey: ['experiments', page],
    queryFn: ({ signal }) => listExperiments(signal, { limit: PAGE_SIZE, offset: page * PAGE_SIZE }),
    retry: false,
  })
  const presets = useQuery({
    queryKey: ['presets'],
    queryFn: ({ signal }) => listPresets(signal),
    retry: false,
    staleTime: Number.POSITIVE_INFINITY,
  })
  const duplicate = useMutation({
    mutationFn: async (item: LibraryItem) => {
      const detail = item.kind === 'user' ? (await getExperiment(item.experiment.id)).experiment : null
      const name = item.kind === 'user' ? item.experiment.name : item.preset.name
      const scenario = detail?.scenario ?? (item.kind === 'preset' ? item.preset.scenario : undefined)
      if (!scenario) throw new Error('No se pudo cargar el escenario del experimento.')
      return createExperiment({
        name: `${name} copia`,
        scenario,
        tags: detail?.tags ?? ['preset'],
        schema_version: 2,
        last_result: detail?.last_result ?? null,
        curve_recipes: detail?.curve_recipes ?? [],
        runs: detail?.runs ?? [],
        curves: detail?.curves ?? [],
        provenance: { duplicated_from: item.kind === 'user' ? item.experiment.id : item.preset.digest },
      })
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['experiments'] }),
  })
  const remove = useMutation({
    mutationFn: (experimentId: string) => deleteExperiment(experimentId),
    onSuccess: () => {
      setDeleteTarget(null)
      void queryClient.invalidateQueries({ queryKey: ['experiments'] })
    },
  })
  const rename = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) => updateExperiment(id, { name }),
    onSuccess: () => {
      setRenameTarget(null)
      void queryClient.invalidateQueries({ queryKey: ['experiments'] })
    },
  })
  const importer = useMutation({
    mutationFn: (payload: JsonObject) => importExperiment(payload),
    onSuccess: () => {
      setImportError(null)
      setPage(0)
      void queryClient.invalidateQueries({ queryKey: ['experiments'] })
    },
  })

  useEffect(() => () => openController.current?.abort(), [])

  const items = useMemo(() => {
    const all: LibraryItem[] = [
      ...(experiments.data?.experiments ?? []).map((experiment): LibraryItem => ({ kind: 'user', experiment })),
      ...(presets.data?.presets ?? []).map((preset): LibraryItem => ({ kind: 'preset', preset })),
    ]
    return all.filter((item) => itemMatches(item, { search, protocol, medium, date })).sort((a, b) => compareItems(a, b, sort))
  }, [date, experiments.data?.experiments, medium, presets.data?.presets, protocol, search, sort])

  const openItem = async (item: LibraryItem) => {
    if (item.kind === 'preset') {
      loadScenario(item.preset.scenario)
      setExperimentName(item.preset.name)
      onOpenExperiment()
      return
    }
    openController.current?.abort()
    const controller = new AbortController()
    openController.current = controller
    setOpeningId(item.experiment.id)
    setOpenError(null)
    try {
      const detail = item.experiment.__detail
        ? { experiment: item.experiment.__detail }
        : await getExperiment(item.experiment.id, controller.signal)
      loadExperiment(detail.experiment)
      onOpenExperiment()
    } catch (error) {
      if (!isAbortError(error)) setOpenError(error instanceof Error ? error : new Error('No se pudo abrir el experimento.'))
    } finally {
      if (openController.current === controller) {
        openController.current = null
        setOpeningId(null)
      }
    }
  }

  return (
    <div className="min-w-0 space-y-5 p-4 sm:p-6">
      <header className="flex flex-col gap-4 border-b border-border pb-5 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-cyan">Paso 5</p>
          <h1 className="mt-1 text-xl font-semibold text-white">Biblioteca de experimentos</h1>
          <p className="mt-1 text-sm text-slate-400">La lista usa summaries ligeros; el escenario completo se carga al abrir.</p>
        </div>
        <label className="inline-flex h-10 cursor-pointer items-center justify-center gap-2 rounded-control border border-border bg-raised px-3 text-sm text-slate-200 hover:border-cyan hover:text-cyan">
          <Upload aria-hidden="true" size={15} /> Importar experimento
          <input accept="application/json,.qkd.json" className="sr-only" onChange={(event) => void importFromFile(event, importer.mutate, setImportError)} type="file" />
        </label>
      </header>

      <section aria-label="Filtros de biblioteca" className="grid gap-3 rounded-panel border border-border bg-surface p-3 md:grid-cols-2 xl:grid-cols-[minmax(220px,1fr)_160px_180px_150px_190px]">
        <label className="relative block"><Search aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" size={15} /><span className="sr-only">Buscar experimento</span><input className="h-9 w-full rounded-control border border-border bg-background pl-9 pr-3 text-sm text-white focus:border-cyan" onChange={(event) => setSearch(event.target.value)} placeholder="Buscar nombre, digest o tag" value={search} /></label>
        <FilterSelect label="Protocolo" onChange={setProtocol} options={[['all', 'Todos'], ['bb84', 'BB84'], ['e91', 'E91']]} value={protocol} />
        <FilterSelect label="Medio" onChange={(value) => setMedium(value as 'all' | MediumId)} options={[['all', 'Todos los medios'], ...Object.entries(mediumDefinitions).map(([id, definition]) => [id, definition.shortLabel])]} value={medium} />
        <FilterSelect label="Fecha" onChange={setDate} options={[['all', 'Cualquier fecha'], ['7', 'Ultimos 7 dias'], ['30', 'Ultimos 30 dias']]} value={date} />
        <FilterSelect label="Orden" onChange={(value) => setSort(value as SortId)} options={[['updated_desc', 'Mas recientes'], ['updated_asc', 'Mas antiguos'], ['name_asc', 'Nombre A-Z'], ['name_desc', 'Nombre Z-A']]} value={sort} />
      </section>

      {importError ? <ApiErrorSummary error={importError} recoveryHint="Elige un archivo JSON completo exportado por QKD Workbench y vuelve a intentarlo." /> : null}
      {openError ? <ApiErrorSummary error={openError} recoveryHint="Comprueba que la API siga activa y vuelve a abrir el experimento." /> : null}
      {importer.error ? <ApiErrorSummary error={importer.error} /> : null}
      {duplicate.error ? <ApiErrorSummary error={duplicate.error} /> : null}
      {remove.error ? <ApiErrorSummary error={remove.error} /> : null}
      {rename.error ? <ApiErrorSummary error={rename.error} /> : null}
      {experiments.error ? <ApiErrorSummary error={experiments.error} recoveryHint="Comprueba que la API este activa y vuelve a cargar los experimentos." /> : null}
      {presets.error ? <ApiErrorSummary error={presets.error} recoveryHint="Comprueba que la API este activa y vuelve a cargar las plantillas." /> : null}
      {experiments.isError || presets.isError ? <Button onClick={() => { void experiments.refetch(); void presets.refetch() }} tone="neutral" type="button">Reintentar carga</Button> : null}
      {experiments.isLoading || presets.isLoading ? <LoadingBlock label="Cargando biblioteca" /> : null}

      {items.length ? (
        <section aria-label="Resultados de biblioteca" className="overflow-hidden rounded-panel border border-border bg-surface">
          <div className="hidden grid-cols-[minmax(260px,1fr)_100px_110px_100px_150px_290px] gap-3 border-b border-border bg-raised px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500 xl:grid"><span>Experimento</span><span>Origen</span><span>Protocolo</span><span>Medio</span><span>Contenido</span><span>Acciones</span></div>
          <div className="divide-y divide-border">
            {items.map((item) => <LibraryRow disabled={openingId !== null || duplicate.isPending} item={item} key={itemKey(item)} onDelete={setDeleteTarget} onDuplicate={(value) => duplicate.mutate(value)} onOpen={(value) => void openItem(value)} onRename={(experiment) => { setRenameTarget(experiment); setRenameValue(experiment.name) }} />)}
          </div>
        </section>
      ) : !experiments.isLoading && !presets.isLoading && !experiments.isError && !presets.isError ? <EmptyState description="Prueba a quitar filtros o importa un experimento JSON exportado por el panel." title="No hay experimentos que coincidan" /> : null}

      {experiments.data?.pagination ? <nav aria-label="Paginacion de experimentos" className="flex items-center justify-between gap-3 text-xs text-slate-400"><span>Pagina {page + 1} · {experiments.data.pagination.total} summaries</span><div className="flex gap-2"><Button disabled={page === 0 || experiments.isFetching} onClick={() => setPage((value) => Math.max(0, value - 1))} size="sm" tone="neutral" type="button">Anterior</Button><Button disabled={!experiments.data.pagination.has_more || experiments.isFetching} onClick={() => setPage((value) => value + 1)} size="sm" tone="neutral" type="button">Siguiente</Button></div></nav> : null}

      <Dialog
        className="max-w-md"
        description={deleteTarget ? `Se eliminaran ${countLabel(deleteTarget.runs_count, 'ejecucion', 'ejecuciones')} y ${countLabel(deleteTarget.curves_count, 'curva', 'curvas')} junto al experimento.` : undefined}
        onClose={() => setDeleteTarget(null)}
        open={deleteTarget !== null}
        title={deleteTarget ? `Eliminar ${deleteTarget.name}` : 'Eliminar experimento'}
      >
        <div className="flex justify-end gap-2">
          <Button onClick={() => setDeleteTarget(null)} tone="ghost" type="button">Cancelar</Button>
          <Button disabled={remove.isPending || !deleteTarget} onClick={() => deleteTarget && remove.mutate(deleteTarget.id)} tone="danger" type="button"><Trash2 aria-hidden="true" size={15} /> Eliminar definitivamente</Button>
        </div>
      </Dialog>
      <Dialog className="max-w-md" onClose={() => setRenameTarget(null)} open={renameTarget !== null} title="Renombrar experimento">
        <label className="block"><span className="text-xs text-slate-500">Nuevo nombre</span><input autoFocus className="mt-1 h-10 w-full rounded-control border border-border bg-background px-3 text-sm text-white focus:border-cyan" maxLength={200} onChange={(event) => setRenameValue(event.target.value)} value={renameValue} /></label>
        <div className="mt-5 flex justify-end gap-2"><Button onClick={() => setRenameTarget(null)} tone="ghost" type="button">Cancelar</Button><Button disabled={!renameValue.trim() || rename.isPending || !renameTarget} onClick={() => renameTarget && rename.mutate({ id: renameTarget.id, name: renameValue.trim() })} tone="primary" type="button">Guardar nombre</Button></div>
      </Dialog>
    </div>
  )
}

function LibraryRow({ item, disabled, onOpen, onDuplicate, onRename, onDelete }: { item: LibraryItem; disabled: boolean; onOpen: (item: LibraryItem) => void; onDuplicate: (item: LibraryItem) => void; onRename: (experiment: ExperimentSummary) => void; onDelete: (experiment: ExperimentSummary) => void }) {
  const source = item.kind === 'user' ? item.experiment : item.preset
  const scenario = item.kind === 'preset' ? item.preset.scenario : null
  const protocol = item.kind === 'user' ? summaryProtocol(item.experiment) : scenario?.protocol.name ?? '—'
  const mediumId = item.kind === 'user' ? summaryMedium(item.experiment) : scenario ? inferMediumFromScenario(scenario) : 'custom'
  const medium = mediumDefinitions[mediumId]?.shortLabel ?? mediumId
  const experiment = item.kind === 'user' ? item.experiment : null
  const content = experiment ? `${countLabel(experiment.runs_count, 'ejecucion', 'ejecuciones')} · ${countLabel(experiment.curves_count, 'curva', 'curvas')}` : 'Escenario base'
  return <article className="grid gap-3 px-4 py-4 hover:bg-white/[0.02] xl:grid-cols-[minmax(260px,1fr)_100px_110px_100px_150px_290px] xl:items-center"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><h2 className="truncate text-sm font-semibold text-white" title={source.name}>{source.name}</h2></div><p className="mt-1 font-mono text-[11px] text-slate-500">{source.digest.slice(0, 16)}</p><p className="mt-1 text-[11px] text-slate-600">{item.kind === 'user' ? `Actualizado ${formatDate(item.experiment.updated_at)}` : 'Preset integrado · solo lectura'}</p></div><div><span className={`rounded-control border px-2 py-1 text-[11px] ${item.kind === 'preset' ? 'border-cyan/40 text-cyan' : 'border-border text-slate-300'}`}>{item.kind === 'preset' ? 'Integrado' : 'Usuario'}</span></div><p className="text-xs uppercase text-slate-300">{protocol}</p><p className="text-xs text-slate-300">{medium}</p><p className="text-xs text-slate-400">{content}</p><div className="flex flex-wrap gap-1.5"><Button disabled={disabled} onClick={() => onOpen(item)} size="sm" tone="primary" type="button"><FlaskConical aria-hidden="true" size={13} /> {disabled ? 'Cargando...' : 'Abrir'}</Button><Button disabled={disabled} onClick={() => onDuplicate(item)} size="sm" tone="neutral" type="button"><Copy aria-hidden="true" size={13} /> Duplicar</Button><Button disabled={disabled} onClick={() => void exportItem(item)} size="sm" tone="ghost" type="button"><Download aria-hidden="true" size={13} /><span className="sr-only">Exportar {source.name}</span></Button>{experiment ? <Button disabled={disabled} onClick={() => onRename(experiment)} size="sm" tone="ghost" type="button"><Pencil aria-hidden="true" size={13} /><span className="sr-only">Renombrar {source.name}</span></Button> : null}{experiment ? <Button disabled={disabled} onClick={() => onDelete(experiment)} size="sm" tone="ghost" type="button"><Trash2 aria-hidden="true" size={13} /><span className="sr-only">Eliminar {source.name}</span></Button> : null}</div></article>
}

function FilterSelect({ label, value, options, onChange }: { label: string; value: string; options: string[][]; onChange: (value: string) => void }) {
  return <label className="block"><span className="sr-only">{label}</span><select aria-label={label} className="h-9 w-full rounded-control border border-border bg-background px-2 text-xs text-white focus:border-cyan" onChange={(event) => onChange(event.target.value)} value={value}>{options.map(([optionValue, optionLabel]) => <option key={optionValue} value={optionValue}>{optionLabel}</option>)}</select></label>
}

function countLabel(count: number, singular: string, plural: string): string {
  return `${count} ${count === 1 ? singular : plural}`
}

async function exportItem(item: LibraryItem): Promise<void> {
  if (item.kind === 'preset') {
    downloadJson(`${safeFileName(item.preset.name)}.qkd.json`, { schema_version: 2, origin: 'builtin', name: item.preset.name, digest: item.preset.digest, scenario: item.preset.scenario, tags: ['preset'], runs: [], curves: [], curve_recipes: [], provenance: { builtin: true } })
    return
  }
  const payload = await exportExperiment(item.experiment.id)
  downloadJson(`${safeFileName(item.experiment.name)}.qkd.json`, payload.experiment)
}

async function importFromFile(event: ChangeEvent<HTMLInputElement>, onImport: (payload: JsonObject) => void, setError: (error: Error | null) => void): Promise<void> {
  const file = event.target.files?.[0]
  if (!file) return
  try {
    const parsed: unknown = JSON.parse(await file.text())
    if (!isRecord(parsed)) throw new Error('El archivo debe contener un objeto JSON de experimento.')
    const candidate = isRecord(parsed.experiment) ? parsed.experiment : parsed
    if (!isRecord(candidate.scenario)) throw new Error('Falta experiment.scenario o no es un objeto valido.')
    if (typeof candidate.name !== 'string' || typeof candidate.digest !== 'string') throw new Error('El experimento necesita name y digest.')
    if (candidate.schema_version !== undefined && (typeof candidate.schema_version !== 'number' || candidate.schema_version > 2)) throw new Error(`schema_version no compatible: ${String(candidate.schema_version)}`)
    setError(null)
    onImport(candidate)
  } catch (error) {
    setError(error instanceof SyntaxError ? new Error(`JSON inválido: ${error.message}`) : error instanceof Error ? error : new Error('No se pudo leer el experimento.'))
  } finally {
    event.target.value = ''
  }
}

function itemMatches(item: LibraryItem, filters: { search: string; protocol: string; medium: 'all' | MediumId; date: string }): boolean {
  if (item.kind === 'user') {
    const source = item.experiment
    const query = filters.search.trim().toLocaleLowerCase('es')
    if (query && !`${source.name} ${source.digest} ${source.tags.join(' ')}`.toLocaleLowerCase('es').includes(query)) return false
    if (filters.protocol !== 'all' && summaryProtocol(source) !== filters.protocol) return false
    if (filters.medium !== 'all' && summaryMedium(source) !== filters.medium) return false
    if (filters.date !== 'all' && new Date(source.updated_at).getTime() < Date.now() - Number(filters.date) * 86_400_000) return false
    return true
  }
  const source = item.preset
  const query = filters.search.trim().toLocaleLowerCase('es')
  const tags = ['preset', source.scenario.protocol.name, inferMediumFromScenario(source.scenario)]
  if (query && !`${source.name} ${source.digest} ${tags.join(' ')}`.toLocaleLowerCase('es').includes(query)) return false
  if (filters.protocol !== 'all' && source.scenario.protocol.name !== filters.protocol) return false
  if (filters.medium !== 'all' && inferMediumFromScenario(source.scenario) !== filters.medium) return false
  return true
}

function compareItems(a: LibraryItem, b: LibraryItem, sort: SortId): number {
  const sourceA = a.kind === 'user' ? a.experiment : a.preset
  const sourceB = b.kind === 'user' ? b.experiment : b.preset
  if (sort === 'name_asc' || sort === 'name_desc') {
    const compared = sourceA.name.localeCompare(sourceB.name, 'es')
    return sort === 'name_asc' ? compared : -compared
  }
  const dateA = a.kind === 'user' ? new Date(a.experiment.updated_at).getTime() : 0
  const dateB = b.kind === 'user' ? new Date(b.experiment.updated_at).getTime() : 0
  return sort === 'updated_desc' ? dateB - dateA : dateA - dateB
}

function itemKey(item: LibraryItem): string {
  return item.kind === 'user' ? `user:${item.experiment.id}` : `preset:${item.preset.digest}`
}

function summaryProtocol(summary: ExperimentSummary): string {
  return summary.tags.find((tag) => tag === 'bb84' || tag === 'e91') ?? ''
}

function summaryMedium(summary: ExperimentSummary): MediumId {
  const candidate = summary.tags.find((tag): tag is MediumId => tag in mediumDefinitions)
  return candidate ?? 'custom'
}

function formatDate(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('es-ES', { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}
