import { createApp, type App } from 'vue'
import { hostOf } from '@/bridge/host'
import { createStatusStore, STATUS_STORE } from '@/stores/status'
import type { LegacyContext } from '@/types/host'
import type { Notice, StatusSnapshot } from '@/types/status'
import StatusRoot from './StatusRoot.vue'

/** Mount points in the panel markup (index.html). */
export const MOUNT_ID = 'status-view'
const TARGETS = ['nav-badge', 'notices-view']

export interface StatusController {
  /** Follow a render of app.js: current route, snapshot and browser-side notices. */
  show(route: string): void
}

/** Factory app.js uses for the status band and notices (`EosStatus.create`). */
export function createStatusController(context: LegacyContext & { getBrowserNotices?: () => readonly Notice[] }): StatusController {
  const document = context.document
  const target = document.getElementById(MOUNT_ID)
  if (!target || TARGETS.some(id => !document.getElementById(id))) throw new Error('Status view mount point is missing')
  const read = () => context.getSnapshot() as unknown as StatusSnapshot
  const store = createStatusStore(hostOf(context), read())
  let app: App | null = null

  return {
    show(route) {
      store.snapshot.value = read()
      store.browserNotices.value = context.getBrowserNotices?.() ?? []
      store.route.value = route
      if (!app) {
        app = createApp(StatusRoot).provide(STATUS_STORE, store)
        app.mount(target)
      }
    },
  }
}
