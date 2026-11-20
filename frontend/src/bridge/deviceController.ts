import { createApp, type App } from 'vue'
import { hostOf } from '@/bridge/host'
import { CAR_STORE, createCarStore } from '@/stores/car'
import { createDeviceStore, DEVICE_STORE, parseDeviceRoute } from '@/stores/device'
import type { DeviceSnapshot, PanelHistory } from '@/types/device'
import type { LegacyContext } from '@/types/host'
import DeviceRoot from './DeviceRoot.vue'

/** Mount point of the device pages in the panel markup (index.html, inside #detail). */
export const MOUNT_ID = 'device-view'

const EMPTY_HISTORY: PanelHistory = { local: [], influx: [] }

export interface DeviceController {
  /** Show a device page ("battery", "energy", "car", "car/<encoded id>" …); false for any other route. */
  show(route: string, options?: { scrollToPlan?: boolean }): boolean
}

/**
 * Factory app.js uses for the device pages (`EosDevice.create`). app.js keeps routing and calls
 * show() on every render, so the pages follow each refresh of snapshot and history.
 */
export function createDeviceController(context: LegacyContext): DeviceController {
  const target = context.document.getElementById(MOUNT_ID)
  if (!target) throw new Error('Device view mount point is missing')
  const host = hostOf(context)
  const read = () => context.getSnapshot() as unknown as DeviceSnapshot
  const history = () => (context.getHistory?.() as PanelHistory | undefined) ?? EMPTY_HISTORY
  const device = createDeviceStore(host, read(), history())
  const car = createCarStore(device)
  let app: App | null = null

  return {
    show(key, options = {}) {
      const route = parseDeviceRoute(key)
      if (!route) return false
      device.snapshot.value = read()
      device.history.value = history()
      device.now.value = host.now()
      device.route.value = route
      if (options.scrollToPlan) car.scrollToPlan.value = true
      if (!app) {
        app = createApp(DeviceRoot).provide(DEVICE_STORE, device).provide(CAR_STORE, car)
        app.mount(target)
      }
      return true
    },
  }
}
