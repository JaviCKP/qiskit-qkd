import type { JsonObject } from '@/api/client'

export function isRecord(value: unknown): value is JsonObject {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

export function cloneJson<T>(value: T): T {
  return structuredClone(value)
}

export function readTarget(
  scenario: JsonObject,
  target: string,
): unknown {
  const [section, field] = target.split('.')
  if (!section || !field) {
    return undefined
  }
  if (section === 'scenario') {
    return scenario[field]
  }
  const sectionValue = scenario[section]
  if (!isRecord(sectionValue)) {
    return undefined
  }
  return sectionValue[field]
}

export function writeTarget<T extends JsonObject>(
  scenario: T,
  target: string,
  value: unknown,
): T {
  const [section, field] = target.split('.')
  if (!section || !field) {
    return scenario
  }
  if (section === 'scenario') {
    return { ...scenario, [field]: value } as T
  }
  const sectionValue = scenario[section]
  if (!isRecord(sectionValue)) {
    return scenario
  }
  return {
    ...scenario,
    [section]: {
      ...sectionValue,
      [field]: value,
    },
  } as T
}
