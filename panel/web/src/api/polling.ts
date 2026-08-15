import { delay } from '@/lib/async'

import type { JobStatus } from './client'

const ACTIVE_JOB_STATUSES = new Set<JobStatus['status']>([
  'queued',
  'running',
  'cancellation_requested',
])

type PollOptions = {
  signal?: AbortSignal
  onStatus?: (status: JobStatus) => void
  initialDelayMs?: number
  maxDelayMs?: number
  backoffFactor?: number
  wait?: (delayMs: number, signal?: AbortSignal) => Promise<void>
}

export async function pollJobStatus(
  fetchStatus: (signal?: AbortSignal) => Promise<JobStatus>,
  options: PollOptions = {},
): Promise<JobStatus> {
  const {
    signal,
    onStatus,
    initialDelayMs = 250,
    maxDelayMs = 2_000,
    backoffFactor = 1.6,
    wait = delay,
  } = options
  signal?.throwIfAborted()
  let delayMs = initialDelayMs
  let completed = 0
  await waitUntilResumed(signal)
  let status = monotonicProgress(await fetchStatus(signal), completed)
  completed = status.progress.done
  onStatus?.(status)
  while (ACTIVE_JOB_STATUSES.has(status.status)) {
    await wait(delayMs, signal)
    signal?.throwIfAborted()
    await waitUntilResumed(signal)
    status = monotonicProgress(await fetchStatus(signal), completed)
    completed = status.progress.done
    onStatus?.(status)
    delayMs = Math.min(maxDelayMs, Math.round(delayMs * backoffFactor))
  }
  return status
}

/** Do not spend requests while the browser cannot make progress. */
export async function waitUntilResumed(signal?: AbortSignal): Promise<void> {
  if (!isPaused()) return
  await new Promise<void>((resolve, reject) => {
    const onResume = () => {
      if (!isPaused()) {
        cleanup()
        resolve()
      }
    }
    const onAbort = () => {
      cleanup()
      reject(signal?.reason)
    }
    const cleanup = () => {
      window.removeEventListener('online', onResume)
      document.removeEventListener('visibilitychange', onResume)
      signal?.removeEventListener('abort', onAbort)
    }
    window.addEventListener('online', onResume)
    document.addEventListener('visibilitychange', onResume)
    signal?.addEventListener('abort', onAbort, { once: true })
    onResume()
  })
}

function isPaused(): boolean {
  return typeof navigator !== 'undefined' && navigator.onLine === false
    || typeof document !== 'undefined' && document.hidden
}

function monotonicProgress(status: JobStatus, previousDone: number): JobStatus {
  const total = Math.max(0, status.progress.total)
  const done = Math.min(total, Math.max(previousDone, status.progress.done))
  return { ...status, progress: { done, total } }
}
