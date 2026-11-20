import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { backend } from '@/test/backend'
import { flush, languagePack, testContext, type TestContext } from '@/test/host'
import { mountDayBalance, mountUsage } from '@/test/mount'
import type { Preferences } from '@/stores/usage'
import type { BackendRequest, PanelSnapshot } from '@/types/host'
import type { Report } from '@/types/usage'
import { slotsOf } from '@/utils/usageCharts'

const NOW = Date.parse('2026-11-18T12:00:00Z')
const MOUNT_ID = 'usage-root'
const de = languagePack('de').messages
const en = languagePack('en').messages
let root: HTMLElement

/** A new mount point: each page mounts its own app. */
function reset() {
  root?.remove()
  root = document.createElement('div')
  root.id = MOUNT_ID
  document.body.append(root)
}
beforeEach(reset)
afterEach(() => root.remove())

type Raw = { kwh: number; cost_eur: number | null; cost_unknown_kwh: number; seconds?: number; sources: Record<string, { kwh: number; cost_eur: number | null; cost_unknown_kwh: number }> }

/** A grid-only amount as the ledger stores it; the backend adds prices, shares and estimate markers. */
function amount(kwh: number, cost: number | null, unknown = 0): Raw {
  return {
    kwh, cost_eur: cost, cost_unknown_kwh: unknown, seconds: 3600,
    sources: Object.fromEntries(['pv', 'battery', 'grid', 'unknown'].map(source => [source,
      { kwh: source === 'grid' ? kwh : 0, cost_eur: source === 'grid' ? cost : 0, cost_unknown_kwh: source === 'grid' ? unknown : 0 }])),
  }
}
function pvAmount(kwh: number, cost = 0): Raw {
  const value = amount(kwh, cost)
  value.sources['grid'] = { kwh: 0, cost_eur: 0, cost_unknown_kwh: 0 }
  value.sources['pv'] = { kwh, cost_eur: cost, cost_unknown_kwh: 0 }
  return value
}
const report = (raw: object, consumers = ['house', 'heat', 'car']) => backend<Report>('report', raw, { consumers })

function memory(values: Record<string, string> = {}): Preferences & { values: Map<string, string> } {
  const map = new Map(Object.entries(values))
  return { values: map, getItem: key => map.get(key) ?? null, setItem: (key, value) => void map.set(key, value) }
}

function open(answer: (values: Record<string, unknown>) => unknown, options: { snapshot?: object; storage?: Preferences; code?: 'de' | 'en' } = {}) {
  const request = vi.fn(async (_action: string, values: Record<string, unknown> = {}) => answer(values)) as unknown as BackendRequest
  const context: TestContext = testContext({ code: options.code ?? 'de', snapshot: { zone: 'Europe/Berlin', ...options.snapshot } as PanelSnapshot, request, now: NOW })
  const page = mountUsage(context, MOUNT_ID, options.storage ?? memory({ 'eos-energiezentrale.billing-period': 'month' }))
  const $ = <T extends Element = HTMLElement>(selector: string) => root.querySelector<T>(selector)
  const text = (selector: string) => $(selector)?.textContent?.replace(/\s+/g, ' ').trim() ?? ''
  const kpis = () => [...root.querySelectorAll('.kpis > div')].map(card => [...card.children].map(item => item.textContent ?? ''))
  const click = async (selector: string) => {
    $(selector)?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await flush()
  }
  return { request, context, page, $, text, kpis, click }
}

