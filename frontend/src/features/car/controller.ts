import { createApp, type App } from 'vue'
import { hostOf, type LegacyContext } from '@/host/types'
import CarPage from './CarPage.vue'
import { CAR, createCarState, parseCarRoute } from './state'
import type { CarSnapshot } from './types'

/** Mount point of the car pages in the panel markup (index.html, inside #detail). */
export const MOUNT_ID = 'car-app'

export interface CarController {
  /** Show "car" or "car/<encoded id>" with the current snapshot; app.js calls it on every render. */
  show(route: string, options?: { scrollToPlan?: boolean }): boolean
}

/**
 * Factory app.js uses for the car pages (`EosCar.create`). app.js keeps routing, the page title,
 * key figures and charts; this view renders everything specific to one vehicle or the fleet.
 */
export function createCarController(context: LegacyContext): CarController {
  const target = context.document.getElementById(MOUNT_ID)
  if (!target) throw new Error('Car view mount point is missing')
  const host = hostOf(context)
  const read = () => context.getSnapshot() as CarSnapshot
  const state = createCarState(host, read())
  let app: App | null = null

  return {
    show(key, options = {}) {
      const route = parseCarRoute(key)
      if (!route) return false
      state.snapshot.value = read()
      state.now.value = host.now()
      state.route.value = route
      if (options.scrollToPlan) state.scrollToPlan.value = true
      if (!app) {
        app = createApp(CarPage).provide(CAR, state)
        app.mount(target)
      }
      return true
    },
  }
}
