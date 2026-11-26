import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { backend } from '@/test/backend'
import { flush, languagePack, testContext, type TestContext } from '@/test/host'
import { mountSettings } from '@/test/mount'
import type { BackendRequest, PanelSnapshot } from '@/types/host'
import { RequestError } from '@/utils/bridge'

const NOW = Date.parse('2026-11-18T17:50:00Z')
const MOUNT_ID = 'settings-root'
let root: HTMLElement

function reset() {
  root?.remove()
  root = document.createElement('div')
  root.id = MOUNT_ID
  document.body.append(root)
}
beforeEach(reset)
afterEach(() => root.remove())

const settings = {
  schedule: [], battery_min_soc: 10, battery_max_soc: 90, battery_pv_support: true, reserve_w: 100, regulation_interval_s: 10,
  battery_pv_min_soc: 30, battery_pv_wait_s: 60, battery_pv_start: false, battery_pv_surplus_w: 500,
  holiday_state: 'BY', holiday_locality: 'augsburg', holiday_catholic: true,
}
const costs = { settings: { pv_price_source: 'eos', pv_price_ct: 7, capacity_wh: 10000, base_price_eur_month: 12, efficiency_source: 'eos', charge_efficiency: 0.95, discharge_efficiency: 0.95, initial_price_ct: null },
  pv_price_ct: 8.2, effective: { charge_efficiency: 0.96, discharge_efficiency: 0.94, capacity_wh: 11059 } }

function open(snapshot: object = {}, options: { code?: 'de' | 'en'; request?: (action: string, values: Record<string, unknown>) => unknown } = {}) {
  const calls: [string, Record<string, unknown>][] = []
  const request = vi.fn(async (action: string, values: Record<string, unknown> = {}) => {
    calls.push([action, values])
    return options.request ? options.request(action, values) : action === 'accounting' && values['period'] ? costs : {}
  }) as unknown as BackendRequest
  const refresh = vi.fn(async () => undefined)
  const context: TestContext = testContext({ code: options.code ?? 'de', snapshot: { zone: 'Europe/Berlin', settings, battery_limits_status: 'confirmed', ...snapshot } as PanelSnapshot, request, now: NOW, refresh })
  const page = mountSettings(context, MOUNT_ID, { historyStatus: 'history_available' })
  const messages = languagePack(options.code ?? 'de').messages
  const $ = <T extends Element = HTMLElement>(selector: string) => root.querySelector<T>(selector)
  const text = (selector: string) => $(selector)?.textContent?.replace(/\s+/g, ' ').trim() ?? ''
  const input = (name: string) => $<HTMLInputElement>(`[name="${name}"]`)!
  const set = async (name: string, value: string | boolean) => {
    const element = input(name)
    if (typeof value === 'boolean') {
      element.checked = value
      element.dispatchEvent(new Event('change', { bubbles: true }))
    } else {
      element.value = value
      element.dispatchEvent(new Event(element.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true }))
    }
    await flush()
  }
  const click = async (selector: string) => {
    $<HTMLElement>(selector)?.click()
    await flush()
  }
  return { page, context, calls, refresh, messages, $, text, input, set, click }
}

