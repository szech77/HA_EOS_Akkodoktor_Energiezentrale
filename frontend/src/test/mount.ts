/**
 * Mounts single pages with their stores, the way App.vue provides them, so view tests do not need
 * the whole panel. Each call follows the test context's current snapshot.
 */
import { createApp, defineComponent, h, shallowRef, triggerRef, type App, type Component } from 'vue'
import { HOST, SNAPSHOT } from '@/composables/useHost'
import { CAR_STORE, createCarStore } from '@/stores/car'
import { createDeviceStore, DEVICE_STORE, parseDeviceRoute } from '@/stores/device'
import { createOverviewStore, OVERVIEW_STORE } from '@/stores/overview'
import { createPvWeatherStore, PV_WEATHER_STORE } from '@/stores/pvWeather'
import { createSettingsStore, SETTINGS_STORE, type SettingsSnapshot } from '@/stores/settings'
import { createStatusStore, STATUS_STORE } from '@/stores/status'
import { createUsageStore, USAGE_STORE, type Preferences } from '@/stores/usage'
import type { DeviceSnapshot, PanelHistory } from '@/types/device'
import type { Host, PanelSnapshot } from '@/types/host'
import type { OverviewSnapshot } from '@/types/overview'
import type { Notice, StatusSnapshot } from '@/types/status'
import NavBadge from '@/components/status/NavBadge.vue'
import StatusArea from '@/components/status/StatusArea.vue'
import DevicePageView from '@/views/DevicePageView.vue'
import NoticesView from '@/views/NoticesView.vue'
import OverviewView from '@/views/OverviewView.vue'
import PvWeatherView from '@/views/PvWeatherView.vue'
import SettingsView from '@/views/SettingsView.vue'
import UsageView from '@/views/UsageView.vue'
import DayBalance from '@/components/overview/DayBalance.vue'
import type { Report } from '@/types/usage'
import type { TestContext } from './host'

const EMPTY_HISTORY: PanelHistory = { local: [], influx: [] }

export function hostOf(context: TestContext): Host {
  return {
    request: context.request,
    t: context.t,
    decimal: context.decimal,
    locale: context.getLocale,
    now: () => context.clock.now,
    lookup: context.lookup ?? (() => undefined),
    refresh: context.refresh ?? (async () => undefined),
  }
}

function target(id: string): HTMLElement {
  const element = document.getElementById(id)
  if (!element) throw new Error(`Test mount point #${id} is missing`)
  return element
}

/** Device and car pages; show() returns false for routes that are no device page. */
export function mountDevice(context: TestContext, id: string) {
  const host = hostOf(context)
  const snapshot = shallowRef(context.getSnapshot() as unknown as DeviceSnapshot)
  const history = shallowRef((context.getHistory?.() as PanelHistory | undefined) ?? EMPTY_HISTORY)
  const now = shallowRef(host.now())
  const device = createDeviceStore(host, snapshot, history, now)
  const car = createCarStore(device)
  let app: App | null = null
  return {
    show(key: string, options: { scrollToPlan?: boolean } = {}) {
      const route = parseDeviceRoute(key)
      if (!route) return false
      snapshot.value = context.getSnapshot() as unknown as DeviceSnapshot
      history.value = (context.getHistory?.() as PanelHistory | undefined) ?? EMPTY_HISTORY
      now.value = host.now()
      device.route.value = route
      if (options.scrollToPlan) car.scrollToPlan.value = true
      if (!app) (app = createApp(DevicePageView).provide(DEVICE_STORE, device).provide(CAR_STORE, car)).mount(target(id))
      return true
    },
  }
}

export function mountOverview(context: TestContext, id: string) {
  const host = hostOf(context)
  const snapshot = shallowRef(context.getSnapshot() as unknown as OverviewSnapshot)
  const now = shallowRef(host.now())
  const store = createOverviewStore(host, snapshot, now, './logo.svg#mark')
  let app: App | null = null
  return {
    show() {
      snapshot.value = context.getSnapshot() as unknown as OverviewSnapshot
      now.value = host.now()
      if (!app) (app = createApp(OverviewView).provide(OVERVIEW_STORE, store)).mount(target(id))
    },
  }
}

