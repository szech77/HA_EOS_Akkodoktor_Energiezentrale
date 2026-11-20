import { createApp, shallowRef, type App } from 'vue'
import { HOST, SNAPSHOT } from '@/composables/useHost'
import { hostOf } from '@/bridge/host'
import type { Host, LegacyContext, ViewController } from '@/types/host'
import PvWeatherView from '@/views/PvWeatherView.vue'
import { createPvWeatherStore, PV_WEATHER_STORE } from '@/stores/pvWeather'

/** Mount point of the view in the panel markup (index.html). */
export const MOUNT_ID = 'pv-view'

/**
 * Factory with the interface app.js already uses for this view (`EosForecast.create`):
 * open() mounts once and loads the forecast, update() follows panel refreshes, close() discards
 * answers of running requests.
 */
export function createPvWeatherController(context: LegacyContext): ViewController {
  const target = context.document.getElementById(MOUNT_ID)
  if (!target) throw new Error('PV view mount point is missing')
  const host: Host = hostOf(context)
  const snapshot = shallowRef(context.getSnapshot())
  const state = createPvWeatherStore(host, snapshot)
  let app: App | null = null

  return {
    open() {
      snapshot.value = context.getSnapshot()
      if (!app) {
        app = createApp(PvWeatherView).provide(HOST, host).provide(SNAPSHOT, snapshot).provide(PV_WEATHER_STORE, state)
        app.mount(target)
      }
      state.selected.value = null
      void state.forecast.load()
    },
    update() {
      snapshot.value = context.getSnapshot()
      state.forecast.refreshIfStale()
    },
    close() {
      state.forecast.cancel()
    },
  }
}
