import { afterEach, expect, test, vi } from 'vitest'

import type { JobStatus } from './client'
import { pollJobStatus } from './polling'

afterEach(() => {
  Object.defineProperty(navigator, 'onLine', { configurable: true, value: true })
  Object.defineProperty(document, 'hidden', { configurable: true, value: false })
})

test('polls active states with bounded exponential backoff and monotonic snapshots', async () => {
  const statuses = [
    status('queued', 0),
    status('running', 1),
    status('cancellation_requested', 2),
    status('done', 3),
  ]
  const fetchStatus = vi.fn(async () => statuses.shift() as JobStatus)
  const delays: number[] = []
  const snapshots: JobStatus[] = []

  const result = await pollJobStatus(fetchStatus, {
    onStatus: (snapshot) => snapshots.push(snapshot),
    wait: async (delayMs) => {
      delays.push(delayMs)
    },
  })

  expect(result.status).toBe('done')
  expect(delays).toEqual([250, 400, 640])
  expect(snapshots.map((snapshot) => snapshot.progress.done)).toEqual([0, 1, 2, 3])
})

test('does not start or continue polling after abort', async () => {
  const controller = new AbortController()
  controller.abort()
  const fetchStatus = vi.fn(async () => status('running', 0))

  await expect(
    pollJobStatus(fetchStatus, { signal: controller.signal }),
  ).rejects.toMatchObject({ name: 'AbortError' })
  expect(fetchStatus).not.toHaveBeenCalled()
})

test('pauses while offline and resumes on the online event', async () => {
  Object.defineProperty(navigator, 'onLine', { configurable: true, value: false })
  const fetchStatus = vi.fn(async () => status('done', 3))
  const pending = pollJobStatus(fetchStatus, { wait: async () => undefined })
  await Promise.resolve()
  expect(fetchStatus).not.toHaveBeenCalled()

  Object.defineProperty(navigator, 'onLine', { configurable: true, value: true })
  window.dispatchEvent(new Event('online'))
  await expect(pending).resolves.toMatchObject({ status: 'done' })
  expect(fetchStatus).toHaveBeenCalledTimes(1)
})

function status(statusValue: JobStatus['status'], done: number): JobStatus {
  return {
    job_id: 'job-test',
    status: statusValue,
    progress: { done, total: 3 },
    elapsed_s: done,
  }
}