describe('settings', () => {
  it('fill from the backend and save only after a change, with typed values', async () => {
    const { $, text, input, set, click, calls, page, refresh, messages } = open()
    await flush()
    expect(input('battery_min_soc').value).toBe('10')
    expect(input('holiday_locality').value).toBe('augsburg')
    expect(text('#battery-limits-status')).toBe(messages['settings.battery_limits_confirmed']!.replace('{minimum}', '10').replace('{maximum}', '90'))
    expect($('#savebar')).toBeNull()
    await set('battery_min_soc', '15')
    expect(text('#savebar b')).toBe(messages['settings.one_change'])
    await set('battery_pv_support', false)
    expect(text('#savebar b')).toBe(messages['settings.changes']!.replace('{count}', '2'))
    await click('#savebar .btn.primary')
    expect(calls).toContainEqual(['settings', {
      battery_min_soc: 15, battery_max_soc: 90, reserve_w: 100, regulation_interval_s: 10, battery_pv_min_soc: 30, battery_pv_wait_s: 60, battery_pv_surplus_w: 500,
      battery_pv_support: false, battery_pv_start: false, holiday_catholic: true, holiday_state: 'BY', holiday_locality: 'augsburg',
    }])
    expect(page.toasts).toEqual([messages['settings.saved']])
    expect(refresh).toHaveBeenCalled()
    expect($('#savebar')).toBeNull()
  })

  it('mark the fields the backend rejected and show the first one', async () => {
    const { $, text, set, click, messages, page, calls } = open({}, {
      request: action => {
        if (action === 'settings') throw new RequestError('rejected', 'invalid_settings', 'settings', { reason: 'out_of_range', fields: ['battery_pv_surplus_w', 'unknown_field'] })
        return {}
      },
    })
    await flush()
    await set('battery_min_soc', '20')
    await click('#savebar .btn.primary')
    expect(calls.map(([action]) => action)).toContain('settings')
    const label = $('[name="battery_pv_surplus_w"]')?.closest('label')
    expect(label?.className).toContain('invalid')
    expect(label?.querySelector('.field-error')?.textContent).toBe(messages['settings.error_out_of_range'])
    expect($<HTMLElement>('[data-settings-section="car"]')?.style.display).not.toBe('none')
    expect(document.activeElement?.getAttribute('name')).toBe('battery_pv_surplus_w')
    expect(page.toasts.at(-1)).toBe(messages['settings.fix_fields'])
    // Editing the field removes its error.
    await set('battery_pv_surplus_w', '600')
    expect($('[name="battery_pv_surplus_w"]')?.closest('label')?.className).not.toContain('invalid')
    expect(text('.field-error')).toBe('')
  })

  it('do not send unreadable numbers and discard restores the saved values', async () => {
    const { input, set, click, calls, page, messages, $ } = open()
    await flush()
    await click('details.expert summary')
    await set('reserve_w', '')
    await click('#savebar .btn.primary')
    expect(calls.some(([action]) => action === 'settings')).toBe(false)
    expect($('[name="reserve_w"]')?.closest('label')?.className).toContain('invalid')
    expect(page.toasts).toEqual([messages['settings.fix_fields']])
    await click('#savebar .btn.ghost')
    expect(input('reserve_w').value).toBe('100')
    expect($('#savebar')).toBeNull()
    expect(page.toasts.at(-1)).toBe(messages['settings.discarded'])
  })

  it('allow a locality only in Bavaria and the Catholic holidays only where they exist', async () => {
    const { input, set, click } = open()
    await flush()
    await click('[data-section="calendar"]')
    expect(input('holiday_locality').disabled).toBe(false)
    await set('holiday_state', 'SN')
    expect(input('holiday_locality').disabled).toBe(true)
    expect(input('holiday_locality').value).toBe('')
    expect(input('holiday_catholic').checked).toBe(true)
    await set('holiday_state', 'HE')
    expect(input('holiday_catholic').checked).toBe(false)
    expect(input('holiday_catholic').disabled).toBe(true)
  })

  it('follow backend changes without local edits and keep local edits', async () => {
    const { input, set, page, context } = open()
    await flush()
    context.snapshot = { ...context.snapshot, settings: { ...settings, battery_max_soc: 95 } } as PanelSnapshot
    page.refresh()
    await flush()
    expect(input('battery_max_soc').value).toBe('95')
    await set('battery_min_soc', '25')
    context.snapshot = { ...context.snapshot, settings: { ...settings, battery_max_soc: 80 } } as PanelSnapshot
    page.refresh()
    await flush()
    expect(input('battery_max_soc').value).toBe('95')
    expect(input('battery_min_soc').value).toBe('25')
  })

  it('hide the car sections without a car', async () => {
    const { $ } = open({ features: { car: false } })
    await flush()
    expect($('[data-section="car"]')).toBeNull()
    expect($('[data-section="calendar"]')).toBeNull()
    expect($('[name="battery_pv_support"]')).toBeNull()
  })

  it('load the cost settings with their effective values and save them through the same bar', async () => {
    const { input, set, click, calls, text, page, messages } = open({ battery_group: { battery_count: 2, capacity_wh: 20000, devices: [] } })
    await flush()
    await click('[data-section="costs"]')
    expect(calls).toContainEqual(['accounting', { period: 'day' }])
    // The EOS price is shown as the effective price; a group of batteries fixes the capacity.
    expect(input('pv_price_ct').disabled).toBe(true)
    expect(input('pv_price_ct').value).toBe('8.2')
    expect(input('capacity_wh').disabled).toBe(true)
    expect(input('capacity_wh').value).toBe('20000')
    expect(text('[data-settings-section="costs"]')).toContain(`${messages['billing.pv_effective']}: 8,2 ct/kWh`)
    expect(text('[data-settings-section="costs"]')).toContain('96 % / 94 % · 11,06 kWh')
    await set('pv_price_source', 'manual')
    expect(input('pv_price_ct').disabled).toBe(false)
    expect(input('base_price_amount_0').value).toBe('12')
    expect(input('base_price_from_0').value).toBe('')
    await set('base_price_amount_0', '14.5')
    await click('#savebar .btn.primary')
    expect(calls).toContainEqual(['accounting', { settings: {
      pv_price_ct: 8.2, charge_efficiency: 0.95, discharge_efficiency: 0.95, capacity_wh: 20000, base_price_eur_month: 12,
      base_price_history: [{ valid_from: '', period: 'month', amount_eur: 14.5 }],
      pv_price_source: 'manual', efficiency_source: 'eos', initial_price_ct: null,
    } }])
    expect(page.costsChanged.count).toBe(1)
    expect(calls.filter(([action, values]) => action === 'accounting' && values['period'] === 'day')).toHaveLength(2)
  })

  it.each(['de', 'en'] as const)('show power-dependent EOS efficiencies and why the inverter is missing in %s', async code => {
    let curves: object = { efficiency_curves: { inverter: true, charge: [0.8385, 0.9409], discharge: [0.858, 0.9409] }, efficiency_curves_reason: null }
    const request = (action: string, values: Record<string, unknown>) => (action === 'accounting' && values['period'] ? { ...costs, ...curves } : {})
    const first = open({}, { code, request })
    await flush()
    await first.click('[data-section="costs"]')
    const decimal = code === 'de' ? ',' : '.'
    expect(first.text('[data-settings-section="costs"]')).toContain(
      `${first.messages['billing.effective_curves']}: 83${decimal}9–94${decimal}1 % / 85${decimal}8–94${decimal}1 % · 11${decimal}06 kWh`)
    first.page.unmount()
    reset()
    curves = { efficiency_curves: { inverter: false, charge: [0.94, 0.975], discharge: [0.96, 0.975] }, efficiency_curves_reason: 'inverter_unassigned' }
    const second = open({}, { code, request })
    await flush()
    await second.click('[data-section="costs"]')
    const costsText = second.text('[data-settings-section="costs"]')
    expect(costsText).toContain(second.messages['billing.effective_curves_battery'])
    expect(costsText).toContain(second.messages['billing.curves_reason_inverter_unassigned'])
    expect(costsText).not.toMatch(/billing\.curves_reason/)
  })

  it.each(['de', 'en'] as const)('edit dated monthly and daily fees, reload and discard in %s', async code => {
    let saved: Record<string, unknown> = { ...costs.settings }
    const { input, set, click, calls, text, messages, $ } = open({}, { code, request: (action, values) => {
      if (action === 'accounting' && values['settings']) saved = values['settings'] as Record<string, unknown>
      return { ...costs, settings: saved }
    } })
    await flush()
    await click('[data-section="costs"]')
    expect(text('[data-base-prices] legend')).toBe(messages['billing.base_price_history'])
    expect(input('base_price_period_0').value).toBe('month')
    await click('[data-base-add]')
    await set('base_price_from_1', '2026-10-15')
    await set('base_price_period_1', 'day')
    await set('base_price_amount_1', '0.12345')
    expect(input('base_price_amount_1').checkValidity()).toBe(true)
    await set('base_price_amount_1', '0.123456789')
    expect(input('base_price_amount_1').checkValidity()).toBe(true)
    await click('#savebar .btn.primary')
    expect(saved['base_price_history']).toEqual([
      { valid_from: '', period: 'month', amount_eur: 12 },
      { valid_from: '2026-10-15', period: 'day', amount_eur: 0.123456789 },
    ])
    expect(input('base_price_amount_1').value).toBe('0.123456789')
    expect($('#savebar')).toBeNull()
    await set('base_price_amount_1', '-1')
    const writes = () => calls.filter(([, values]) => values['settings']).length
    await click('#savebar .btn.primary')
    expect(writes()).toBe(1)
    expect(text('.field-error')).toBe(messages['settings.error_input'])
    await click('#savebar .btn.ghost')
    expect(input('base_price_amount_1').value).toBe('0.123456789')
    await click('[data-base-remove]')
    await click('[data-base-remove]')
    await click('#savebar .btn.primary')
    expect(saved['base_price_history']).toEqual([])
    expect($('[data-base-prices] input')).toBeNull()
  })

  it.each(['de', 'en'] as const)('save a dated fixed kWh price, reload, toggle and discard in %s', async code => {
    let saved: Record<string, unknown> = { ...costs.settings }
    const { $, input, set, click, calls, messages } = open({}, { code, request: (action, values) => {
      if (action === 'accounting' && values['settings']) saved = values['settings'] as Record<string, unknown>
      return { ...costs, settings: saved }
    } })
    await flush()
    await click('[data-section="costs"]')
    expect(input('grid_price_source_0').value).toBe('dynamic')
    expect($('[name="grid_price_ct_0"]')).toBeNull()
    await set('grid_price_source_0', 'fixed')
    expect(input('grid_price_ct_0').closest('label')?.textContent).toContain(messages['billing.grid_price_ct'])
    await click('#savebar .btn.primary')
    expect(calls.some(([, values]) => values['settings'])).toBe(false)
    await set('grid_price_ct_0', '29.1234')
    await set('base_price_from_0', '2026-01-01')
    await click('#savebar .btn.primary')
    expect(saved['base_price_history']).toEqual([{
      valid_from: '2026-01-01', period: 'month', amount_eur: 12, grid_price_source: 'fixed', grid_price_ct: 29.1234,
    }])
    expect(input('grid_price_ct_0').value).toBe('29.1234')
    expect($('#savebar')).toBeNull()
    await set('grid_price_ct_0', '30')
    await click('#savebar .btn.ghost')
    expect(input('grid_price_ct_0').value).toBe('29.1234')
    await set('grid_price_source_0', 'dynamic')
    expect($('[name="grid_price_ct_0"]')).toBeNull()
    await set('grid_price_source_0', 'fixed')
    expect(input('grid_price_ct_0').value).toBe('29.1234')
    await set('grid_price_source_0', 'dynamic')
    await click('#savebar .btn.primary')
    expect(saved['base_price_history']).toEqual([{
      valid_from: '2026-01-01', period: 'month', amount_eur: 12, grid_price_source: 'dynamic', grid_price_ct: 29.1234,
    }])
  })

  it('show backend date errors on the tariff list and preserve edits', async () => {
    const { click, set, $, text, messages } = open({}, { request: (action, values) => {
      if (action === 'accounting' && values['settings']) throw new RequestError('invalid', 'invalid_settings', 'accounting', { fields: ['base_price_history'], reason: 'invalid_type' })
      return costs
    } })
    await flush()
    await click('[data-section="costs"]')
    await click('[data-base-add]')
    await set('base_price_from_1', '')
    await click('#savebar .btn.primary')
    expect(text('[data-base-prices] .field-error')).toBe(messages['settings.error_invalid_type'])
    expect(document.activeElement?.getAttribute('name')).toBe('base_price_history')
    expect($('#savebar')).not.toBeNull()
    await set('base_price_from_1', '2026-11-01')
    expect($('[data-base-prices] .field-error')).toBeNull()
  })
})

