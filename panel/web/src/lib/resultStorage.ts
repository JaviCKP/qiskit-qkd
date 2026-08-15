import type { StateStorage } from 'zustand/middleware'

/**
 * The workspace used to persist complete run/curve payloads in localStorage.
 * That made a 20k-event result turn every draft edit into a multi-megabyte
 * synchronous stringify.  This storage adapter is deliberately boring: it
 * keeps only draft and job metadata, and drops recreatable result payloads
 * before they reach localStorage.
 */

export const RESULT_STORAGE_VERSION = 3
export const RESULT_STORAGE_MAX_BYTES = 512_000

export type ResultStorageDiagnostic =
  | { kind: 'quota'; key: string; bytes: number }
  | { kind: 'corrupt'; key: string }
  | { kind: 'future-version'; key: string; version: number }
  | { kind: 'unavailable'; key: string; reason: string }

let lastDiagnostic: ResultStorageDiagnostic | null = null

export function getResultStorageDiagnostic(): ResultStorageDiagnostic | null {
  return lastDiagnostic
}

export function clearResultStorageDiagnostic(): void {
  lastDiagnostic = null
}

/** Remove fields that are either large result payloads or event logs. */
export function compactPersistedWorkspace(value: unknown, metadataOnly = false): unknown {
  if (!isRecord(value)) return value
  const state = isRecord(value.state) ? { ...value.state } : value
  if (isRecord(state)) {
    if (Array.isArray(state.runs)) {
      state.runs = state.runs.map((run) => compactRun(run, metadataOnly))
    }
    if (Array.isArray(state.curves)) {
      state.curves = state.curves.map((curve) => compactCurve(curve, metadataOnly))
    }
    if (isRecord(state.activeRun)) state.activeRun = compactActiveRun(state.activeRun)
    if (isRecord(state.activeSweep)) state.activeSweep = compactActiveSweep(state.activeSweep)
  }
  return isRecord(value.state) ? { ...value, state } : state
}

export function compactWorkspaceState(value: unknown, metadataOnly = false): unknown {
  const wrapped = compactPersistedWorkspace({ state: value }, metadataOnly)
  return isRecord(wrapped) && 'state' in wrapped ? wrapped.state : wrapped
}

/**
 * A StateStorage implementation that never throws during rehydration or
 * quota pressure.  Corrupt data is ignored, and future versions are left in
 * place so a downgrade can still recover them.
 */
export function createResultStorage(
  backing: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'> | undefined =
    typeof window === 'undefined' ? undefined : window.localStorage,
): StateStorage {
  return {
    getItem: (key) => {
      if (!backing) return null
      try {
        const raw = backing.getItem(key)
        if (raw === null) return null
        const parsed: unknown = JSON.parse(raw)
        if (isRecord(parsed) && typeof parsed.version === 'number' && parsed.version > RESULT_STORAGE_VERSION) {
          lastDiagnostic = { kind: 'future-version', key, version: parsed.version }
          return null
        }
        return JSON.stringify(compactPersistedWorkspace(parsed))
      } catch {
        lastDiagnostic = { kind: 'corrupt', key }
        try {
          backing.removeItem(key)
        } catch {
          // A broken storage implementation must not prevent the app booting.
        }
        return null
      }
    },
    setItem: (key, value) => {
      if (!backing) return
      const compacted = compactPersistedWorkspace(parseJson(value))
      let encoded = JSON.stringify(compacted)
      try {
        // Keep an explicit cap so a pathological draft cannot monopolise the
        // synchronous storage quota.  IDs and draft fields are retained.
        if (encoded.length > RESULT_STORAGE_MAX_BYTES) {
          encoded = JSON.stringify(compactPersistedWorkspace(compacted, true))
        }
        backing.setItem(key, encoded)
        lastDiagnostic = null
      } catch (error) {
        if (isQuotaError(error)) {
          lastDiagnostic = { kind: 'quota', key, bytes: encoded.length }
          try {
            const metadataOnly = JSON.stringify(compactPersistedWorkspace(compacted, true))
            backing.setItem(key, metadataOnly)
            return
          } catch {
            // Quota can be exhausted before even metadata fits.  Losing a
            // cache is preferable to crashing every state update.
            return
          }
        }
        lastDiagnostic = { kind: 'unavailable', key, reason: error instanceof Error ? error.message : String(error) }
      }
    },
    removeItem: (key) => {
      try {
        backing?.removeItem(key)
      } catch (error) {
        lastDiagnostic = { kind: 'unavailable', key, reason: error instanceof Error ? error.message : String(error) }
      }
    },
  }
}

export const resultStorage = createResultStorage()

function parseJson(value: string): unknown {
  try {
    return JSON.parse(value)
  } catch {
    return null
  }
}

function compactRun(value: unknown, metadataOnly = false): unknown {
  if (!isRecord(value)) return null
  const run = metadataOnly
    ? pickMetadata(value, ['jobId', 'label', 'digest', 'seed', 'startedAt', 'completedAt', 'costEstimate', 'status', 'scenario'])
    : { ...value, result: {} }
  if (isRecord(run.status)) run.status = compactStatus(run.status)
  return run
}

function compactCurve(value: unknown, metadataOnly = false): unknown {
  if (!isRecord(value)) return null
  return metadataOnly
    ? pickMetadata(value, ['jobId', 'baseDigest', 'baseLabel', 'scenario', 'axis', 'series', 'metric', 'repeats', 'createdAt', 'costEstimate'])
    : { ...value, result: {} }
}

function compactActiveRun(value: Record<string, unknown>): Record<string, unknown> {
  const run = { ...value }
  if (isRecord(run.status)) run.status = compactStatus(run.status)
  return run
}

function compactActiveSweep(value: Record<string, unknown>): Record<string, unknown> {
  const sweep = { ...value }
  if (isRecord(sweep.status)) sweep.status = compactStatus(sweep.status)
  return sweep
}

function compactStatus(value: Record<string, unknown>): Record<string, unknown> {
  const status = { ...value }
  // result may contain the complete event sample.  result_summary is a small
  // diagnostic DTO and is intentionally retained for the offline UI.
  delete status.result
  return status
}

function pickMetadata(value: Record<string, unknown>, keys: string[]): Record<string, unknown> {
  return Object.fromEntries(keys.filter((key) => key in value).map((key) => [key, value[key]]))
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isQuotaError(error: unknown): boolean {
  return error instanceof DOMException && (error.name === 'QuotaExceededError' || error.code === 22)
    || isRecord(error) && (error.name === 'QuotaExceededError' || error.code === 22)
}
