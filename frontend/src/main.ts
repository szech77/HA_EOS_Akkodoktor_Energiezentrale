/**
 * Entry of the Vue bundle (vue/eos-vue.js), loaded by bootstrap.js as a classic script.
 *
 * During the step-by-step migration each Vue feature registers the global interface that
 * app.js already uses for it; app.js keeps owning routing, authentication and refreshes.
 */
import { createPvWeatherController } from '@/features/pv-weather/controller'

declare global {
  // eslint-disable-next-line no-var
  var EosForecast: { create: typeof createPvWeatherController } | undefined
}

globalThis.EosForecast = Object.freeze({ create: createPvWeatherController })
