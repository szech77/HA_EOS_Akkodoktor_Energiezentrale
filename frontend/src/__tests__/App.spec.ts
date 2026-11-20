import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createApp, type App as VueApp } from 'vue'
import App from '@/App.vue'
import { resolveRoute } from '@/router'
import { createAppStore } from '@/stores/app'
import { history, snapshot } from '@/test/fixtures/device'
import { flush, languagePack } from '@/test/host'
import { createBridge, RequestError, type BridgeWindow } from '@/utils/bridge'

const ORIGIN = 'https://ha.example'
type Answer = { result?: unknown; error?: string; reason?: string; fields?: string[] }

/** The HA panel (panel.js) around the iframe: it answers each request of the bridge. */
function panel(answer: (action: string, values: Record<string, unknown>) => Answer | Promise<Answer> | undefined) {
  let listener: ((event: MessageEvent) => void) | null = null
  const requests: { action: string; values: Record<string, unknown>; client: string }[] = []
  const parent = {
    postMessage(message: { channel: string; id: number; client: string; action: string; values: Record<string, unknown> }, origin: string) {
      expect(origin).toBe(ORIGIN)
      expect(message.channel).toBe('eos-energy-request')
      requests.push({ action: message.action, values: message.values, client: message.client })
      void Promise.resolve(answer(message.action, message.values)).then(reply => {
        if (reply) listener?.({ source: parent, origin: ORIGIN, data: { channel: 'eos-energy-response', id: message.id, client: message.client, ...reply } } as unknown as MessageEvent)
      })
    },
  }
  const view: BridgeWindow & { location: { origin: string; href: string } } = {
    parent,
    location: { origin: ORIGIN, href: `${ORIGIN}/eos-energiezentrale-static/index.html?v=build1&lang=de` },
    addEventListener: (_type, handler) => { listener = handler },
  }
  return { view, requests, send: (event: object) => listener?.(event as MessageEvent) }
}

const pack = languagePack('de')
const de = pack.messages

describe('bridge', () => {
  it('accepts answers only from the parent panel of the same origin, addressed to this client', async () => {
    const outer = panel(() => undefined)
    const bridge = createBridge(outer.view, (code, action) => `${action}:${code}`, 'client-1')
    const pending = bridge.request('snapshot')
    const reply = (event: object) => outer.send({ source: outer.view.parent, origin: ORIGIN, ...event })
    reply({ source: {}, data: { channel: 'eos-energy-response', id: 1, client: 'client-1', result: 'foreign' } })
    reply({ origin: 'https://foreign.example', data: { channel: 'eos-energy-response', id: 1, client: 'client-1', result: 'foreign' } })
    reply({ data: { channel: 'eos-energy-response', id: 1, client: 'other', result: 'other client' } })
    reply({ data: { channel: 'eos-energy-response', id: 1, client: 'client-1', result: 'mine' } })
    await expect(pending).resolves.toBe('mine')
  })

  it('turns backend errors into allow-listed codes with field hints, never raw text', async () => {
    const outer = panel(() => ({ error: '<script>', reason: 'out_of_range', fields: ['battery_min_soc', 'Bad Field'] }))
    const bridge = createBridge(outer.view, (code, action) => `${action}:${code}`)
    const error = await bridge.request('settings').catch(failure => failure as RequestError)
    expect(error).toBeInstanceOf(RequestError)
    expect(error).toMatchObject({ code: 'request_failed', action: 'settings', reason: 'out_of_range', fields: ['battery_min_soc'], message: 'settings:request_failed' })
  })

  it('times out after 30 seconds and refuses to run outside the HA panel', async () => {
    vi.useFakeTimers()
    try {
      const bridge = createBridge(panel(() => undefined).view, code => code)
      const pending = bridge.request('snapshot').catch(failure => (failure as RequestError).code)
      await vi.advanceTimersByTimeAsync(30_000)
      await expect(pending).resolves.toBe('timeout')
    } finally {
      vi.useRealTimers()
    }
    const alone = { location: { origin: ORIGIN }, addEventListener() {} } as unknown as BridgeWindow & { parent: unknown }
    ;(alone as { parent: unknown }).parent = alone
    await expect(createBridge(alone, code => code).request('snapshot')).rejects.toMatchObject({ code: 'ingress_only' })
  })
})