describe('control areas', () => {
  it('take over an area only after confirmation and report the result', async () => {
    const control = { battery: { available: true, enabled: false, release_pending: false }, vehicle: { available: false, enabled: false, release_pending: false } }
    const { $, text, click, calls, refresh, messages } = open({ control })
    await flush()
    await click('[data-section="system"]')
    expect($<HTMLButtonElement>('[data-control-area="vehicle"] [data-area-action="toggle"]')?.hidden).toBe(true)
    expect(text('[data-control-area="vehicle"] .control-area-state')).toBe(messages['control.area_unavailable.vehicle'])
    await click('[data-control-area="battery"] [data-area-action="toggle"]')
    expect(text('[data-control-area="battery"] .control-area-confirm p')).toBe(messages['control.area_confirm.battery'])
    expect(document.activeElement?.getAttribute('data-area-action')).toBe('confirm')
    expect(calls.some(([action]) => action === 'control')).toBe(false)
    await click('[data-control-area="battery"] [data-area-action="confirm"]')
    expect(calls).toContainEqual(['control', { battery: true }])
    expect(text('#control-result')).toBe(messages['control.area_taken.battery'])
    expect(refresh).toHaveBeenCalled()
  })

  it('wait for the settings before any change', async () => {
    const { $ } = open({ settings: {}, control: { battery: { available: true, enabled: true, release_pending: false } } })
    await flush()
    expect($<HTMLButtonElement>('[data-control-area="battery"] [data-area-action="toggle"]')?.disabled).toBe(true)
  })
})