describe('report pages', () => {
  it('show total consumption for every period from backend totals, without ledger rows as consumers', async () => {
    for (const period of ['day', 'month', 'year'] as const) {
      const stamp = period === 'day' ? '2026-02-01T00:00:00+00:00' : period === 'month' ? '2026-02-01' : '2026-02'
      const data = report({
        date: '2026-02-01', end: period === 'year' ? '2027-01-01' : period === 'month' ? '2026-03-01' : '2026-02-02', hours: [stamp],
        consumers: { house: { total: amount(4, 1), bins: [{ time: stamp, ...amount(4, 1) }] }, export: { total: amount(999, 999), bins: [] }, storage: { total: amount(999, 999), bins: [] } },
      })
      const page = open(() => data, { storage: memory({ 'eos-energiezentrale.billing-period': period }) })
      page.page.show('total')
      await flush()
      expect(page.request).toHaveBeenCalledWith('accounting', { period, date: '2026-11-18' })
      expect(page.text('#usage h1')).toBe(de['usage.total_title'])
      expect(page.$<HTMLAnchorElement>('.d-head .back')?.getAttribute('href')).toBe('#overview')
      expect(page.kpis()[0]?.[1]).toBe('4 kWh')
      expect(page.text('#usage-charts title')).toMatch(/4 kWh.*Ø 25 ct\/kWh/)
      expect(page.text('.usage-two')).toContain(de['usage.net'])
      expect(page.text('#usage-charts') + page.text('#usage-table')).not.toMatch(/999/)
      reset()
    }
  })

  it('place the backend unit price under the cost figure of every consumer and mark estimates', async () => {
    for (const key of ['house', 'heat', 'car', 'car/one']) {
      const data = report({ date: '2026-02-01', end: '2026-03-01', consumers: { [key]: { total: amount(4, 1), bins: [] } } }, ['house', 'heat', 'car', key])
      const page = open(() => data, { snapshot: { vehicles: [{ id: 'one', name: 'Auto One' }, { id: 'two', name: 'Two' }] } })
      page.page.show(key)
      await flush()
      expect(page.kpis()[2]?.[1]).toMatch(/1,00/)
      expect(page.kpis()[2]?.[2]).toBe('Ø 25 ct/kWh')
      expect(page.text('#usage-table')).toContain('25 ct/kWh')
      expect(page.$('.d-head .back')?.getAttribute('href')).toBe(key.startsWith('car') ? '#car' : '#overview')
      if (key === 'car/one') expect(page.text('#usage h1')).toBe('Auto One')
      reset()
    }
    const partial = report({ date: '2026-02-01', end: '2026-03-01', consumers: { house: { total: amount(4, 0.6, 2), bins: [{ time: '2026-02-01', ...amount(4, 0.6, 2) }] } } })
    const page = open(() => partial)
    page.page.show('house')
    await flush()
    // 0.60 € is only the known part; the average of the priced energy is an estimate.
    expect(page.kpis()[2]?.[2]).toBe('Ø ≈ 30 ct/kWh')
    expect(page.kpis()[2]?.[1]).toContain(de['billing.known_portion'])
    expect(page.text('#usage-charts title')).toContain('Ø ≈ 30 ct/kWh')
    expect(page.text('#usage > details:last-of-type')).toContain(de['billing.estimated_average_note'])
  })

  it('show grid import above and feed-in below, prices and where the PV energy went', async () => {
    const stamp = '2026-02-01'
    const data = report({
      date: stamp, end: '2026-03-01', base_days: 28, settings: { base_price_eur_month: 10 },
      consumers: {
        house: { total: amount(4, 1.2), bins: [{ time: stamp, ...amount(4, 1.2) }] },
        export: { total: pvAmount(3, 0.24), bins: [{ time: stamp, ...pvAmount(3, 0.24) }] },
        storage: { total: amount(1, 0.3), bins: [{ time: stamp, ...amount(1, 0.3) }] },
      },
    })
    const storage = memory({ 'eos-energiezentrale.billing-period': 'month' })
    const page = open(() => data, { storage })
    page.page.show('grid')
    await flush()
    expect(page.text('#usage h1')).toBe(de['usage.grid_title'])
    expect(page.kpis()[0]?.[1]).toBe('3 kWh')
    expect(page.kpis()[1]?.[1]).toBe('5 kWh')
    expect(page.$('#usage-charts g')?.getAttribute('aria-label')).toMatch(new RegExp(`${de['usage.import']} 5 kWh \\([^)]*1,50[^)]*\\) · ${de['usage.feed_in']} 3 kWh \\(\\+[^)]*0,24`))
    expect(page.text('.chart-tools .tag')).toBe(de['usage.unit_day'])
    expect(page.text('.series-legend')).toContain(`↓ ${de['usage.feed_in']}`)
    expect(page.text('.usage-two')).toContain(de['usage.grid_balance']!)
    expect(page.text('.usage-two')).toContain('−0,24')
    expect(page.text('#usage-table')).toMatch(/3 kWh · 100 %/)
    expect(page.$('.usage-head .plan-link')?.getAttribute('href')).toBe('#grid')
    // The euro chart draws import cost up and feed-in credit down; only the drawing changes.
    await page.click('.chart-tools button:nth-child(3)')
    expect(page.$('#usage-charts svg')?.getAttribute('aria-label')).toBe(de['usage.grid_cost_chart'])
    expect(page.text('.chart-tools .tag')).toBe(de['usage.unit_eur_day'])
    expect(storage.values.get('eos-energiezentrale.billing-unit')).toBe('eur')
    expect(page.page.store.selectUnit('W')).toBe(false)
    page.page.show('house')
    await flush()
    expect(page.$('#usage-charts svg')?.getAttribute('aria-label')).toBe(de['billing.cost_chart'])
  })

  it('draw the power profile of a day in kW; costs and older days stay hourly', async () => {
    const hours = ['2026-11-18T08:00:00+00:00', '2026-11-18T09:00:00+00:00']
    const point = (time: string, pv: number, grid: number) => ({ time, house: { pv, battery: 0, grid, unknown: 0 }, total: { pv, battery: 0, grid, unknown: 0 }, grid: { import: grid, export: 0 } })
    const day = report({
      date: '2026-11-18', end: '2026-11-19', hours, base_days: 1, settings: {},
      consumers: { house: { total: amount(2, 0.6), bins: hours.map(time => ({ time, ...amount(1, 0.3) })) } },
      power_profile: { step_s: 120, gap_s: 600, points: [point(hours[0]!, 1500, 500), point('2026-11-18T08:02:00+00:00', 1200, 800), point('2026-11-18T09:30:00+00:00', 0, 2000)] },
    }) as Report
    let answer: Report = day
    const page = open(() => answer, { storage: memory({ 'eos-energiezentrale.billing-period': 'day', 'eos-energiezentrale.billing-unit': 'kw' }) })
    page.page.show('house')
    await flush()
    const svg = () => page.$('#usage-charts svg')
    expect(svg()?.getAttribute('aria-label')).toBe(de['usage.power_chart'])
    expect(page.text('.chart-tools .tag')).toBe(de['usage.unit_power'])
    // PV and grid as areas; the gap after 08:02 splits them (no PV at 09:30); hours stay tappable.
    expect(root.querySelectorAll('polygon.area')).toHaveLength(3)
    expect(root.querySelectorAll('[data-billing-bin]')).toHaveLength(2)
    expect(root.querySelector('[data-billing-bin]')?.getAttribute('aria-label')).toContain('1 kWh')
    expect(root.querySelector('#usage-charts title')).toBeNull()
    // The pointer readout names the time, the total and each source with power.
    const readout = page.page.store.charts.readout(day.power_profile!.points[0]!, 'house')
    expect(readout.title).toMatch(/2 kW$/)
    expect(readout.lines.map(([label, value]) => [label, value])).toEqual([[de['billing.pv'], '1,5 kW'], [de['billing.grid'], '0,5 kW']])
    expect(page.page.store.charts.readout(day.power_profile!.points[2]!, 'grid').lines.map(([label, value]) => [label, value])).toEqual([[de['usage.import'], '2 kW'], [de['usage.feed_in'], '0 kW']])
    // Costs stay bars on the day view as well.
    page.page.store.selectUnit('eur')
    await flush()
    expect(svg()?.getAttribute('aria-label')).toBe(de['billing.cost_chart'])
    expect(root.querySelector('polygon.area')).toBeNull()
    // kWh: the hourly bars; tapping an hour shows its values below the chart.
    page.page.store.selectUnit('kwh')
    await flush()
    expect(svg()?.getAttribute('aria-label')).toBe(de['billing.energy_chart'])
    await page.click('[data-billing-bin]')
    expect(page.$('[data-billing-bin]')?.getAttribute('aria-pressed')).toBe('true')
    expect(page.text('.chart-panel > .footnote')).toContain('1 kWh')
    // A day beyond the local history has no profile: kW shows the hourly bars with a note.
    answer = { ...day, power_profile: { points: [] } }
    page.page.store.selectUnit('kw')
    await page.page.store.load(true)
    await flush()
    expect(svg()?.getAttribute('aria-label')).toBe(de['billing.energy_chart'])
    expect(page.text('.chart-panel > .footnote')).toContain(de['usage.profile_hourly'])
  })

  it('show PV production by use, the forecast ahead and its power curve, never in euros', async () => {
    const hours = ['2026-11-18T10:00:00+00:00', '2026-11-18T11:00:00+00:00', '2026-11-18T12:00:00+00:00']
    const data = report({
      date: '2026-11-18', end: '2026-11-19', hours, base_days: 1, settings: {},
      consumers: { house: { total: pvAmount(3), bins: hours.slice(0, 2).map(time => ({ time, ...pvAmount(1.5) })) }, export: { total: pvAmount(1), bins: [{ time: hours[1], ...pvAmount(1) }] } },
      power_profile: { step_s: 120, gap_s: 600, points: [{ time: hours[0], solar: 2500, pv_flow: { house: 2500, car: 0, heat: 0, storage: 0, export: 0 }, pv_gap: { battery_pv: 0, battery_grid: 0, battery_unknown: 0, grid: 0, unknown: 0 }, house: { pv: 2500, battery: 0, grid: 0, unknown: 0 }, total: { pv: 2500, battery: 0, grid: 0, unknown: 0 }, grid: { import: 0, export: 0 } }] },
      pv_forecast: { bins: [{ time: hours[2], kwh: 2.2 }], points: [{ time: hours[2], end: '2026-11-18T13:00:00+00:00', w: 2200 }], kwh: 2.2, complete: true },
    })
    const page = open(() => data, { storage: memory({ 'eos-energiezentrale.billing-period': 'day', 'eos-energiezentrale.billing-unit': 'kwh' }) })
    page.page.show('pv')
    await flush()
    expect(page.text('#usage h1')).toBe(de['usage.pv_title'])
    expect(page.$('#usage-charts svg')?.getAttribute('aria-label')).toBe(de['usage.pv_chart'])
    expect(root.querySelectorAll('.forecast-bar')).toHaveLength(1)
    const labels = [...root.querySelectorAll('[data-billing-bin]')].map(item => item.getAttribute('aria-label')).join('\n')
    expect(labels).toContain(`${de['usage.pv_produced']} 2,5 kWh: ${de['usage.pv_to_house']} 1,5 kWh · ${de['usage.pv_to_export']} 1 kWh`)
    expect(labels).toContain(`${de['usage.pv_forecast']} 2,2 kWh`)
    expect(page.kpis()[0]?.[1]).toBe('4 kWh')
    expect(page.kpis()[3]?.[1]).toBe('2,2 kWh')
    expect(page.$<HTMLButtonElement>('.chart-tools button:nth-child(3)')?.hidden).toBe(true)
    page.page.store.selectUnit('kw')
    await flush()
    expect(page.$('#usage-charts svg')?.getAttribute('aria-label')).toBe(de['usage.pv_power_chart'])
    expect(root.querySelector('.forecast-line')).not.toBeNull()
    expect(root.querySelector('polygon.area')).not.toBeNull()
    page.page.store.selectUnit('eur')
    await flush()
    expect(page.$('#usage-charts svg')?.getAttribute('aria-label')).toBe(de['usage.pv_chart'])
  })

  it('stack PV uses above zero and the uncovered consumption below, battery by charging origin', async () => {
    const hour = '2026-11-18T10:00:00+00:00'
    const data = report({ date: '2026-11-18', end: '2026-11-19', hours: [hour], consumers: {} }) as Report
    const page = open(() => ({ ...data, balance: { ...(data.balance ?? {}), bins: [{ time: hour, pv_kwh: 3.5, pv_flow: { house: 1, car: 2, heat: 0, storage: 0.5, export: 0 }, pv_gap: { battery_pv: 0.6, battery_grid: 0.2, battery_unknown: 0, grid: 0.4, unknown: 0 } }] } }),
      { storage: memory({ 'eos-energiezentrale.billing-period': 'day', 'eos-energiezentrale.billing-unit': 'kwh' }) })
    page.page.show('pv')
    await flush()
    const fills = [...root.querySelectorAll<SVGRectElement>('[data-billing-bin] rect')].map(rect => rect.style.fill).filter(Boolean)
    expect(fills).toHaveLength(6)
    expect(fills.slice(0, 3)).toEqual(['var(--house)', 'var(--car)', 'var(--battery)'])
    expect(page.$('[data-billing-bin]')?.getAttribute('aria-label')).toContain(
      `${de['usage.pv_uncovered']}: ${de['usage.pv_gap_battery_pv']} 0,6 kWh · ${de['usage.pv_gap_battery_grid']} 0,2 kWh · ${de['usage.pv_gap_grid']} 0,4 kWh`)
    const readout = page.page.store.charts.readout({ time: hour, solar: 3500, pv_flow: { house: 1000, car: 2000, heat: 0, storage: 500, export: 0 }, pv_gap: { battery_pv: 600, battery_grid: 0, battery_unknown: 0, grid: 400, unknown: 0 } }, 'pv')
    expect(readout.lines.map(line => line[0])).toEqual([de['usage.pv_to_house'], de['usage.pv_to_car'], de['usage.pv_to_storage'], de['usage.pv_gap_battery_pv'], de['usage.pv_gap_grid']])
  })

  it('split own power by origin so grid-charged storage is not listed as own power', async () => {
    const part = (kwh: number, cost: number, price: number | null) => ({ kwh, cost_eur: cost, price_ct: price })
    const view = { grid_kwh: 1, grid_price_ct: 30, grid_cost_eur: 0.3, self_kwh: 4, self_price_ct: 10, self_cost_eur: 0.4, cost_available: true, cost_eur: 0.7,
      self_origin: { pv_direct: part(2, 0.2, 10), battery_pv: part(1, 0.11, 11), battery_grid: part(1, 0.33, 33), battery_unknown: part(0, 0, null) } }
    const page = open(() => ({ date: '2026-11-01', end: '2026-12-01', consumers: {}, views: { house: view } }))
    const prices = (data: object) => page.page.store.text.prices('house', data as Report).rows.map(row => row.label).join('|')
    const labels = prices({ views: { house: view } })
    expect(labels).toMatch(new RegExp(`${de['usage.self_pv_direct']!.split('{')[0]}.*${de['usage.self_battery_pv']!.split('{')[0]}.*${de['usage.self_battery_grid']!.split('{')[0]}`))
    expect(labels).not.toContain(de['usage.self_power']!.split('{')[0])
    expect(prices({ views: { house: { ...view, self_origin: { ...view.self_origin, battery_unknown: part(0.5, 0.15, 30) } } } })).toContain(de['usage.self_battery_unknown']!.split('{')[0])
    // Reports without the split keep the combined row.
    expect(prices({ views: { house: { ...view, self_origin: undefined } } })).toContain(de['usage.self_power']!.split('{')[0])
  })

  it('word the facts the backend selected', () => {
    const page = open(() => ({}))
    const { fact } = page.page.store.text
    expect(fact({ id: 'best', time: '2026-02-03', unit: 'day', percent: 80 })).toMatchObject({ title: de['usage.fact_best_day'], tag: '80 %' })
    expect(fact({ id: 'savings', eur: -0.5, self_price_ct: 40, grid_price_ct: 30 }).title).toBe(de['usage.fact_extra_cost'])
    expect(fact({ id: 'savings', eur: -0.5, self_price_ct: 40, grid_price_ct: 30 }).tag).toMatch(/^-0,50/)
    expect(fact({ id: 'consumer', key: 'house', kwh: 2, cost_available: true, cost_eur: 0.5 }).href).toBe('#usage/house')
  })
})

