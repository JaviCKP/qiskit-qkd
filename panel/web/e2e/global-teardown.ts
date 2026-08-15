import { spawn } from 'node:child_process'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'

/** Remove only temporary stores created by the E2E runner. */
export default async function globalTeardown(): Promise<void> {
  const runToken = process.env.QKD_E2E_RUN_TOKEN
  if (!runToken || runToken.length > 64 || !/^[A-Za-z0-9_-]+$/.test(runToken)) return
  const tempRoot = path.resolve(os.tmpdir())
  const expectedPrefix = `qkd-panel-e2e-${runToken}-`
  const entries = await fs.readdir(tempRoot, { withFileTypes: true })
  const targets = entries
    .filter((entry) => entry.isDirectory() && entry.name.startsWith(expectedPrefix))
    .map((entry) => {
      const target = path.resolve(tempRoot, entry.name)
      return path.dirname(target) === tempRoot ? target : null
    })
    .filter((target): target is string => target !== null)
  if (!targets.length) return
  // On Windows Playwright may run globalTeardown before it force-stops the
  // webServer process, leaving SQLite WAL handles briefly locked.  A detached
  // best-effort watcher finishes removal after that process exits; it has no
  // access beyond the explicitly enumerated temporary target paths.
  spawnDetachedCleanup(targets)
  await Promise.all(targets.map((target) => removeWithRetry(target)))
}

async function removeWithRetry(target: string): Promise<void> {
  for (let attempt = 0; attempt < 5; attempt += 1) {
    try {
      await fs.rm(target, { recursive: true, force: true })
      return
    } catch (error) {
      if (!isRetryableRemovalError(error)) throw error
      await new Promise((resolve) => setTimeout(resolve, 100))
    }
  }
  return
}

function isRetryableRemovalError(error: unknown): boolean {
  return typeof error === 'object' && error !== null && 'code' in error
    && ((error as { code?: string }).code === 'EBUSY' || (error as { code?: string }).code === 'EPERM')
}

function spawnDetachedCleanup(targets: string[]): void {
  const script = [
    'const fs=require("node:fs/promises");',
    `const targets=${JSON.stringify(targets)};`,
    '(async()=>{for(let i=0;i<120;i++){let left=[];for(const target of targets){try{await fs.rm(target,{recursive:true,force:true})}catch(error){if(error?.code!=="EBUSY"&&error?.code!=="EPERM")continue;left.push(target)}}if(!left.length)return;await new Promise(resolve=>setTimeout(resolve,250))}})().catch(()=>{})',
  ].join('')
  const child = spawn(process.execPath, ['-e', script], {
    detached: true,
    stdio: 'ignore',
    windowsHide: true,
  })
  child.unref()
}
