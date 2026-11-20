/**
 * The panel application: connection to Home Assistant, language pack, periodic refreshes of the
 * snapshot and history, and the browser-side notices. All feature stores read the refs held here.
 */
import { computed, inject, shallowRef, type ComputedRef, type InjectionKey, type ShallowRef } from 'vue'
import type { PanelHistory } from '@/types/device'
import type { Host, PanelSnapshot } from '@/types/host'
import type { Notice } from '@/types/status'
import { createBridge, RequestError, type BridgeWindow } from '@/utils/bridge'
import { STARTUP_MESSAGES } from '@/utils/startupMessages'

export const SNAPSHOT_INTERVAL_MS = 5_000
export const HISTORY_INTERVAL_MS = 60_000
const LANGUAGE_ATTEMPTS = 4
const TOAST_MS = 3_500

/** The snapshot as the app itself reads it; feature stores type their own part of it. */
export type AppSnapshot = PanelSnapshot & {
  readonly live?: PanelSnapshot['live'] & { readonly time?: string }
  readonly features?: Readonly<Record<string, boolean>>
  readonly vehicles?: readonly { readonly id?: string; readonly name?: string }[]
  readonly settings?: Readonly<Record<string, unknown>>
  readonly [key: string]: unknown
}

export interface Language {
  readonly locale: string
  readonly messages: Readonly<Record<string, string>>
}

export type Stage = 'language' | 'view' | 'ready'

/** A failure that keeps the panel from being shown, with a technical detail without raw messages. */
export interface StartupFailure {
  readonly stage: 'language' | 'view'
  readonly message: string
  readonly detail: string
}

export interface AppStore {
  readonly host: Host
  readonly language: ShallowRef<Language>
  readonly stage: ShallowRef<Stage>
  readonly failure: ShallowRef<StartupFailure | null>
  readonly snapshot: ShallowRef<AppSnapshot>
  readonly history: ShallowRef<PanelHistory>
  /** Time of the shown snapshot: "now" of charts and plans. */
  readonly now: ShallowRef<number>
  /** The last snapshot request failed; the panel keeps showing the previous values. */
  readonly connectionFailure: ShallowRef<boolean>
  /** Page whose view failed to render (browser notice until the page is opened again). */
  readonly viewFailure: ShallowRef<'device' | 'pv' | null>
  readonly browserNotices: ComputedRef<readonly Notice[]>
  readonly toastText: ShallowRef<string>
  toast(message: string): void
  start(): Promise<void>
  stop(): void
  refresh(): Promise<void>
  refreshHistory(): Promise<void>
  /** Show an unexpected error as a startup failure. */
  fail(stage: 'language' | 'view', error: unknown): void
}

export const APP_STORE: InjectionKey<AppStore> = Symbol('eos-app')

export interface AppEnvironment {
  readonly view: BridgeWindow & { readonly location: { readonly origin: string; readonly href: string } }
  readonly document?: Pick<Document, 'documentElement' | 'title'>
  readonly navigatorLanguage?: string
  readonly clientId?: string
}

const startupCode = (href: string, fallback: string): 'de' | 'en' =>
  (new URL(href).searchParams.get('lang') || fallback || 'en').startsWith('de') ? 'de' : 'en'

const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms))

