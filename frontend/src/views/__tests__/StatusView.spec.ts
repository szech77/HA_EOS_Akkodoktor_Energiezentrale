import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createStatusController } from '@/bridge/statusController'
import { backend } from '@/test/backend'
import { flush, languagePack, testContext } from '@/test/host'
import type { BackendRequest, PanelSnapshot } from '@/types/host'
import type { Notice } from '@/types/status'

const NOW = Date.parse('2026-11-08T12:00:00Z')
let nodes: HTMLElement[] = []

/** New mount points: each controller mounts its own app. */
function reset() {
  nodes.forEach(node => node.remove())
  nodes = ['status-view', 'nav-badge', 'notices-view'].map(id => {
    const node = document.createElement('div')
    node.id = id
    document.body.append(node)
    return node
  })
}
beforeEach(reset)
afterEach(() => nodes.forEach(node => node.remove()))

function open(snapshot: object, options: { route?: string; code?: 'de' | 'en'; request?: BackendRequest; browser?: Notice[] } = {}) {
  const request = options.request ?? (vi.fn(async () => ({})) as unknown as BackendRequest)
  const refresh = vi.fn(async () => undefined)
  const context = { ...testContext({ code: options.code ?? 'de', snapshot: snapshot as PanelSnapshot, request, now: NOW, refresh }), getBrowserNotices: () => options.browser ?? [] }
  const view = createStatusController(context)
  view.show(options.route ?? 'overview')
  const $ = <T extends Element = HTMLElement>(selector: string) => document.querySelector<T>(selector)
  const text = (selector: string) => $(selector)?.textContent?.replace(/\s+/g, ' ').trim() ?? ''
  const messages = languagePack(options.code ?? 'de').messages
  return { view, request, refresh, $, text, messages, context }
}

const settings = { schedule: [] }
const view = (data: object, now = NOW) => ({ ...backend<object>('view', data, { now }), settings, zone: 'Europe/Berlin' })

