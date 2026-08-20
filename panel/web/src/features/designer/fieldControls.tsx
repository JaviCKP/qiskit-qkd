import { useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'

import type { CatalogField, JsonObject } from '@/api/client'
import { isRecord } from '@/features/shared/scenarioPaths'
import { formatInputValue, parseInputValue } from '@/lib/format'

export function FieldControl({
  field,
  value,
  id,
  disabled = false,
  onChange,
}: {
  field: CatalogField
  value: unknown
  id: string
  disabled?: boolean
  onChange: (target: string, value: unknown) => void
}) {
  if (field.type === 'boolean') {
    return (
      <input
        checked={Boolean(value)}
        className="mt-2 h-4 w-4 accent-cyan"
        disabled={disabled}
        id={id}
        onChange={(event) => onChange(field.key, event.target.checked)}
        type="checkbox"
      />
    )
  }
  if (field.type === 'select' && field.options?.length) {
    return (
      <select
        className={controlClass}
        disabled={disabled}
        id={id}
        onChange={(event) => onChange(field.key, event.target.value)}
        value={formatInputValue(value)}
      >
        {field.options.map((option) => <option key={option} value={option}>{option}</option>)}
      </select>
    )
  }
  if (field.type === 'table') {
    return <DecoyTable disabled={disabled} id={id} onChange={(next) => onChange(field.key, next)} value={value} />
  }
  if (field.type === 'number_list' || field.type === 'string_list') {
    return (
      <ListInput
        disabled={disabled}
        id={id}
        numeric={field.type === 'number_list'}
        onChange={(next) => onChange(field.key, next)}
        value={value}
      />
    )
  }
  if (field.type === 'json' || field.type === 'schedule_list') {
    return <JsonEditor disabled={disabled} id={id} key={JSON.stringify(value)} onChange={(next) => onChange(field.key, next)} value={value} />
  }
  return (
    <NumberOrTextInput
      disabled={disabled}
      field={field}
      id={id}
      onChange={(next) => onChange(field.key, next)}
      value={value}
    />
  )
}

const controlClass = 'h-9 min-w-0 flex-1 rounded-control border border-border bg-background px-3 text-sm text-white transition-colors hover:border-border-strong focus:border-cyan disabled:cursor-not-allowed disabled:opacity-50'

function NumberOrTextInput({
  field,
  value,
  id,
  disabled,
  onChange,
}: {
  field: CatalogField
  value: unknown
  id: string
  disabled: boolean
  onChange: (value: unknown) => void
}) {
  const isNumber = field.type === 'number' || field.type === 'integer'
  const numericValue = typeof value === 'number' ? value : Number(value)
  const canSlide = isNumber && typeof field.min === 'number' && typeof field.max === 'number' && field.max > field.min && (field.scale !== 'log' || field.min > 0)

  return (
    <div className="min-w-0 flex-1 space-y-2">
      <input
        className={`${controlClass} w-full font-mono tabular-nums`}
        disabled={disabled}
        id={id}
        max={field.max ?? undefined}
        min={field.min ?? undefined}
        onChange={(event) => onChange(parseInputValue(event.target.value, field.type))}
        step={field.step ?? (field.type === 'integer' ? 1 : 'any')}
        type={isNumber ? 'number' : 'text'}
        value={formatInputValue(value)}
      />
      {canSlide ? (
        <input
          aria-label={`${field.label_es}: ajuste deslizante`}
          className="w-full accent-cyan"
          disabled={disabled}
          max={sliderMax(field)}
          min={sliderMin(field)}
          onChange={(event) => onChange(valueFromSlider(Number(event.target.value), field))}
          step={field.scale === 'log' ? 0.01 : (field.step ?? 0.01)}
          type="range"
          value={valueToSlider(numericValue, field)}
        />
      ) : null}
    </div>
  )
}

function ListInput({
  numeric,
  value,
  id,
  disabled,
  onChange,
}: {
  numeric: boolean
  value: unknown
  id: string
  disabled: boolean
  onChange: (value: Array<number | string>) => void
}) {
  const items = Array.isArray(value) ? value : []
  return (
    <input
      className={`${controlClass} font-mono`}
      disabled={disabled}
      id={id}
      onChange={(event) => {
        const parts = event.target.value.split(',').map((part) => part.trim()).filter(Boolean)
        onChange(numeric ? parts.map(Number) : parts)
      }}
      value={items.join(', ')}
    />
  )
}

function JsonEditor({
  value,
  id,
  disabled,
  onChange,
}: {
  value: unknown
  id: string
  disabled: boolean
  onChange: (value: unknown) => void
}) {
  const [text, setText] = useState(() => JSON.stringify(value, null, 2))
  const [error, setError] = useState<string | null>(null)

  return (
    <div className="min-w-0 flex-1">
      <textarea
        className="min-h-28 w-full rounded-control border border-border bg-background px-3 py-2 font-mono text-xs text-white focus:border-cyan disabled:opacity-50"
        disabled={disabled}
        id={id}
        onBlur={() => {
          try {
            onChange(JSON.parse(text))
            setError(null)
          } catch {
            setError('JSON inválido: revisa comas, comillas y llaves.')
          }
        }}
        onChange={(event) => setText(event.target.value)}
        value={text}
      />
      {error ? <p className="mt-1 text-xs text-danger">{error}</p> : null}
    </div>
  )
}

function DecoyTable({
  value,
  id,
  disabled,
  onChange,
}: {
  value: unknown
  id: string
  disabled: boolean
  onChange: (value: JsonObject[]) => void
}) {
  const rows = Array.isArray(value) ? value.filter(isRecord) : []
  const probabilitySum = rows.reduce((total, row) => total + Number(row.selection_probability ?? 0), 0)
  const updateRow = (index: number, key: string, nextValue: string | number) => {
    onChange(rows.map((row, rowIndex) => rowIndex === index ? { ...row, [key]: nextValue } : row))
  }

  return (
    <div aria-label="Intensidades decoy" className="min-w-0 flex-1 space-y-3" id={id}>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[500px] text-left text-xs">
          <caption className="sr-only">Intensidades y probabilidades de selección decoy</caption>
          <thead className="text-slate-500">
            <tr><th className="pb-2 font-medium">Nombre</th><th className="pb-2 font-medium">μ</th><th className="pb-2 font-medium">p</th><th className="w-10 pb-2"><span className="sr-only">Acciones</span></th></tr>
          </thead>
          <tbody className="divide-y divide-border">
            {rows.map((row, index) => (
              <tr key={`${String(row.name)}-${index}`}>
                <td className="py-2 pr-2"><input aria-label={`Nombre intensidad ${index + 1}`} className="h-8 w-full rounded-control border border-border bg-background px-2 text-white focus:border-cyan" disabled={disabled} onChange={(event) => updateRow(index, 'name', event.target.value)} value={formatInputValue(row.name)} /></td>
                <td className="py-2 pr-2"><input aria-label={`Fotones medios intensidad ${index + 1}`} className="h-8 w-full rounded-control border border-border bg-background px-2 font-mono text-white focus:border-cyan" disabled={disabled} min={0} onChange={(event) => updateRow(index, 'mean_photon_number', Number(event.target.value))} step="any" type="number" value={formatInputValue(row.mean_photon_number)} /></td>
                <td className="py-2 pr-2"><input aria-label={`Probabilidad intensidad ${index + 1}`} className="h-8 w-full rounded-control border border-border bg-background px-2 font-mono text-white focus:border-cyan" disabled={disabled} max={1} min={0} onChange={(event) => updateRow(index, 'selection_probability', Number(event.target.value))} step={0.01} type="number" value={formatInputValue(row.selection_probability)} /></td>
                <td className="py-2"><button aria-label={`Eliminar intensidad ${index + 1}`} className="flex h-8 w-8 items-center justify-center rounded-control border border-border text-slate-400 hover:border-danger hover:text-danger disabled:opacity-40" disabled={disabled} onClick={() => onChange(rows.filter((_, rowIndex) => rowIndex !== index))} type="button"><Trash2 aria-hidden="true" size={15} /></button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className={`font-mono text-xs ${Math.abs(probabilitySum - 1) < 1e-9 ? 'text-success' : 'text-warning'}`}>Suma p = {probabilitySum.toFixed(3)}</span>
        <button aria-label="Añadir intensidad decoy" className="flex h-8 items-center gap-2 rounded-control border border-border px-2 text-xs text-cyan hover:bg-cyan/10 disabled:opacity-40" disabled={disabled} onClick={() => onChange([...rows, { name: `decoy_${rows.length + 1}`, mean_photon_number: 0, selection_probability: 0 }])} type="button"><Plus aria-hidden="true" size={14} /> Añadir</button>
      </div>
    </div>
  )
}

function sliderMin(field: CatalogField): number {
  const minimum = field.min ?? 0
  return field.scale === 'log' ? Math.log10(minimum) : minimum
}

function sliderMax(field: CatalogField): number {
  const maximum = field.max ?? 1
  return field.scale === 'log' ? Math.log10(maximum) : maximum
}

function valueToSlider(value: number, field: CatalogField): number {
  const minimum = field.min ?? 0
  if (field.scale === 'log') return Math.log10(Math.max(value, minimum))
  return Number.isFinite(value) ? value : minimum
}

function valueFromSlider(value: number, field: CatalogField): number {
  const rawValue = field.scale === 'log' ? 10 ** value : value
  return field.type === 'integer' ? Math.round(rawValue) : rawValue
}
