import { ref, shallowRef, type Ref, type ShallowRef } from 'vue'
import type { Host, PanelSnapshot } from '@/host/types'
import { isNumber } from '@/shared/format'
import { FORECAST_STATUSES, type ForecastStatus, type ViewStatus, type WeatherForecast } from './types'

/** The strip refreshes at least this often, even without a new PV forecast. */
export const RELOAD_MS = 15 * 60_000

/**
 * Only the PV forecast itself decides about a reload: totals and vehicle estimates change with
 * every poll and would otherwise reload the view every few seconds.
 */
export function forecastKey(snapshot: PanelSnapshot): string {
  return JSON.stringify((snapshot.forecast ?? []).filter(row => isNumber(row?.solar)).map(row => [row.time, row.end, row.solar]))
}

const known = (status: string): status is ForecastStatus => (FORECAST_STATUSES as readonly string[]).includes(status)

export interface PvForecast {
  readonly data: ShallowRef<WeatherForecast | null>
  readonly status: Ref<ViewStatus>
  /** Load now; a reload keeps the current strip visible and ignores late answers. */
  load(): Promise<void>
  /** Reload only when the PV forecast changed or the last load is older than RELOAD_MS. */
  refreshIfStale(): void
  /** Answers of running requests are discarded (view closed). */
  cancel(): void
}

export function usePvForecast(host: Host, snapshot: ShallowRef<PanelSnapshot>): PvForecast {
  const data = shallowRef<WeatherForecast | null>(null)
  const status = ref<ViewStatus>('loading')
  let generation = 0
  let key = ''
  let loadedAt = 0

  async function load(): Promise<void> {
    const token = ++generation
    const first = data.value === null
    key = forecastKey(snapshot.value)
    loadedAt = host.now()
    if (first) status.value = 'loading'
    try {
      const result = await host.request<WeatherForecast>('weather_forecast')
      if (token !== generation) return
      data.value = result
      status.value = known(result?.status) ? result.status : 'unavailable'
    } catch {
      if (token !== generation) return
      // A failed reload keeps the strip that is already visible.
      if (first) {
        data.value = null
        status.value = 'unavailable'
      }
    }
  }

  function refreshIfStale(): void {
    if (status.value === 'loading') return
    if (forecastKey(snapshot.value) !== key || host.now() - loadedAt >= RELOAD_MS) void load()
  }

  return { data, status, load, refreshIfStale, cancel: () => void ++generation }
}