describe('report values', () => {
  it('never present unknown costs as free and keep tiny costs visible', () => {
    const page = open(() => ({}))
    const { costValue, money, averageCostLabel } = page.page.store.text
    const value = (raw: object) => backend<Parameters<typeof costValue>[0]>('amount', raw)
    expect(costValue(value({ kwh: 5, cost_eur: 0, cost_unknown_kwh: 5 }))).toBe('—')
    expect(costValue(value({ kwh: 5, cost_eur: 1, cost_unknown_kwh: 2 }))).toMatch(/^≈/)
    expect(costValue(value({ kwh: 5, cost_eur: -1, cost_unknown_kwh: 0 }))).not.toMatch(/^≈/)
    expect(costValue(value({ kwh: 0.03, cost_eur: 0.009, cost_unknown_kwh: 0 }))).toMatch(/0,009/)
    expect(averageCostLabel(value({ kwh: 1, cost_eur: 0, cost_unknown_kwh: 1 }))).toBe('Ø — ct/kWh')
    expect(money(0.000001)).toMatch(/^< /)
    expect(money(-0.000001)).toMatch(/^> /)
    expect(money(0)).toMatch(/^0,00/)
  })

  it('label the unit price in German and English', () => {
    for (const [code, messages, label] of [['de', de, 'Ø 25 ct/kWh'], ['en', en, 'Avg 25 ct/kWh']] as const) {
      const page = open(() => ({}), { code })
      const value = backend<Parameters<typeof page.page.store.text.averageCostLabel>[0]>('amount', { kwh: 4, cost_eur: 1, cost_unknown_kwh: 0 })
      expect(page.page.store.text.averageCostLabel(value)).toBe(label)
      expect(page.page.store.text.name('total')).toBe(messages['billing.total_consumption'])
    }
  })

  it('keep all calendar positions: days of a month, twelve months and repeated DST hours', () => {
    expect(slotsOf({ date: '2026-02-01', end: '2026-03-01', consumers: {} }, 'month', 'de-DE', 'Europe/Berlin').map(slot => slot.key)).toHaveLength(28)
    const year = slotsOf({ date: '2026-01-01', end: '2027-01-01', consumers: {} }, 'year', 'de-DE', 'Europe/Berlin')
    expect(year).toHaveLength(12)
    expect(year[11]?.key).toBe('2026-12')
    const dst = slotsOf({ date: '2026-10-25', end: '2026-10-26', hours: ['2026-10-25T00:00:00+00:00', '2026-10-25T01:00:00+00:00'], consumers: {} }, 'day', 'de-DE', 'Europe/Berlin')
    expect(dst).toHaveLength(2)
    expect(dst[0]?.label).not.toBe(dst[1]?.label)
  })
})

