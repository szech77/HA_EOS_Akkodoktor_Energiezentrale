import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createApp, h, shallowRef, type App } from 'vue'
import EOSSetupWizard from '@/components/settings/EOSSetupWizard.vue'
import { createSettingsStore, SETTINGS_STORE, type SettingsSnapshot } from '@/stores/settings'
import { flush, testContext, type TestContext } from '@/test/host'
import type { SetupLoad } from '@/composables/useEOSSetup'
import type { BackendRequest, PanelSnapshot } from '@/types/host'
import { RequestError } from '@/utils/bridge'

const response: SetupLoad = {
  draft: { latitude: 48, longitude: 11, timezone: 'Europe/Berlin', devices: [], planes: [], pv_provider: 'keep',
    weather_provider: 'keep', price_provider: 'keep', price_zones: [{ start: '00:00', price_ct: 30 }], fee_ct: 0, vat_percent: 19, bidding_zone: 'DE-LU',
    feedin_provider: 'keep', feedin_ct: 8.2, load_provider: 'keep', annual_kwh: 5000, inverter_id: 'inverter1',
    inverter_profile: 'generic-hybrid', inverter_power_w: 10000, horizon_hours: 24, prediction_hours: 72, interval_seconds: 300 },
  providers: { pvforecast: ['PVForecastAkkudoktor'], weather: ['WeatherBrightSky'], elecprice: ['ElecPriceFixed'], load: ['LoadAkkudoktor'] },
  profiles: { battery: ['generic-lfp'], inverter: ['generic-hybrid'] },
  current_providers: { pvforecast: null, weather: 'WeatherBrightSky', elecprice: 'ElecPriceFixed', feedintariff: 'FeedInTariffFixed', load: 'LoadAkkudoktor' },
  ha_location: { latitude: 0, longitude: 0, timezone: 'UTC' },
}
let app: App
let root: HTMLElement
let host: TestContext
let request: ReturnType<typeof vi.fn>
let gps: ReturnType<typeof vi.fn>

function mount(controlActive = false, code: 'de' | 'en' = 'de') {
  host = testContext({ snapshot: {} as PanelSnapshot, request: request as BackendRequest, now: 0, code })
  const settings = createSettingsStore({ ...host, locale: host.getLocale }, shallowRef<SettingsSnapshot>({}), { toast: vi.fn(), costsChanged: vi.fn() })
  app = createApp({ render: () => h(EOSSetupWizard, { controlActive }) })
  app.provide(SETTINGS_STORE, settings)
  app.mount(root)
}
const click = async (text: string) => {
  const button = [...root.querySelectorAll<HTMLButtonElement>('button')].find(row => row.textContent?.trim() === text)
  expect(button).toBeDefined()
  button!.click()
  await flush()
}
const submit = async () => { root.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })); await flush() }
async function review() {
  await click(host.t('wizard.start'))
  for (let index = 0; index < 5; index++) await submit()
}

beforeEach(() => {
  root = document.createElement('div'); document.body.append(root)
  gps = vi.fn()
  Object.defineProperty(navigator, 'geolocation', { configurable: true, value: { getCurrentPosition: gps } })
  Object.defineProperty(window, 'isSecureContext', { configurable: true, value: true })
  request = vi.fn(async (_action: string, values: Record<string, unknown> = {}) => {
    if (values['operation'] === 'load') return structuredClone(response)
    if (values['operation'] === 'preview') return { token: 'review-token', changes: [{ path: 'general/latitude', before: 48, after: 0 }], expires_seconds: 600 }
    return { ok: true }
  })
})
afterEach(() => { app?.unmount(); root.remove(); vi.restoreAllMocks() })

