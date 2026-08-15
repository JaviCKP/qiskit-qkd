import { useEffect, useRef, useState } from 'react'
import {
  Cable,
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
  return (
    <section className={`min-w-0 rounded-2xl border border-border bg-surface/70 p-4 sm:p-5 ${collapsed ? 'pb-3' : ''}`}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-cyan">Experimentos preparados</p>
          <h2 className="mt-1 text-base font-semibold text-white">
            {collapsed ? `Medio activo: ${media.find((medium) => medium.id === activeMediumId)?.shortLabel ?? activeMediumId}` : 'Empieza con un escenario que ya tiene sentido'}
          </h2>
          {!collapsed ? <p className="text-sm text-slate-400">Al elegir uno se configuran juntos emisor, canal y receptor.</p> : null}
        </div>
        <button
          aria-expanded={!collapsed}
          className="inline-flex h-9 shrink-0 items-center justify-center rounded-control border border-border px-3 text-sm font-medium text-slate-300 hover:border-slate-500 hover:text-white"
          onClick={() => setCollapsed((value) => !value)}
          type="button"
        >
          {collapsed ? 'Cambiar medio' : 'Ocultar galeria'}
        </button>
      </div>
      {collapsed ? (
        <div className="mt-3 flex min-w-0 gap-2 overflow-x-auto pb-1" role="list" aria-label="Medios disponibles">
          {media.map((medium) => (
            <button
              aria-pressed={medium.id === activeMediumId}
              className={`shrink-0 rounded-control border px-3 py-2 text-sm ${medium.id === activeMediumId ? 'border-cyan/60 bg-cyan/10 text-cyan' : 'border-border bg-background/50 text-slate-300 hover:border-slate-500'}`}
              key={medium.id}
              onClick={() => onOpen(medium.id)}
              type="button"
            >
              {medium.shortLabel}
            </button>
          ))}
        </div>
      ) : (
        <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4 xl:grid-cols-7">
          {media.map((medium) => {
          const Icon = icons[medium.icon]
          const active = medium.id === activeMediumId
          return (
            <button
              aria-pressed={active}
              className={`group min-w-0 rounded-xl border p-3 text-left transition-colors ${
                active
                  ? 'border-cyan/70 bg-cyan/10 shadow-[0_0_0_1px_rgba(47,200,222,0.12)]'
                  : 'border-border bg-background/50 hover:border-slate-500 hover:bg-raised'
              }`}
              key={medium.id}
              onClick={() => { onOpen(medium.id); setCollapsed(true) }}
              type="button"
            >
              <div className="flex items-center gap-2.5">
                <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border ${active ? 'border-cyan/30 bg-cyan/10 text-cyan' : 'border-border bg-surface text-slate-400 group-hover:text-cyan'}`}>
                  <Icon aria-hidden="true" size={16} />
                </div>
                <div className="min-w-0">
                  <span className={`block truncate text-sm font-medium ${active ? 'text-white' : 'text-slate-300'}`}>{medium.shortLabel}</span>
                  <span className="mt-0.5 block truncate text-[11px] text-slate-500">{medium.expectedRange}</span>
                </div>
              </div>
              <span className={`mt-3 block text-xs ${active ? 'text-cyan' : 'text-slate-500'}`}>
                {active ? 'Plantilla activa' : medium.realismLabel}
              </span>
              <span className="mt-1 block truncate text-xs text-slate-500" title={medium.detectorLabel}>{medium.detectorLabel}</span>
            </button>
          )
          })}
        </div>
      )}
    </section>
  )
}