describe('report selection', () => {
  it('remembers the period, drills into a bin without remembering the date and steps back and forth', async () => {
    const storage = memory()
    const data = report({ date: '2026-11-01', end: '2026-12-01', consumers: { house: { total: amount(4, 1), bins: [{ time: '2026-11-03', ...amount(4, 1) }] } } })
    const page = open(() => data, { storage })
    page.page.show('house')
    await flush()
    // Without a saved choice the month opens.
    expect(page.request).toHaveBeenLastCalledWith('accounting', { period: 'month', date: '2026-11-18' })
    await page.click('[data-billing-bin]')
    expect(page.request).toHaveBeenLastCalledWith('accounting', { period: 'day', date: '2026-11-03' })
    expect(storage.values.get('eos-energiezentrale.billing-period')).toBe('day')
    expect([...storage.values.values()]).not.toContain('2026-11-03')
    await page.click('.pnav .pbtn')
    expect(page.request).toHaveBeenLastCalledWith('accounting', { period: 'day', date: '2026-11-02' })
    await page.click('.segctl button:nth-child(3)')
    expect(page.request).toHaveBeenLastCalledWith('accounting', { period: 'year', date: '2026-11-02' })
  })

  it('ignores invalid saved values and keeps working when the browser blocks its storage', async () => {
    const blocked: Preferences = { getItem: () => { throw new Error('blocked') }, setItem: () => { throw new Error('blocked') } }
    for (const storage of [memory({ 'eos-energiezentrale.billing-period': 'week', 'eos-energiezentrale.billing-unit': 'W' }), blocked]) {
      const page = open(() => ({ date: '2026-11-01', end: '2026-12-01', consumers: {} }), { storage })
      page.page.show('house')
      await flush()
      expect(page.page.store.period.value).toBe('month')
      expect(page.page.store.unit.value).toBe('kwh')
      expect(page.page.store.selectPeriod('week')).toBe(false)
      expect(page.page.store.selectPeriod('year')).toBe(true)
      reset()
    }
  })

  it('reloads a shown report at most once a minute while the panel refreshes', async () => {
    const page = open(() => ({ date: '2026-11-01', end: '2026-12-01', consumers: {} }))
    page.page.show('house')
    await flush()
    page.context.clock.now += 5_000
    page.page.show('house')
    await flush()
    expect(page.request).toHaveBeenCalledTimes(1)
    page.page.store.invalidate()
    page.context.clock.now += 5_000
    page.page.show('house')
    await flush()
    expect(page.request).toHaveBeenCalledTimes(2)
  })
})