describe('status band', () => {
  it('shows backup power as neutral information and sorts independent errors first, in both languages', async () => {
    for (const code of ['de', 'en'] as const) {
      const state = { armed: true, control_paused: true, power_supply: { state: 'backup', sample: '2026-11-08T12:00:00Z' }, source_configuration: { unavailable: ['grid', 'house_total'] } }
      let page = open(view(state), { code })
      await flush()
      expect(page.$('#status-band')?.className).toContain('tone-info')
      expect(page.text('#status-band h2')).toBe(page.messages['control.backup'])
      expect(page.text('.notices')).toContain(page.messages['notice.backup_power_paused'])
      reset()
      page = open(view({ ...state, errors: { release: 'TimeoutError' } }), { code, route: 'notices' })
      await flush()
      const cards = [...document.querySelectorAll('#notices-view .notice-card')]
      expect(cards[0]?.className).toContain('tone-crit')
      expect(cards[0]?.getAttribute('role')).toBe('alert')
      expect(cards[0]?.textContent).toContain(page.messages['notice.release'])
      expect(cards[0]?.textContent).toContain('system/release')
      reset()
    }
  })

  it('shows active control without notices and names the next battery change', async () => {
    const { $, text, messages } = open({ ...view({ armed: true }), next_mode: { battery: { time: '2026-11-08T14:00:00Z', mode: 'SELF_CONSUMPTION' } } })
    await flush()
    expect($('#status-band')?.className).toContain('tone-ok')
    expect(text('#status-band h2')).toBe(messages['control.active'])
    expect(text('#status-band p')).toContain('15:00')
    expect(text('#status-band p')).toContain('Eigenverbrauch')
    expect($('.notices')).toBeNull()
    expect($('#nav-badge .badge')).toBeNull()
  })

  it('keeps an EOS calculation in the text, not in the headline', async () => {
    for (const state of ['calculating', 'updating']) {
      const { text, messages } = open({ control_status: 'active', armed: true, settings, eos_run: { state, elapsed_s: 240 } })
      await flush()
      expect(text('#status-band h2')).toBe(messages['control.active'])
      expect(text('#status-band p')).toContain(messages[`eos.run_${state}`]!.replace('{seconds}', '240'))
      reset()
    }
  })

  it('looks like active control with the last valid EOS plan and follows only the backend state', async () => {
    const title = async (snapshot: object) => {
      const page = open({ settings, ...snapshot })
      await flush()
      const result = [page.text('#status-band h2'), page.$('#status-band')?.className ?? '']
      reset()
      return result
    }
    const { messages } = open({})
    reset()
    for (const name of ['planning_vehicle', 'syncing_vehicle', 'waiting', 'read_only', 'active', 'backup', 'power_supply_waiting']) {
      expect((await title({ control_status: name, armed: name !== 'read_only' }))[0]).toBe(messages[`control.${name}`])
    }
    expect(await title({ control_status: 'cached_eos', armed: true })).toEqual([messages['control.active'], expect.stringContaining('tone-ok')])
    expect((await title({ control_status: 'unexpected' }))[0]).toBe(messages['control.read_only'])
  })

  it('confirms taking over inline, names the devices and sends an explicit boolean', async () => {
    const { $, text, request, refresh, messages } = open({ control_status: 'read_only', armed: false, settings, features: { car: false } })
    await flush()
    expect($('[data-confirm]')).toBeNull()
    $<HTMLButtonElement>('#status-band .status-actions .btn')?.click()
    await flush()
    expect(text('.status-confirm')).toContain(messages['control.take_battery'])
    expect(text('.status-confirm')).not.toContain(messages['control.take_devices'])
    expect($<HTMLButtonElement>('#status-band > .status-actions .btn')?.disabled).toBe(true)
    expect(document.activeElement?.textContent).toBe(messages['control.take_confirm'])
    $<HTMLButtonElement>('.status-confirm .btn.primary')?.click()
    await flush()
    expect(request).toHaveBeenCalledWith('control', { enabled: true })
    expect(refresh).toHaveBeenCalledTimes(1)
    expect(text('.status-result')).toBe(messages['control.taken'])
    expect($('.status-confirm')).toBeNull()
  })

  it('names only the controlled devices on release and can be cancelled', async () => {
    const areas = (battery: object, vehicle: object) => ({ battery: { available: true, enabled: false, release_pending: false, ...battery }, vehicle: { available: true, enabled: false, release_pending: false, ...vehicle } })
    const { $, text, request, messages } = open({ control_status: 'active', armed: true, settings, control: areas({ enabled: true }, {}) })
    await flush()
    $<HTMLButtonElement>('#status-band .status-actions .btn')?.click()
    await flush()
    expect(text('.status-confirm')).toContain(messages['control.release_battery'])
    expect(text('.status-confirm')).not.toContain(messages['control.release_wallbox'])
    expect($('.status-confirm .btn.danger')).not.toBeNull()
    $<HTMLButtonElement>('.status-confirm .btn.ghost')?.click()
    await flush()
    expect($('.status-confirm')).toBeNull()
    expect(request).not.toHaveBeenCalled()
  })

  it('says which single area is controlled and offers release while a release is pending', async () => {
    const areas = { battery: { available: true, enabled: false, release_pending: false }, vehicle: { available: true, enabled: true, release_pending: false } }
    let page = open({ control_status: 'active', armed: true, settings, control: areas, next_mode: { battery: { time: '2026-11-08T14:00:00Z', mode: 'SELF_CONSUMPTION' } } })
    await flush()
    expect(page.text('#status-band p')).toBe(page.messages['status_band.active_vehicle'])
    reset()
    page = open({ control_status: 'read_only', armed: false, release_pending: true, settings })
    await flush()
    expect(page.$('#status-band')?.className).toContain('tone-warn')
    expect(page.text('#status-band p')).toBe(page.messages['status_band.release_pending'])
    expect(page.text('#status-band .label-long')).toBe(page.messages['control.release'])
  })

  it('cannot be operated before the backend sent the settings, nor while a request runs', async () => {
    let resolve: (value: unknown) => void = () => undefined
    const request = vi.fn(() => new Promise(done => { resolve = done })) as unknown as BackendRequest
    let page = open({ control_status: 'read_only', armed: false })
    await flush()
    expect(page.$<HTMLButtonElement>('#status-band .status-actions .btn')?.disabled).toBe(true)
    reset()
    page = open({ control_status: 'read_only', armed: false, settings }, { request })
    await flush()
    page.$<HTMLButtonElement>('#status-band .status-actions .btn')?.click()
    await flush()
    page.$<HTMLButtonElement>('.status-confirm .btn.primary')?.click()
    await flush()
    expect(page.$<HTMLButtonElement>('.status-confirm .btn.primary')?.disabled).toBe(true)
    resolve({})
    await flush()
    expect(page.$('.status-confirm')).toBeNull()
  })
})

