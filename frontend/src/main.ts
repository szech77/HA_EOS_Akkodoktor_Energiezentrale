/**
 * Entry of the Vue bundle (vue/eos-vue.js), loaded by bootstrap.js as a classic script.
 *
 * During the step-by-step migration each Vue page registers a controller for app.js (src/bridge);
 * app.js keeps owning routing, authentication and refreshes.
 */
import { createDeviceController } from '@/bridge/deviceController'
import { createPvWeatherController } from '@/bridge/pvWeatherController'

declare global {
  // eslint-disable-next-line no-var
  var EosForecast: { create: typeof createPvWeatherController } | undefined
  // eslint-disable-next-line no-var
  var EosDevice: { create: typeof createDeviceController } | undefined
}

globalThis.EosForecast = Object.freeze({ create: createPvWeatherController })
globalThis.EosDevice = Object.freeze({ create: createDeviceController })
