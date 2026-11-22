/** Test host: the real language packs of the integration and a controllable clock and backend. */
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import type { BackendRequest, FormatDecimal, PanelSnapshot, Translate } from '@/types/host'

type Pack = { locale: string; messages: Record<string, string> }

// Panel texts are maintained in the integration (energy/i18n); tests read them from there.
const PACKS = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..', 'custom_components', 'eos_energiezentrale', 'energy', 'i18n')

export function languagePack(code: 'de' | 'en'): Pack {
  return JSON.parse(readFileSync(join(PACKS, `${code}.json`), 'utf8')) as Pack
}

/** Backend data and services of a test; the mount helpers (test/mount.ts) build the stores from it. */
export interface TestContext {
  readonly document: Document
  snapshot: PanelSnapshot
  clock: { now: number }
  readonly request: BackendRequest
  readonly getSnapshot: () => PanelSnapshot
  readonly getHistory?: () => unknown
  readonly t: Translate
  readonly decimal: FormatDecimal
  readonly getLocale: () => string
  readonly now: () => number
  readonly lookup: (key: string) => string | undefined
  readonly refresh: () => Promise<void>
}

export function testContext(options: { code?: 'de' | 'en'; snapshot: PanelSnapshot; request: BackendRequest; now: number; refresh?: () => Promise<void> }): TestContext {
  const pack = languagePack(options.code ?? 'de')
  const clock = { now: options.now }
  const context: TestContext = {
    document,
    snapshot: options.snapshot,
    clock,
    request: options.request,
    getSnapshot: () => context.snapshot,
    // Missing keys fail the test instead of showing a key name in the view.
    t: (key, values = {}) => {
      const text = pack.messages[key]
      if (typeof text !== 'string') throw new Error(`Missing text ${key}`)
      return text.replace(/\{(\w+)\}/g, (match, name: string) => String(values[name] ?? match))
    },
    decimal: (value, digits = 1) => new Intl.NumberFormat(pack.locale, { maximumFractionDigits: digits }).format(value),
    getLocale: () => pack.locale,
    now: () => clock.now,
    lookup: key => pack.messages[key],
    refresh: options.refresh ?? (async () => undefined),
  }
  return context
}

/** Let pending promises and the following Vue render run. */
export const flush = async (): Promise<void> => {
  for (let index = 0; index < 3; index++) await new Promise(resolve => setTimeout(resolve, 0))
}