export function createAppStore(environment: AppEnvironment): AppStore {
  const code = startupCode(environment.view.location.href, environment.navigatorLanguage ?? globalThis.navigator?.language ?? 'en')
  const startup = STARTUP_MESSAGES[code]
  const language = shallowRef<Language>({ locale: code === 'de' ? 'de-DE' : 'en-GB', messages: startup })
  // Same empty state as before the first answer of the backend: pages render without values.
  const snapshot = shallowRef<AppSnapshot>({ live: {}, settings: {}, errors: {}, plan: {}, forecast: [], zone: 'Europe/Berlin' })
  const history = shallowRef<PanelHistory>({ local: [], influx: [] })
  const now = shallowRef(Date.now())
  const connectionFailure = shallowRef(false)
  const viewFailure = shallowRef<'device' | 'pv' | null>(null)
  const stage = shallowRef<Stage>('language')
  const failure = shallowRef<StartupFailure | null>(null)
  const toastText = shallowRef('')
  const formats = new Map<string, Intl.NumberFormat>()
  let toastTimer: ReturnType<typeof setTimeout> | undefined
  let timers: ReturnType<typeof setInterval>[] = []
  let refreshing = false
  let historyRefreshing = false

  const t: Host['t'] = (key, values = {}) => {
    const context: Record<string, string | number> = { vehicle: snapshot.value.vehicle_name ?? 'E-Auto', ...values }
    return (language.value.messages[key] ?? key).replace(/\{(\w+)\}/g, (token, name: string) => (Object.hasOwn(context, name) ? String(context[name]) : token))
  }
  const bridge = createBridge(
    environment.view,
    (failed, action) => `${t(`action.${action}`)}: ${language.value.messages[`error.${failed}`] ?? t('error.request')}`,
    environment.clientId,
  )
  const decimal: Host['decimal'] = (value, digits = 1) => {
    const key = `${language.value.locale}/${digits}`
    let format = formats.get(key)
    if (!format) formats.set(key, (format = new Intl.NumberFormat(language.value.locale, { maximumFractionDigits: digits })))
    return format.format(value)
  }
  const snapshotTime = () => Date.parse(snapshot.value.live?.time ?? '') || Date.now()

  async function refresh() {
    if (refreshing) return
    refreshing = true
    try {
      snapshot.value = await bridge.request<AppSnapshot>('snapshot')
      now.value = snapshotTime()
      connectionFailure.value = false
    } catch {
      // Shown as a browser notice; the authenticated bridge already reported the request.
      connectionFailure.value = true
    } finally {
      refreshing = false
    }
  }

  async function refreshHistory() {
    if (historyRefreshing) return
    historyRefreshing = true
    try {
      history.value = await bridge.request<PanelHistory>('history')
    } catch {
      // History failures appear in the backend notices; the charts keep the previous data.
    } finally {
      historyRefreshing = false
    }
  }

  const host: Host = {
    request: bridge.request,
    t,
    decimal,
    locale: () => language.value.locale,
    now: () => now.value,
    lookup: key => language.value.messages[key],
    refresh,
  }

  function fail(failedStage: 'language' | 'view', error: unknown) {
    const known = error instanceof RequestError
    const name = known ? error.code : error instanceof Error ? error.name : 'Error'
    // Only allow-listed codes and error names leave the browser console; raw messages stay short.
    console.error(`EOS UI failed during ${failedStage}`, name)
    const raw = !known && error instanceof Error ? error.message.slice(0, 200) : ''
    failure.value = {
      stage: failedStage,
      message: `${t(`startup.${failedStage}`)}. ${known ? error.message : t('startup.unexpected')}`,
      detail: [failedStage, name, known ? error.asset ?? '' : '', raw].filter(Boolean).join(' · '),
    }
  }

  async function loadLanguage(): Promise<Language> {
    for (let attempt = 0; ; attempt++) {
      try {
        const loaded = await bridge.request<{ locale?: unknown; messages?: unknown }>('language')
        if (!loaded || typeof loaded.locale !== 'string' || !loaded.messages || typeof loaded.messages !== 'object') throw bridge.error('language_invalid', 'language')
        return { locale: loaded.locale, messages: { ...startup, ...(loaded.messages as Record<string, string>) } }
      } catch (error) {
        const retry = error instanceof RequestError && ['not_ready', 'bridge_not_ready'].includes(error.code)
        if (!retry || attempt === LANGUAGE_ATTEMPTS - 1) throw error
        await sleep(500 * (attempt + 1))
      }
    }
  }

  return {
    host,
    language,
    stage,
    failure,
    snapshot,
    history,
    now,
    connectionFailure,
    viewFailure,
    // Browser-side failures stay in the browser; they are shown, never reported to the backend.
    browserNotices: computed(() => [
      ...(connectionFailure.value ? [{ severity: 'warning', message: 'notice.connection', browser: true } as const] : []),
      ...(viewFailure.value === 'pv' ? [{ severity: 'warning', message: 'forecast.open_failed', browser: true } as const] : []),
      ...(viewFailure.value === 'device' ? [{ severity: 'warning', message: 'device.open_failed', browser: true } as const] : []),
    ]),
    toastText,
    toast(message) {
      toastText.value = message
      clearTimeout(toastTimer)
      toastTimer = setTimeout(() => (toastText.value = ''), TOAST_MS)
    },
    async start() {
      try {
        language.value = await loadLanguage()
      } catch (error) {
        fail('language', error)
        return
      }
      if (environment.document) {
        environment.document.documentElement.lang = language.value.locale
        environment.document.title = t('app.title')
      }
      stage.value = 'ready'
      await Promise.all([refresh(), refreshHistory()])
      timers = [setInterval(() => void refresh(), SNAPSHOT_INTERVAL_MS), setInterval(() => void refreshHistory(), HISTORY_INTERVAL_MS)]
    },
    stop() {
      timers.forEach(clearInterval)
      timers = []
      clearTimeout(toastTimer)
    },
    refresh,
    refreshHistory,
    fail,
  }
}

export function useAppStore(): AppStore {
  const store = inject(APP_STORE)
  if (!store) throw new Error('App store is not provided')
  return store
}
