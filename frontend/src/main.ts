/**
 * Entry of the panel bundle (vue/eos-vue.js), loaded by loader.js inside the Home Assistant panel
 * iframe. Requests go through the panel (panel.js), which owns the HA authentication.
 */
import { createApp } from 'vue'
import App from '@/App.vue'
import { createAppStore } from '@/stores/app'
import type { Preferences } from '@/stores/usage'

/** Browser storage for per-viewer conveniences; the accessor itself may throw when site data is blocked. */
function preferences(): Preferences | undefined {
  try {
    return window.localStorage
  } catch {
    return undefined
  }
}

const target = document.getElementById('app')
if (target) {
  const store = createAppStore({ view: window, document, navigatorLanguage: navigator.language })
  const app = createApp(App, { app: store, storage: preferences() })
  // Errors outside a page (header, status band) keep the panel from working: show them as such.
  app.config.errorHandler = error => store.fail(store.stage.value === 'language' ? 'language' : 'view', error)
  app.mount(target)
}