describe('connections and battery group', () => {
  const group = (value: object) => open({ eos_status: 'plan_available', battery_group: value }, { code: 'de' })

  it('list EOS, InfluxDB and the plugins with their features', async () => {
    const { text, messages } = open({ eos_status: 'plan_available', plugins: { battery: { name: 'Fronius <GEN24>', features: { grid_charge: true, charge_limit: false }, measurements: ['battery_soc'] } } })
    await flush()
    const list = text('#connections')
    expect(list).toContain(`Akkudoktor EOS${messages['status.plan_available']}`)
    expect(list).toContain(`InfluxDB${messages['status.history_available']}`)
    expect(list).toContain('Fronius <GEN24>')
    expect(root.querySelector('#connections')?.innerHTML).not.toContain('<GEN24>')
    expect(list).toContain(messages['measurement.battery_soc'])
  })

  it('identify PV-only units, storage SoC and the combined capacity in both languages', async () => {
    for (const code of ['de', 'en'] as const) {
      const { text } = open({ battery_group: { inverter_count: 2, battery_count: 1, capacity_wh: 10000, devices: [
        { name: 'primary', battery: true, soc: 0, solar: 2000, ac: -500, available: true },
        { name: 'roof', battery: false, solar: 1200, ac: 1200, available: true }] } }, { code })
      await flush()
      const list = text('#connections')
      expect(list).toMatch(/10 kWh/)
      expect(list).toMatch(/SoC: 0 %/)
      expect(list).toMatch(/AC[^:]*: − 0[.,]5 kW/)
      expect(list).toContain('roof')
      expect(list).toMatch(code === 'de' ? /Nur PV/ : /PV only/)
      reset()
    }
  })

  it('keep missing measurements unknown, show names as text and name incomplete devices', async () => {
    const { text } = group({ inverter_count: 2, battery_count: 2, devices: [{ name: '<device>', battery: true, soc: null, solar: null, ac: null, available: false }] })
    await flush()
    expect(text('#connections')).toContain('<device>')
    expect(root.querySelector('#connections')?.innerHTML).not.toContain('<device>')
    expect(text('#connections')).toMatch(/SoC: —/)
    expect(text('#connections')).toMatch(/Messwerte unvollständig/)
  })

  it('show Victron firmware diagnostics with version, source and raw registers', async () => {
    for (const code of ['de', 'en'] as const) {
      const render = async (firmware: object) => {
        reset()
        const page = open({ battery_group: { devices: [{ name: 'GX', battery: true, measurements: {}, read_diagnostics: { firmware } }] } }, { code })
        await flush()
        return page.text('#connections')
      }
      const manual = await render({ version: 'v3.66', source: 'configured', register_status: 'reserved', raw_words: [65535, 65535] })
      expect(manual).toMatch(/Venus OS: v3\.66/)
      expect(manual).toMatch(code === 'de' ? /manuell angegeben/ : /manually configured/)
      expect(manual).toMatch(/0xFFFF 0xFFFF/)
      expect(await render({ version: 'v3.50–v3.69', source: 'assumed', register_status: 'reserved', raw_words: [65535, 65535] })).toMatch(code === 'de' ? /Standardannahme/ : /assumed default/)
      expect(await render({ version: 'v3.74~42', source: 'detected', register_status: 'valid', raw_words: [0x0374, 0x42] })).toMatch(code === 'de' ? /automatisch erkannt/ : /automatically detected/)
      const unknown = await render({ version: null, source: 'unknown', register_status: 'unsupported', raw_words: null })
      expect(unknown).toMatch(code === 'de' ? /unbekannt/ : /unknown/)
      expect(unknown).not.toMatch(/v3\.66/)
    }
  })

  it('show the declared Victron values, the pooled EOS approximation and a missing battery', async () => {
    let page = group({ inverter_count: 1, battery_count: 1, approximate: true, devices: [{ name: 'Victron', battery: true, soc: 100, available: true, plugin: { name: '<custom plugin>' }, measurements: { solar: 250, house_total: 408, grid: 0 } }] })
    await flush()
    const list = page.text('#connections')
    expect(list).toMatch(/PV-Leistung/)
    expect(list).toMatch(/Hausverbrauch/)
    expect(list).toMatch(/0,41 kW/)
    expect(list).not.toMatch(/Wechselrichter AC/)
    expect(list).toContain('<custom plugin>')
    expect(list).toMatch(/angenäherte EOS-Planung/)
    reset()
    page = group({ inverter_count: 0, battery_count: 0, devices: [] })
    await flush()
    expect(page.text('#connections')).toMatch(/Kein Speicher eingerichtet/)
  })
})

