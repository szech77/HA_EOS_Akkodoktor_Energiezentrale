/**
 * Entry of the Vue bundle (vue/eos-vue.js), loaded by bootstrap.js as a classic script.
 *
 * During the step-by-step migration each Vue feature registers a global interface for app.js;
 * app.js keeps owning routing, authentication and refreshes.
 */
import { createCarController } from '@/features/car/controller'
import { createPvWeatherController } from '@/features/pv-weather/controller'

declare global {
  // eslint-disable-next-line no-var
  var EosForecast: { create: typeof createPvWeatherController } | undefined
  // eslint-disable-next-line no-var
  var EosCar: { create: typeof createCarController } | undefined
}

globalThis.EosForecast = Object.freeze({ create: createPvWeatherController })
globalThis.EosCar = Object.freeze({ create: createCarController })
