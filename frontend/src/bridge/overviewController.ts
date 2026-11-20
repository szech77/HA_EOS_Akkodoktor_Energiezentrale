import { createApp, type App } from 'vue'
import { hostOf } from '@/bridge/host'
import { createOverviewStore, OVERVIEW_STORE } from '@/stores/overview'
import type { LegacyContext } from '@/types/host'
import type { OverviewSnapshot } from '@/types/overview'
import OverviewView from '@/views/OverviewView.vue'

/** Mount point of the overview in the panel markup (index.html, inside #overview). */
export const MOUNT_ID = 'overview-view'

export interface OverviewController {
  /** Follow a render of app.js with the current snapshot. */
  show(): void
}

/** Factory app.js uses for the overview (`EosOverview.create`). */
export function createOverviewController(context: LegacyContext): OverviewController {
  const target = context.document.getElementById(MOUNT_ID)
  if (!target) throw new Error('Overview mount point is missing')
  const host = hostOf(context)
  const read = () => context.getSnapshot() as unknown as OverviewSnapshot
  // The header logo carries the build version that bootstrap.js set; the hub uses the same file.
  const logo = context.document.querySelector('use[data-logo]')?.getAttribute('href') ?? './logo.svg#mark'
  const store = createOverviewStore(host, read(), logo)
  let app: App | null = null

  return {
    show() {
      store.snapshot.value = read()
      store.now.value = host.now()
      if (!app) {
        app = createApp(OverviewView).provide(OVERVIEW_STORE, store)
        app.mount(target)
      }
    },
  }
}