describe('routes', () => {
  const context = { features: { car: true, heat: false }, vehicles: [{ id: 'a b' }, { id: 'c' }] }

  it('resolve pages and fall back to the overview for unknown or unavailable ones', () => {
    expect(resolveRoute('#battery', context)).toMatchObject({ key: 'battery', page: { name: 'device', device: 'battery' }, section: 'overview' })
    expect(resolveRoute('#car/a%20b', context)).toMatchObject({ key: 'car/a%20b', page: { name: 'device', device: 'car' }, section: 'car' })
    // Reports belong to the overview section, as before; the car section is the car pages.
    expect(resolveRoute('#usage/car/c', context)).toMatchObject({ page: { name: 'usage', report: 'car/c' }, section: 'overview' })
    expect(resolveRoute('#settings', context)).toMatchObject({ page: { name: 'settings' }, section: 'settings' })
    for (const hash of ['#heat', '#usage/heat', '#car/unknown', '#car/%E0%A4%A', '#usage/invalid', '#nothing', '']) {
      expect(resolveRoute(hash, context).page).toEqual({ name: 'overview' })
    }
    expect(resolveRoute('#car', { ...context, features: { car: false } }).page).toEqual({ name: 'overview' })
  })

  it('show the only vehicle for the car page, so menu and energy flow open the same page', () => {
    expect(resolveRoute('#car', { vehicles: [{ id: 'one' }] })).toMatchObject({ key: 'car/one', redirect: 'car/one', section: 'car' })
    expect(resolveRoute('#car', context)).toMatchObject({ key: 'car', page: { name: 'device', device: 'car' } })
  })
})

describe('panel app', () => {
  let target: HTMLElement
  let mounted: VueApp | null = null

  beforeEach(() => {
    target = document.createElement('div')
    document.body.append(target)
    vi.spyOn(window, 'scrollTo').mockImplementation(() => undefined)
    window.location.hash = ''
  })
  afterEach(() => {
    vi.useRealTimers()
    mounted?.unmount()
    mounted = null
    target.remove()
  })

  function start(answer: (action: string, values: Record<string, unknown>) => Answer | undefined) {
    const outer = panel(answer)
    const store = createAppStore({ view: outer.view, document, navigatorLanguage: 'de-DE', clientId: 'test' })
    mounted = createApp(App, { app: store })
    mounted.mount(target)
    const text = (selector: string) => target.querySelector(selector)?.textContent?.replace(/\s+/g, ' ').trim() ?? ''
    return { store, requests: outer.requests, text }
  }
  const backend = (overrides: Record<string, Answer> = {}) => (action: string): Answer =>
    overrides[action] ?? (action === 'language' ? { result: pack } : action === 'snapshot' ? { result: snapshot() } : action === 'history' ? { result: history() } : { result: {} })

  it('waits for the integration, then shows the overview in the HA language with its navigation', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'setInterval'] })
    try {
      let attempts = 0
      const { requests, text } = start(action => {
        if (action === 'language' && ++attempts < 3) return { error: 'not_ready' }
        return backend()(action)
      })
      await vi.advanceTimersByTimeAsync(2_000)
      expect(attempts).toBe(3)
      expect(requests.map(item => item.action)).toEqual(expect.arrayContaining(['snapshot', 'history']))
      expect(document.documentElement.lang).toBe('de-DE')
      expect(text('header nav')).toContain(de['nav.overview'])
      expect(target.querySelector('header [data-route="overview"]')?.getAttribute('aria-current')).toBe('page')
      expect(target.querySelector('#overview')).not.toBeNull()
      // The snapshot follows every five seconds, the history every minute.
      const before = requests.filter(item => item.action === 'snapshot').length
      await vi.advanceTimersByTimeAsync(5_000)
      expect(requests.filter(item => item.action === 'snapshot').length).toBe(before + 1)
    } finally {
      vi.useRealTimers()
    }
  })

  it('names a failed start with its stage and code, without the backend text', async () => {
    const { text } = start(action => (action === 'language' ? { error: 'unauthorized' } : undefined))
    await flush()
    expect(text('.startup-notice')).toBe(`${de['startup.language']}. ${de['action.language']}: ${de['error.unauthorized']}`)
    expect(text('.startup-details code')).toBe('language · unauthorized')
    expect(target.querySelector('header')).toBeNull()
    mounted?.unmount()
    const invalid = start(action => (action === 'language' ? { result: { locale: 'de-DE' } } : undefined))
    await flush()
    expect(invalid.text('.startup-notice')).toContain(de['error.language_invalid'])
  })

  it('shows a lost connection as a browser notice until the next snapshot arrives', async () => {
    let online = false
    const { store, text } = start(action => (action === 'snapshot' && !online ? { error: 'timeout' } : backend()(action)))
    await flush()
    expect(store.connectionFailure.value).toBe(true)
    expect(text('#status-view')).toContain(de['notice.connection'])
    online = true
    await store.refresh()
    await flush()
    expect(text('#status-view')).not.toContain(de['notice.connection'])
  })

  it('follows the address to the settings and back to the overview for unknown pages', async () => {
    start(backend())
    await flush()
    window.location.hash = '#settings'
    window.dispatchEvent(new HashChangeEvent('hashchange'))
    await flush()
    expect(target.querySelector('#settings')).not.toBeNull()
    expect(target.querySelector('header [data-route="settings"]')?.getAttribute('aria-current')).toBe('page')
    window.location.hash = '#unknown'
    window.dispatchEvent(new HashChangeEvent('hashchange'))
    await flush()
    expect(target.querySelector('#overview')).not.toBeNull()
  })
})