describe('today on the overview', () => {
  it('shows each consumer with its unit price, the feed-in and the total, each linking to its report', async () => {
    const context = testContext({ snapshot: { zone: 'Europe/Berlin' } as PanelSnapshot, request: (async () => ({})) as BackendRequest, now: NOW })
    mountDayBalance(context, MOUNT_ID, report({ date: '2026-02-01', consumers: { house: { total: amount(1, 0.1) }, heat: { total: amount(3, 0.9) }, export: { total: pvAmount(2, 0.16) } } }))
    await flush()
    const tiles = [...root.querySelectorAll<HTMLAnchorElement>('.balance-card')]
    expect(tiles.map(tile => tile.getAttribute('href'))).toEqual(['#usage/house', '#usage/heat', '#usage/grid', '#usage/total'])
    expect(tiles[0]?.textContent).toMatch(/0,10[^Ø]*Ø 10 ct\/kWh/)
    expect(tiles[1]?.textContent).toMatch(/0,90[^Ø]*Ø 30 ct\/kWh/)
    expect(tiles[2]?.className).toContain('feed')
    expect(tiles[2]?.textContent).toMatch(new RegExp(`${de['usage.feed_in']}2 kWh\\+0,16`))
    expect(tiles[3]?.textContent).toMatch(/4 kWh.*Ø 25 ct\/kWh/)
    expect(root.querySelector('#day-balance .panel-heading')?.textContent).toContain(de['billing.today'])
  })

  it('shows no unpriced day as free', async () => {
    const context = testContext({ snapshot: { zone: 'Europe/Berlin' } as PanelSnapshot, request: (async () => ({})) as BackendRequest, now: NOW })
    mountDayBalance(context, MOUNT_ID, report({ date: '2026-11-10', consumers: { heat: { total: { kwh: 3, cost_eur: 0, cost_unknown_kwh: 3, sources: { pv: { kwh: 3, cost_eur: 0, cost_unknown_kwh: 3 } } } } } }))
    await flush()
    expect(root.querySelector('.panel-heading span')?.textContent).toContain('3 kWh · —')
  })
})