/** PV & weather page: open() mounts a fresh visit, update() follows a refresh, close() leaves. */
export function mountPvWeather(context: TestContext, id: string) {
  const host = hostOf(context)
  const snapshot = shallowRef<PanelSnapshot>(context.getSnapshot())
  const store = createPvWeatherStore(host, snapshot)
  let app: App | null = null
  const close = () => {
    app?.unmount()
    app = null
  }
  return {
    open() {
      close()
      snapshot.value = context.getSnapshot()
      ;(app = createApp(PvWeatherView).provide(HOST, host).provide(SNAPSHOT, snapshot).provide(PV_WEATHER_STORE, store)).mount(target(id))
    },
    /** A panel refresh: the app always receives a new snapshot, even with unchanged values. */
    update() {
      snapshot.value = context.getSnapshot()
      triggerRef(snapshot)
    },
    close,
  }
}

/** Status band and notices; the badge goes to #nav-badge-host and the notices page to #notices-view. */
export function mountStatus(context: TestContext & { getBrowserNotices?: () => readonly Notice[] }, id: string) {
  const host = hostOf(context)
  const snapshot = shallowRef(context.getSnapshot() as unknown as StatusSnapshot)
  const route = shallowRef('overview')
  const browserNotices = shallowRef<readonly Notice[]>([])
  const store = createStatusStore(host, snapshot, route, browserNotices)
  const Root: Component = defineComponent(() => () => [
    h(StatusArea),
    h('nav', h(NavBadge)),
    h('div', { id: 'notices-view' }, route.value === 'notices' ? [h(NoticesView)] : []),
  ])
  let app: App | null = null
  return {
    store,
    show(next: string) {
      snapshot.value = context.getSnapshot() as unknown as StatusSnapshot
      browserNotices.value = context.getBrowserNotices?.() ?? []
      route.value = next
      if (!app) (app = createApp(Root).provide(STATUS_STORE, store)).mount(target(id))
    },
  }
}

type Vehicles = { vehicles?: readonly { id?: string; name?: string }[]; features?: Record<string, boolean> }

function usageOf(context: TestContext, storage?: Preferences) {
  const read = () => context.getSnapshot() as unknown as Vehicles & PanelSnapshot
  return createUsageStore(hostOf(context), {
    zone: () => read().zone,
    vehicles: () => (read().features?.['car'] === false ? [] : read().vehicles ?? []),
    features: () => read().features,
  }, storage)
}

/** A report page; show() opens another report or follows a panel refresh (new tick). */
export function mountUsage(context: TestContext, id: string, storage?: Preferences) {
  const store = usageOf(context, storage)
  const key = shallowRef('house')
  const tick = shallowRef(context.clock.now)
  const Root: Component = defineComponent(() => () => h(UsageView, { reportKey: key.value, tick: tick.value, key: key.value }))
  let app: App | null = null
  return {
    store,
    show(report: string) {
      key.value = report
      tick.value = context.clock.now
      if (!app) (app = createApp(Root).provide(USAGE_STORE, store)).mount(target(id))
    },
  }
}

/** Today's tiles of the overview. */
export function mountDayBalance(context: TestContext, id: string, report: Report | null) {
  const store = usageOf(context)
  createApp(DayBalance, { report }).provide(USAGE_STORE, store).mount(target(id))
}

/** The settings page with its own toast list; refresh() follows a new backend snapshot. */
export function mountSettings(context: TestContext, id: string, options: { historyStatus?: string } = {}) {
  const host = hostOf(context)
  const snapshot = shallowRef(context.getSnapshot() as unknown as SettingsSnapshot)
  const toasts: string[] = []
  const costsChanged = { count: 0 }
  const store = createSettingsStore(host, snapshot, { toast: message => toasts.push(message), costsChanged: () => costsChanged.count++ })
  const Root: Component = defineComponent(() => () => h(SettingsView, { snapshot: snapshot.value, historyStatus: options.historyStatus }))
  const app = createApp(Root).provide(SETTINGS_STORE, store)
  app.mount(target(id))
  return {
    store,
    toasts,
    costsChanged,
    refresh() {
      snapshot.value = context.getSnapshot() as unknown as SettingsSnapshot
    },
    unmount: () => app.unmount(),
  }
}
