import { useEffect, useRef, useState } from 'react'
import {
  Cable,
  ChevronDown,
  ChevronUp,
  CloudSun,
  Orbit,
  Satellite,
  SlidersHorizontal,
  Sparkles,
  Waves,
  type LucideIcon,
} from 'lucide-react'

import type { MediumDefinition, MediumId } from './mediums'

type MediumGalleryProps = {
  media: MediumDefinition[]
  activeMediumId: MediumId
  onOpen: (mediumId: MediumId) => void
}

const icons: Record<MediumDefinition['icon'], LucideIcon> = {
  cable: Cable,
  cloud: CloudSun,
  orbit: Orbit,
  satellite: Satellite,
  sliders: SlidersHorizontal,
  sparkles: Sparkles,
  waves: Waves,
}

export function MediumGallery({ media, activeMediumId, onOpen }: MediumGalleryProps) {
  const [collapsed, setCollapsed] = useState(false)
  const previousMedium = useRef(activeMediumId)
  useEffect(() => {
    if (previousMedium.current !== activeMediumId) setCollapsed(true)
    previousMedium.current = activeMediumId
  }, [activeMediumId])
  const activeMedium = media.find((medium) => medium.id === activeMediumId)
  return (
    <section className={`min-w-0 rounded-panel border border-border bg-surface bg-panel-sheen p-4 shadow-panel sm:p-5 ${collapsed ? 'pb-3' : ''}`}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <p className="text-2xs font-semibold uppercase tracking-eyebrow text-cyan">Experimentos preparados</p>
          <h2 className="mt-1 text-base font-semibold text-white">
            {collapsed ? `Medio activo: ${activeMedium?.shortLabel ?? activeMediumId}` : 'Empieza con un escenario que ya tiene sentido'}
          </h2>
          <p className="mt-1 text-sm text-slate-400">
            {collapsed
              ? activeMedium?.summary ?? 'Elige otro medio para cargar una plantilla completa.'
              : 'Al elegir uno se configuran juntos emisor, canal y receptor.'}
          </p>
        </div>
        <button
          aria-expanded={!collapsed}
          className="inline-flex h-9 shrink-0 items-center justify-center gap-1.5 rounded-control border border-border bg-raised px-3 text-sm font-medium text-slate-300 transition-colors hover:border-border-strong hover:bg-overlay hover:text-white"
          onClick={() => setCollapsed((value) => !value)}
          type="button"
        >
          {collapsed ? <ChevronDown aria-hidden="true" size={15} /> : <ChevronUp aria-hidden="true" size={15} />}
          {collapsed ? 'Cambiar medio' : 'Ocultar galería'}
        </button>
      </div>
      {collapsed ? (
        <div aria-label="Medios disponibles" className="mt-3 flex min-w-0 gap-1.5 overflow-x-auto pb-1" role="list">
          {media.map((medium) => {
            const Icon = icons[medium.icon]
            const active = medium.id === activeMediumId
            return (
              <button
                aria-pressed={active}
                className={`flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
                  active
                    ? 'border-cyan/60 bg-cyan/10 text-cyan'
                    : 'border-border bg-background/50 text-slate-300 hover:border-border-strong hover:bg-raised hover:text-white'
                }`}
                key={medium.id}
                onClick={() => onOpen(medium.id)}
                type="button"
              >
                <Icon aria-hidden="true" size={14} />
                {medium.shortLabel}
              </button>
            )
          })}
        </div>
      ) : (
        <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4 xl:grid-cols-7">
          {media.map((medium) => {
            const Icon = icons[medium.icon]
            const active = medium.id === activeMediumId
            return (
              <button
                aria-pressed={active}
                className={`group relative flex min-w-0 flex-col overflow-hidden rounded-control border p-3 text-left transition-all duration-200 ease-emphasis ${
                  active
                    ? 'border-cyan/70 bg-cyan/[0.07] shadow-glow'
                    : 'border-border bg-background/50 hover:-translate-y-0.5 hover:border-border-strong hover:bg-raised hover:shadow-lifted'
                }`}
                key={medium.id}
                onClick={() => { onOpen(medium.id); setCollapsed(true) }}
                title={medium.summary}
                type="button"
              >
                <div className="flex items-center gap-2.5">
                  <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-control border transition-colors ${
                    active
                      ? 'border-cyan/40 bg-cyan/15 text-cyan'
                      : 'border-border bg-surface text-slate-400 group-hover:border-cyan/30 group-hover:text-cyan'
                  }`}
                  >
                    <Icon aria-hidden="true" size={16} />
                  </div>
                  <div className="min-w-0">
                    <span className={`block truncate text-sm font-medium ${active ? 'text-white' : 'text-slate-300'}`}>{medium.shortLabel}</span>
                    <span className="mt-0.5 block truncate font-mono text-2xs text-slate-500">{medium.expectedRange}</span>
                  </div>
                </div>
                <span className={`mt-3 block text-xs font-medium ${active ? 'text-cyan' : 'text-slate-400'}`}>
                  {active ? 'Plantilla activa' : medium.realismLabel}
                </span>
                <span className="mt-0.5 block truncate text-xs text-slate-500" title={medium.detectorLabel}>{medium.detectorLabel}</span>
              </button>
            )
          })}
        </div>
      )}
    </section>
  )
}
