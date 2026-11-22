import { inject, ref, type InjectionKey, type Ref, type ShallowRef } from 'vue'
import type { Host, PanelSnapshot } from '@/types/host'
import { createFormat, type Format } from '@/utils/format'
import { createLabels, type Labels } from '@/utils/pvWeatherLabels'
import { usePvForecast, type PvForecast } from '@/composables/usePvForecast'

/** Everything the PV & weather view shares between its components and its controller. */
export interface PvWeatherStore {
  readonly forecast: PvForecast
  /** Start time of the hour the user tapped; null shows the hint. */
  readonly selected: Ref<string | null>
  readonly format: Format
  readonly labels: Labels
}

export const PV_WEATHER_STORE: InjectionKey<PvWeatherStore> = Symbol('eos-pv-weather')

export function createPvWeatherStore(host: Host, snapshot: ShallowRef<PanelSnapshot>): PvWeatherStore {
  const format = createFormat(host, () => snapshot.value.zone)
  return {
    forecast: usePvForecast(host, snapshot),
    selected: ref(null),
    format,
    labels: createLabels(host.t, format, host.decimal),
  }
}

export function usePvWeatherStore(): PvWeatherStore {
  const state = inject(PV_WEATHER_STORE)
  if (!state) throw new Error('PV weather state is not provided')
  return state
}
