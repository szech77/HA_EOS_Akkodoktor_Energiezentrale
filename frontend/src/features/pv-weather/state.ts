import { inject, ref, type InjectionKey, type Ref, type ShallowRef } from 'vue'
import type { Host, PanelSnapshot } from '@/host/types'
import { createFormat, type Format } from '@/shared/format'
import { createLabels, type Labels } from './labels'
import { usePvForecast, type PvForecast } from './usePvForecast'

/** Everything the PV & weather view shares between its components and its controller. */
export interface PvWeatherState {
  readonly forecast: PvForecast
  /** Start time of the hour the user tapped; null shows the hint. */
  readonly selected: Ref<string | null>
  readonly format: Format
  readonly labels: Labels
}

export const PV_WEATHER: InjectionKey<PvWeatherState> = Symbol('eos-pv-weather')

export function createPvWeatherState(host: Host, snapshot: ShallowRef<PanelSnapshot>): PvWeatherState {
  const format = createFormat(host, () => snapshot.value.zone)
  return {
    forecast: usePvForecast(host, snapshot),
    selected: ref(null),
    format,
    labels: createLabels(host.t, format, host.decimal),
  }
}

export function usePvWeather(): PvWeatherState {
  const state = inject(PV_WEATHER)
  if (!state) throw new Error('PV weather state is not provided')
  return state
}
