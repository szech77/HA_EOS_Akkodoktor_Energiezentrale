/**
 * Consumption and cost reports: the selected period, date and chart unit, and the loaded report.
 * Period and unit are per-viewer conveniences kept in the browser; the date is not remembered.
 */
import { inject, shallowRef, type InjectionKey, type ShallowRef } from 'vue'
import type { Host } from '@/types/host'
import type { ChartUnit, Period, Report } from '@/types/usage'
import { createFormat } from '@/utils/format'
import { createUsageText, usageKeys, type UsageText, type Vehicle } from '@/utils/usage'
import { createUsageCharts, type UsageCharts } from '@/utils/usageCharts'

export const PERIODS: readonly Period[] = ['day', 'month', 'year']
export const UNITS: readonly ChartUnit[] = ['kw', 'kwh', 'eur']
export const PERIOD_KEY = 'eos-energiezentrale.billing-period'
export const UNIT_KEY = 'eos-energiezentrale.billing-unit'
/** A shown report is reloaded at most this often while the page follows the panel refreshes. */
export const REPORT_MAX_AGE_MS = 60_000

/** Browser storage may be disabled or blocked; the selection then lives in memory only. */
export interface Preferences {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
}

function saved<T extends string>(storage: Preferences | undefined, key: string, allowed: readonly T[], fallback: T): T {
  try {
    const value = storage?.getItem(key)
    if (allowed.includes(value as T)) return value as T
  } catch {
    // Keep the default.
  }
  return fallback
}

function remember(storage: Preferences | undefined, key: string, value: string) {
  try {
    storage?.setItem(key, value)
  } catch {
    // Keep the in-memory selection.
  }
}

export interface UsageStore {
  readonly host: Host
  readonly period: ShallowRef<Period>
  readonly unit: ShallowRef<ChartUnit>
  /** First day of the shown period (YYYY-MM-DD, installation time zone); null is "now". */
  readonly date: ShallowRef<string | null>
  readonly report: ShallowRef<Report | null>
  readonly loading: ShallowRef<boolean>
  readonly error: ShallowRef<string | null>
  readonly text: UsageText
  readonly charts: UsageCharts
  /** Report pages of this installation, in the order of the sub navigation. */
  keys(): string[]
  vehicles(): readonly Vehicle[]
  /** Time zone of the installation. */
  zone(): string | undefined
  /** Today in the installation time zone. */
  today(): string
  selectPeriod(value: string): boolean
  selectUnit(value: string): boolean
  /** Step one period back or forward, or return to the current one. */
  move(step: -1 | 1 | 'now'): void
  /** Open a bin of a month or year chart as its day or month. */
  drill(date: string): void
  /** Load the shown period; without force a report younger than REPORT_MAX_AGE_MS is kept. */
  load(force?: boolean): Promise<void>
  /** Cost settings changed: the next visit loads the report again. */
  invalidate(): void
}

export const USAGE_STORE: InjectionKey<UsageStore> = Symbol('eos-usage')

export interface UsageSources {
  readonly zone: () => string | undefined
  readonly vehicles: () => readonly Vehicle[]
  readonly features: () => Readonly<Record<string, boolean>> | undefined
}

export function createUsageStore(host: Host, sources: UsageSources, storage?: Preferences): UsageStore {
  const { zone, vehicles } = sources
  const period = shallowRef<Period>(saved(storage, PERIOD_KEY, PERIODS, 'month'))
  const unit = shallowRef<ChartUnit>(saved(storage, UNIT_KEY, UNITS, 'kwh'))
  const date = shallowRef<string | null>(null)
  const report = shallowRef<Report | null>(null)
  const loading = shallowRef(false)
  const error = shallowRef<string | null>(null)
  const format = createFormat(host, zone)
  const text = createUsageText(host, zone, vehicles)
  let loadedKey: string | null = null
  let loadedAt = 0

  const today = () => format.dayKey(host.now())
  const selectPeriod = (value: string) => {
    if (!PERIODS.includes(value as Period)) return false
    period.value = value as Period
    remember(storage, PERIOD_KEY, value)
    return true
  }

  async function load(force = false): Promise<void> {
    date.value ??= today()
    const key = `${period.value}/${date.value}`
    if (loading.value || (!force && loadedKey === key && Date.now() - loadedAt < REPORT_MAX_AGE_MS)) return
    loading.value = true
    error.value = null
    try {
      const result = await host.request<Report>('accounting', { period: period.value, date: date.value })
      if (`${period.value}/${date.value}` === key) {
        report.value = result
        loadedKey = key
        loadedAt = Date.now()
      }
    } catch (failure) {
      error.value = failure instanceof Error ? failure.message : String(failure)
    } finally {
      loading.value = false
    }
    // The selection changed while loading: load what is shown now.
    if (`${period.value}/${date.value}` !== key) await load(true)
  }

  return {
    host,
    period,
    unit,
    date,
    report,
    loading,
    error,
    text,
    charts: createUsageCharts(text, host, zone),
    keys: () => usageKeys(sources.features(), vehicles()),
    vehicles,
    zone,
    today,
    selectPeriod(value) {
      const changed = selectPeriod(value)
      if (changed) void load(true)
      return changed
    },
    selectUnit(value) {
      // Switching kW/kWh/€ only redraws; the report already carries all of them.
      if (!UNITS.includes(value as ChartUnit)) return false
      unit.value = value as ChartUnit
      remember(storage, UNIT_KEY, value)
      return true
    },
    move(step) {
      if (step === 'now') date.value = today()
      else {
        const cursor = new Date(`${date.value ?? today()}T12:00:00Z`)
        if (period.value === 'day') cursor.setUTCDate(cursor.getUTCDate() + step)
        else if (period.value === 'month') {
          cursor.setUTCDate(1)
          cursor.setUTCMonth(cursor.getUTCMonth() + step)
        } else {
          cursor.setUTCMonth(0, 1)
          cursor.setUTCFullYear(cursor.getUTCFullYear() + step)
        }
        date.value = cursor.toISOString().slice(0, 10)
      }
      void load(true)
    },
    drill(day) {
      if (period.value === 'day') return
      date.value = day
      selectPeriod(period.value === 'year' ? 'month' : 'day')
      void load(true)
    },
    load,
    invalidate() {
      loadedAt = 0
    },
  }
}

export function useUsageStore(): UsageStore {
  const store = inject(USAGE_STORE)
  if (!store) throw new Error('Usage store is not provided')
  return store
}