describe('source diagnostics', () => {
  const now = NOW
  const iso = new Date(now).toISOString()
  const plugin = { type: 'plugin', name: 'Configured devices' }
  const data = {
    live: { time: iso, solar: 0, grid: 10, house_total: 940, house: 940, heat: 0, car: 0, battery_soc: 87, battery_charge: 0, battery_discharge: 510 },
    features: { car: true, heat: true },
    plugins: { battery: { name: 'Configured devices', measurements: ['battery_soc', 'battery_charge', 'battery_discharge'] }, wallbox: { name: 'go-e <v2>', measurements: ['car'] } },
    source_configuration: { missing: [], unavailable: ['heat'], sources: {
      solar: { source: plugin, available: true, reason: null, max_age_s: 45, sample: iso },
      grid: { source: plugin, available: true, reason: null, max_age_s: 45, sample: iso },
      house_total: { source: plugin, available: true, reason: null, max_age_s: 120, sample: iso },
      heat: { source: { type: 'sensor', name: 'sensor.heat_pump' }, available: false, reason: 'stale', max_age_s: 120, sample: new Date(now - 300000).toISOString() } } },
    battery_group: { devices: [{ name: 'Victron', battery: true, available: true, plugin: { name: 'Victron GX' }, soc: 87, charge: 0, discharge: 510, measurements: { grid: 10, house_total: 940 } }] },
  }
  const rows = () => [...root.querySelectorAll('#source-diagnostics tr')].map(row => [...row.children].map(cell => cell.textContent?.trim()))

  it('list every configured source with value, age and status', async () => {
    open({ source_diagnostics: backend('sourceDiagnostics', data, { now }) })
    await flush()
    expect(rows()).toContainEqual(['Netzanschlussleistung', 'Plugin: Configured devices', '10 W', '0 s', 'OK'])
    expect(rows()).toContainEqual(['Wärmepumpenleistung', 'Sensor: sensor.heat_pump', '—', '300 s', 'veraltet (max. 120 s)'])
    expect(root.querySelector('#source-diagnostics tr.warn code')?.textContent).toBe('sensor.heat_pump')
    expect(root.querySelector('#source-diagnostics')?.textContent).toContain('go-e <v2>')
    expect(root.querySelector('#source-diagnostics')?.innerHTML).not.toContain('<v2>')
    expect(root.querySelector('#source-diagnostics')?.textContent).toContain('Stand 18:50:00')
  })

  it('show the AC balance against the measured house total and estimated values with their reason', async () => {
    open({ source_diagnostics: backend('balancedDiagnostics', data, { now }) })
    await flush()
    expect(rows()).toContainEqual(['Hausverbrauch gesamt aus Bilanz (PV + Netz + Entladung − Ladung)', '520 W'])
    expect(rows()).toContainEqual(['Abweichung: Bilanz − Messung', '−420 W'])
    expect(root.querySelector('#source-diagnostics tr.warn td[colspan]')?.textContent).toMatch(/Gemessener Hausverbrauch weicht ab/)
    expect([...root.querySelectorAll('#source-diagnostics h3')].map(item => item.textContent)).toContain('Victron · Victron GX')
    reset()
    open({ source_diagnostics: backend('sourceDiagnostics', { ...data, live: { ...data.live, balance: { house_total: 520, complete: true,
      consumers: { house: 520, car: 0, heat: 0 }, estimated: { heat: 'consumer_hold', solar: 'source_balance' } } } }, { now }) })
    await flush()
    expect(rows()).toContainEqual(['PV-Leistung', 'aus gemessenem Hausverbrauch und den übrigen Quellen berechnet'])
    expect(rows()).toContainEqual(['Wärmepumpenleistung', 'Messwert kurz nicht verfügbar, letzter Wert gehalten'])
  })

  it('say when there are no diagnostics yet', async () => {
    const { text, messages } = open()
    await flush()
    expect(text('#source-diagnostics')).toBe(messages['diagnostics.empty'])
  })

  it('copy an aligned plain-text report, with a fallback for a blocked clipboard', async () => {
    let copied = ''
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: async (value: string) => { copied = value } } })
    const view = backend<{ sources: unknown[] }>('balancedDiagnostics', data, { now })
    const { click, text } = open({ source_diagnostics: view })
    await flush()
    await click('#diagnostics-copy')
    expect(text('#diagnostics-result')).toBe('Messwerte in die Zwischenablage kopiert.')
    const lines = copied.split('\n')
    expect(lines[0]).toBe('EOS Energiezentrale · Diagnose · Messquellen')
    expect(lines[1]).toMatch(/^Stand 18\.11\.26, 18:50:00 \(2026-11-18T17:50:00/)
    expect(lines.some(line => /^Netzanschlussleistung +Plugin: Configured devices +10 W +0 s +OK$/.test(line))).toBe(true)
    expect(lines.some(line => /^Wärmepumpenleistung +Sensor: sensor\.heat_pump +— +300 s +veraltet \(max\. 120 s\)$/.test(line))).toBe(true)
    expect(copied).toMatch(/Abweichung: Bilanz − Messung +-420 W\nErlaubte Abweichung +300 W\nGemessener Hausverbrauch weicht ab/)
    expect(lines).toContain('Geräte: Victron · Victron GX · Messwerte vollständig')
    expect(copied).toContain('Plugin: go-e <v2>')
    // Right-aligned value and age columns end below their headings in every source row.
    const header = lines.find(line => line.startsWith('Messgröße'))!
    const sources = lines.slice(lines.indexOf(header) + 1, lines.indexOf(header) + 1 + view.sources.length)
    const valueEnd = header.indexOf('Wert') + 4
    const ageEnd = header.indexOf('Alter') + 5
    sources.forEach(line => {
      expect(line.slice(0, valueEnd)).toMatch(/(W|%|—)$/)
      expect(line.slice(0, ageEnd)).toMatch(/( s|—)$/)
    })
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: async () => { throw new Error('denied') } } })
    const execCommand = vi.fn(() => false)
    Object.defineProperty(document, 'execCommand', { configurable: true, value: execCommand })
    await click('#diagnostics-copy')
    expect(execCommand).toHaveBeenCalledWith('copy')
    expect(text('#diagnostics-result')).toMatch(/Kopieren/)
  })

  it('save a dated UTF-8 text file with the same report', async () => {
    let blob: Blob | undefined
    const create = vi.spyOn(URL, 'createObjectURL').mockImplementation(value => {
      blob = value as Blob
      return 'blob:report'
    })
    URL.revokeObjectURL ??= () => undefined
    const clicked = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    const { click, text } = open({ source_diagnostics: backend('sourceDiagnostics', data, { now }) })
    await flush()
    await click('#diagnostics-export')
    expect(create).toHaveBeenCalled()
    expect(clicked).toHaveBeenCalled()
    expect(blob?.type).toBe('text/plain;charset=utf-8')
    expect(await blob?.text()).toMatch(/Speicher-Entladeleistung +510 W/)
    expect(text('#diagnostics-result')).toBe('Datei eos-messwerte-2026-11-18-17-50-00.txt gespeichert.')
  })
})