describe('notices', () => {
  const notices: Notice[] = [
    { id: 'system/eos', code: 'eos', severity: 'warning', message: 'notice.eos', since: '2026-11-08T11:00:00Z' },
    { id: 'system/release', code: 'release', severity: 'error', message: 'notice.release' },
    { id: 'system/backup', code: 'backup_power_active', severity: 'info', message: 'notice.backup_power_active' },
  ]

  it('show the two most important as compact cards, the pill and the count in the navigation', async () => {
    const { $, text, messages } = open({ control_status: 'active', armed: true, settings, notices })
    await flush()
    const cards = [...document.querySelectorAll('#status-view .notices .notice-card')]
    expect(cards).toHaveLength(2)
    expect(cards[0]?.textContent).toContain(messages['notice.release'])
    expect(cards[0]?.querySelector('a')?.getAttribute('href')).toBe('#notices')
    expect(cards[0]?.querySelector('small')).toBeNull()
    expect($('.notice-pill')?.className).toContain('tone-crit')
    expect(text('.notice-pill .txt')).toContain(messages['notice_card.more']!.replace('{count}', '2'))
    expect(text('#nav-badge .badge')).toBe('3')
    expect($('#nav-badge .badge')?.className).toContain('tone-crit')
  })

  it('list every notice with id, age and the page that helps on the notices page', async () => {
    const { $, text, messages } = open({ control_status: 'active', armed: true, settings, notices,
      resolved_notices: [{ id: 'system/eos', code: 'eos', at: '2026-11-08T11:05:00Z', since: '2026-11-08T11:02:00Z' }] }, { route: 'notices' })
    await flush()
    expect($('#status-view .notices')).toBeNull()
    expect($('.notice-pill')).toBeNull()
    expect(text('#notices-view .page-top .tag')).toBe(messages['notice_card.open_count']!.replace('{count}', '3'))
    const cards = [...document.querySelectorAll('#notices-view .notice-card')]
    expect(cards.map(card => card.className.split(' ')[1])).toEqual(['tone-crit', 'tone-warn', 'tone-info'])
    expect(cards[1]?.textContent).toContain('system/eos')
    expect(cards[1]?.querySelector('a')?.getAttribute('href')).toBe('#settings')
    expect(cards[0]?.querySelector('a')).toBeNull()
    expect(text('#notices-view .list .row')).toContain(messages['notice_card.duration']!.replace('{minutes}', '3'))
  })

  it('keep browser-side problems marked as such', async () => {
    const { text, messages } = open({ control_status: 'active', armed: true, settings }, { route: 'notices', browser: [{ severity: 'warning', message: 'notice.connection', browser: true }] })
    await flush()
    expect(text('#notices-view .notice-card')).toContain(messages['notice_card.browser'])
    expect(text('#notices-view .notice-card')).not.toContain('ID ')
  })

  it('say when everything is fine', async () => {
    const { text, messages } = open({ control_status: 'active', armed: true, settings }, { route: 'notices' })
    await flush()
    expect(text('#notices-view .page-top .tag')).toBe(messages['notice_card.none_open'])
    expect(text('#notices-view .plan-panel')).toContain(messages['notice_card.all_clear'])
  })

  it('name the missing measurement and the vehicle of a vehicle notice', async () => {
    const vehicles = [{ name: 'First', source_configuration: { unavailable: ['car_soc'] } }, { name: 'Second', source_configuration: { unavailable: ['car_soc', 'grid'] } }]
    const { text } = open({ ...view({ vehicles, source_configuration: { missing: ['grid'], unavailable: [] } }) }, { route: 'notices', code: 'en' })
    await flush()
    const all = text('#notices-view .notices')
    expect(all).toMatch(/Missing configuration.*Grid connection power/)
    expect(all).toMatch(/Second:.*Vehicle SoC/)
  })

  it('refuse to start without their mount points', () => {
    nodes[1]?.remove()
    const context = testContext({ snapshot: {} as PanelSnapshot, request: (async () => ({})) as BackendRequest, now: NOW })
    expect(() => createStatusController(context)).toThrow(/mount point/)
  })
})
