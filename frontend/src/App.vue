<script setup lang="ts">
import { computed, onBeforeUnmount, onErrorCaptured, onMounted, provide, watch, type ShallowRef } from 'vue'
import AppHeader from '@/components/app/AppHeader.vue'
import StartupFailure from '@/components/app/StartupFailure.vue'
import DayBalance from '@/components/overview/DayBalance.vue'
import StatusArea from '@/components/status/StatusArea.vue'
import { HOST, SNAPSHOT } from '@/composables/useHost'
import { consumerEnabled, resolveRoute, useHash } from '@/router'
import { APP_STORE, type AppStore } from '@/stores/app'
import { CAR_STORE, createCarStore } from '@/stores/car'
import { createDeviceStore, DEVICE_STORE, parseDeviceRoute } from '@/stores/device'
import { createOverviewStore, OVERVIEW_STORE } from '@/stores/overview'
import { createPvWeatherStore, PV_WEATHER_STORE } from '@/stores/pvWeather'
import { createSettingsStore, SETTINGS_STORE, type SettingsSnapshot } from '@/stores/settings'
import { createStatusStore, STATUS_STORE } from '@/stores/status'
import { createUsageStore, USAGE_STORE, type Preferences } from '@/stores/usage'
import type { DeviceSnapshot } from '@/types/device'
import type { OverviewSnapshot } from '@/types/overview'
import type { StatusSnapshot } from '@/types/status'
import type { Report } from '@/types/usage'
import { buildVersion } from '@/utils/reload'
import DevicePageView from '@/views/DevicePageView.vue'
import NoticesView from '@/views/NoticesView.vue'
import OverviewView from '@/views/OverviewView.vue'
import PvWeatherView from '@/views/PvWeatherView.vue'
import SettingsView from '@/views/SettingsView.vue'
import UsageView from '@/views/UsageView.vue'

/**
 * The panel: title bar, status band and the page of the address hash. Every page reads the
 * snapshot the app store refreshes; feature stores only add their presentation.
 */
const props = defineProps<{ app: AppStore; storage?: Preferences }>()
const app = props.app
const { host, snapshot, history, now, stage, failure, toastText } = app
const hash = useHash()
const route = computed(() => resolveRoute(hash.value, snapshot.value))
const page = computed(() => route.value.page)
const ready = computed(() => stage.value === 'ready' && !failure.value)
const version = buildVersion(window.location.href)
const logo = `./logo.svg${version ? `?v=${encodeURIComponent(version)}` : ''}#mark`

const status = createStatusStore(host, snapshot as unknown as ShallowRef<StatusSnapshot>, computed(() => route.value.key), app.browserNotices)
const overview = createOverviewStore(host, snapshot as unknown as ShallowRef<OverviewSnapshot>, now, logo)
const device = createDeviceStore(host, snapshot as unknown as ShallowRef<DeviceSnapshot>, history, now)
const car = createCarStore(device)
const usage = createUsageStore(host, {
  zone: () => snapshot.value.zone,
  vehicles: () => (consumerEnabled(snapshot.value, 'car') ? snapshot.value.vehicles ?? [] : []),
  features: () => snapshot.value.features,
}, props.storage)
const settings = createSettingsStore(host, snapshot as unknown as ShallowRef<SettingsSnapshot>, { toast: app.toast, costsChanged: usage.invalidate })

provide(APP_STORE, app)
provide(HOST, host)
provide(SNAPSHOT, snapshot)
provide(STATUS_STORE, status)
provide(OVERVIEW_STORE, overview)
provide(DEVICE_STORE, device)
provide(CAR_STORE, car)
provide(PV_WEATHER_STORE, createPvWeatherStore(host, snapshot))
provide(USAGE_STORE, usage)
provide(SETTINGS_STORE, settings)

watch(route, (next, previous) => {
  // replace keeps the back button on the previous page; the hash change resolves again.
  if (next.redirect) {
    window.location.replace(`#${next.redirect}`)
    return
  }
  if (next.page.name === 'device') {
    const deviceRoute = parseDeviceRoute(next.key)
    if (deviceRoute) device.route.value = deviceRoute
  }
  if (next.key === previous?.key) return
  // A new visit may retry a page that failed to render; the status band stays in view.
  app.viewFailure.value = null
  if (previous) window.scrollTo(0, 0)
  else requestAnimationFrame(() => window.scrollTo(0, 0))
}, { immediate: true })

// "To the charging plan" links outside the car page: the car page scrolls to its plan once shown.
const planLink = (event: MouseEvent) => {
  if ((event.target as Element | null)?.closest?.('.plan-link[href="#car"]')) car.scrollToPlan.value = true
}

// A device or PV page that fails to render becomes a browser notice; the rest of the panel stays usable.
onErrorCaptured(error => {
  const name = page.value.name
  if (name === 'device' || name === 'pv') {
    console.error('EOS UI view failed', error instanceof Error ? error.name : 'Error')
    app.viewFailure.value = name
  } else app.fail('view', error)
  return false
})

onMounted(() => {
  document.addEventListener('click', planLink)
  void app.start()
})
onBeforeUnmount(() => {
  document.removeEventListener('click', planLink)
  app.stop()
})
</script>

<template>
  <div class="energy-app">
    <AppHeader v-if="ready" :section="route.section" :car="consumerEnabled(snapshot, 'car')" :logo="logo" :t="host.t" />
    <main>
      <StartupFailure v-if="failure" :failure="failure" :t="host.t" />
      <template v-else-if="ready">
        <StatusArea />
        <section v-if="page.name === 'overview'" id="overview">
          <OverviewView />
          <DayBalance :report="snapshot.accounting as Report | null | undefined" />
        </section>
        <section v-else-if="page.name === 'device'" id="detail">
          <DevicePageView v-if="app.viewFailure.value !== 'device'" />
        </section>
        <section v-else-if="page.name === 'pv'" id="pv">
          <div class="d-head"><a class="back" href="#overview">{{ host.t('nav.back') }}</a></div>
          <div id="pv-view"><PvWeatherView v-if="app.viewFailure.value !== 'pv'" /></div>
        </section>
        <UsageView v-else-if="page.name === 'usage'" :key="page.report" :report-key="page.report" :tick="now" />
        <section v-else-if="page.name === 'notices'" id="notices">
          <div id="notices-view"><NoticesView /></div>
        </section>
        <SettingsView v-else-if="page.name === 'settings'" :snapshot="snapshot" :history-status="(history as { status?: string }).status" />
      </template>
    </main>
  </div>
  <div v-if="toastText" id="toast" class="toast" role="status">{{ toastText }}</div>
</template>
