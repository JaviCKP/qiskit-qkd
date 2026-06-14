export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

export function cloneJson<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

export function readTarget(
  scenario: Record<string, unknown>,
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

export function writeTarget(
  scenario: Record<string, unknown>,
  target: string,
  value: unknown,
): Record<string, unknown> {
  const [section, field] = target.split('.')
  if (!section || !field) {
    return scenario
  }
  if (section === 'scenario') {
    return { ...scenario, [field]: value }
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
  }
}