describe('EOS setup wizard', () => {
  it('loads only after starting and preserves zero-valued Home Assistant coordinates', async () => {
    mount()
    expect(request).not.toHaveBeenCalled()
    await click(host.t('wizard.start'))
    expect(gps).not.toHaveBeenCalled()
    await click(host.t('wizard.location_home'))
    expect(root.querySelector<HTMLInputElement>('[name="latitude"]')!.value).toBe('0')
    expect(root.querySelector<HTMLInputElement>('[name="longitude"]')!.value).toBe('0')
    expect(request).toHaveBeenCalledTimes(1)
  })

  it('requests GPS only on explicit input and keeps coordinates local until review', async () => {
    mount()
    await click(host.t('wizard.start'))
    gps.mockImplementation((success: PositionCallback) => success({ coords: { latitude: 0, longitude: 0, accuracy: 5 } } as GeolocationPosition))
    await click(host.t('wizard.locate'))
    expect(gps).toHaveBeenCalledWith(expect.any(Function), expect.any(Function), { enableHighAccuracy: true, maximumAge: 0, timeout: 15000 })
    expect(root.querySelector<HTMLInputElement>('[name="latitude"]')!.value).toBe('0')
    expect(request).toHaveBeenCalledTimes(1)
    expect(root.textContent).toContain('5 m')
  })

  it('offers manual input after denied GPS and does not request GPS over plain HTTP', async () => {
    mount()
    await click(host.t('wizard.start'))
    Object.defineProperty(window, 'isSecureContext', { configurable: true, value: false })
    await click(host.t('wizard.locate'))
    expect(gps).not.toHaveBeenCalled()
    expect(root.textContent).toContain(host.t('wizard.location_secure'))
    Object.defineProperty(window, 'isSecureContext', { configurable: true, value: true })
    gps.mockImplementation((_success: PositionCallback, error: PositionErrorCallback) => error({ code: 1 } as GeolocationPositionError))
    await click(host.t('wizard.locate'))
    expect(root.textContent).toContain(host.t('wizard.location_denied'))
    expect(root.querySelector<HTMLInputElement>('[name="latitude"]')!.disabled).toBe(false)
  })

  it('does not load or write until control is explicitly released', async () => {
    mount(true)
    await click(host.t('wizard.start'))
    expect(request).not.toHaveBeenCalled()
    await click(host.t('wizard.release'))
    expect(request).toHaveBeenCalledWith('control', { enabled: false })
    expect(request).not.toHaveBeenCalledWith('eos_setup', expect.anything())
  })

  it('requires server preview and a checked confirmation before a single apply', async () => {
    mount()
    await review()
    expect(request).toHaveBeenCalledWith('eos_setup', expect.objectContaining({ operation: 'preview', draft: expect.objectContaining({ latitude: 48 }) }))
    await click(host.t('wizard.apply'))
    expect(request.mock.calls.some(call => call[1]?.['operation'] === 'apply')).toBe(false)
    const checkbox = root.querySelector<HTMLInputElement>('input[type="checkbox"]')!
    checkbox.checked = true; checkbox.dispatchEvent(new Event('change', { bubbles: true })); await flush()
    await click(host.t('wizard.apply'))
    expect(request).toHaveBeenCalledWith('eos_setup', { operation: 'apply', token: 'review-token', confirm: true })
    expect(root.textContent).toContain(host.t('wizard.success'))
    expect(request.mock.calls.filter(call => call[1]?.['operation'] === 'apply')).toHaveLength(1)
  })

  it('invalidates the preview when editing and never silently retries a failed apply', async () => {
    mount()
    await review()
    const checkbox = root.querySelector<HTMLInputElement>('input[type="checkbox"]')!
    checkbox.checked = true; checkbox.dispatchEvent(new Event('change', { bubbles: true })); await flush()
    request.mockRejectedValueOnce(new RequestError('private backend text', 'invalid_settings', 'eos_setup', { reason: 'setup_conflict' }))
    await click(host.t('wizard.apply'))
    expect(root.textContent).toContain(host.t('wizard.error_setup_conflict'))
    expect(root.textContent).not.toContain('private backend text')
    expect(root.textContent).not.toContain(host.t('wizard.success'))
    expect(root.querySelector('input[type="checkbox"]')).toBeNull()
    expect(request.mock.calls.filter(call => call[1]?.['operation'] === 'apply')).toHaveLength(1)
  })

  it('edits daily price zones of a fixed tariff and shows the reviewed time windows', async () => {
    mount()
    await click(host.t('wizard.start'))
    for (let index = 0; index < 3; index++) await submit()
    const provider = root.querySelector<HTMLSelectElement>('select')!
    provider.value = 'ElecPriceFixed'; provider.dispatchEvent(new Event('change')); await flush()
    expect(root.querySelectorAll('[data-price-zone]')).toHaveLength(1)
    expect(root.textContent).not.toContain(host.t('wizard.remove_price_zone'))
    await click(host.t('wizard.add_price_zone'))
    const input = (name: string) => root.querySelector<HTMLInputElement>(`[name="${name}"]`)!
    expect(input('zone_start_1').value).toBe('01:00')
    for (const [name, value] of [['zone_start_0', '00:30'], ['zone_price_0', '8.5'], ['zone_start_1', '05:30'], ['zone_price_1', '28']]) {
      input(name!).value = value!; input(name!).dispatchEvent(new Event('input')); await flush()
    }
    request.mockImplementation(async (_action: string, values: Record<string, unknown> = {}) => values['operation'] === 'preview'
      ? { token: 'review-token', expires_seconds: 600, changes: [{ path: 'elecprice/elecpricefixed/elecprice_marketprice_amt_kwh/windows',
        before: [{ start: '00:00', end: '24:00', value: .3 }],
        after: [{ start: '00:00', end: '00:30', value: .28 }, { start: '00:30', end: '05:30', value: .085 }, { start: '05:30', end: '24:00', value: .28 }] }] }
      : structuredClone(response))
    await submit(); await submit()
    const sent = request.mock.calls.find(call => call[1]?.['operation'] === 'preview')![1]['draft']
    expect(sent['price_provider']).toBe('ElecPriceFixed')
    expect(sent['price_zones']).toEqual([{ start: '00:30', price_ct: 8.5 }, { start: '05:30', price_ct: 28 }])
    const row = root.querySelector('.wizard-review tbody tr')!.textContent!
    expect(row).toContain(`0,3 ${host.t('wizard.all_day')}`)
    expect(row).toContain('00:30–05:30: 0,085')
    expect(row).toContain('05:30–24:00: 0,28')
  })

  it('renders the same guided steps in English', async () => {
    mount(false, 'en')
    await review()
    expect(root.textContent).toContain('Review & apply')
    expect(root.textContent).toContain('Latitude (°)')
    expect(root.textContent).not.toMatch(/wizard\.(field|step)_/)
  })
})
