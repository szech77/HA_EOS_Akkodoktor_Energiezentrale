import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mountOverview } from '@/test/mount'
import { backend } from '@/test/backend'
import { flush, languagePack, testContext } from '@/test/host'
import type { BackendRequest, PanelSnapshot } from '@/types/host'

const NOW = Date.parse('2026-11-11T12:00:00Z')
const HOUR = 3_600_000
const at = (hours: number) => new Date(NOW + hours * HOUR).toISOString()
const MOUNT_ID = 'overview-root'
let root: HTMLElement

function reset() {
  root?.remove()
  root = document.createElement('div')
  root.id = MOUNT_ID
  document.body.append(root)
}
beforeEach(reset)
afterEach(() => root.remove())

function open(data: Record<string, unknown>, code: 'de' | 'en' = 'de') {
  const context = testContext({ code, snapshot: data as PanelSnapshot, request: (async () => ({})) as BackendRequest, now: NOW })
  const view = mountOverview(context, MOUNT_ID)
  view.show()
  const node = (id: string) => root.querySelector<HTMLAnchorElement>(`.node[data-node="${id}"]`)
  const pulse = (index: number) => root.querySelectorAll<SVGPathElement>('.pulse')[index]
  /** Next panel refresh: app.js receives a new snapshot object from the backend. */
  const update = async (values: Record<string, unknown>) => {
    context.snapshot = { ...context.snapshot, ...values } as PanelSnapshot
    view.show()
    await flush()
  }
  return { node, pulse, update, messages: languagePack(code).messages, text: (selector: string) => root.querySelector(selector)?.textContent?.replace(/\s+/g, ' ').trim() ?? '' }
}

const car = (id: string, soc: number | null, watts: number | null, extra: Record<string, unknown> = {}) =>
  ({ id, name: `Auto ${id}`, live: { car_soc: soc, car: watts, car_connected: true }, power_reference: { car: (watts ?? 0) * 2 }, ...extra })
const base = (values: Record<string, unknown> = {}) => ({
  zone: 'Europe/Berlin',
  live: { time: at(0), solar: 1000, grid: 2000, battery: 0, battery_soc: 60, house: 1000, heat: 0, car: 9000 },
  settings: { battery_min_soc: 20 },
  features: { car: true, heat: true },
  power_reference: { car: 22000 },
  ...values,
})

describe('energy flow', () => {
  it('links PV to its report and the weather symbol to PV and weather', async () => {
    const { node } = open(base({ live: { ...base().live, weather: { condition: 'sunny', temperature: 7, unit: '°C' } } }))
    await flush()
    expect(node('solar')?.getAttribute('href')).toBe('#usage/pv')
    root.querySelector<HTMLButtonElement>('.flow-weather')?.click()
    expect(location.hash).toBe('#pv')
    expect(root.querySelector('.flow-weather')?.textContent).toContain('7 °C')
  })

  it('greys the grid in backup mode and stops even retained pulses until grid operation returns', async () => {
    for (const code of ['de', 'en'] as const) {
      reset()
      const { node, pulse, update, messages } = open(base({ power_supply: { state: 'backup', grid_active: false }, flow_display: { grid: { value: 5000, aligned: true, age_s: 20 } } }), code)
      await flush()
      const grid = node('grid')!
      expect(grid.classList.contains('grid-disconnected')).toBe(true)
      expect(grid.querySelector('.backup-indicator')?.getAttribute('title')).toBe(messages['power_supply.backup'])
      expect(grid.querySelector('.backup-bolt')).not.toBeNull()
      expect(pulse(1)?.classList.contains('inactive')).toBe(true)
      expect(grid.querySelector('strong')?.textContent).toBe('—')
      expect(grid.getAttribute('aria-label')).toContain(messages['power_supply.backup'])
      await update({ power_supply: { state: 'grid', grid_active: true }, flow_display: {} })
      expect(grid.classList.contains('grid-disconnected')).toBe(false)
      expect(grid.querySelector('.backup-indicator')).toBeNull()
      expect(pulse(1)?.classList.contains('inactive')).toBe(false)
      expect(grid.querySelector('strong')?.textContent).toMatch(/^2(,00)? kW$/)
    }
  })

  it('creates no backup state from zero or missing grid watts', async () => {
    for (const grid of [0, null]) {
      reset()
      const { node } = open(base({ live: { ...base().live, grid } }))
      await flush()
      expect(node('grid')?.classList.contains('grid-disconnected')).toBe(false)
      expect(node('grid')?.querySelector('.backup-indicator')).toBeNull()
    }
  })

  it('shows one configured vehicle with its own SoC and link instead of the generic car node', async () => {
    const { node } = open(base({ vehicles: [car('first', 20, 1380)] }))
    await flush()
    const vehicle = node('car/first')!
    expect(vehicle.getAttribute('href')).toBe('#car/first')
    expect(vehicle.querySelector('span:not(.orb)')?.textContent).toBe('Auto first · 20 %')
    expect(vehicle.querySelector('strong')?.textContent).toBe('1,38 kW')
    expect(vehicle.querySelectorAll('.car-soc-bar.filled')).toHaveLength(1)
    expect(node('car')).toBeNull()
  })

  it('gives two cars independent values, SoCs, rows, wires and power references', async () => {
    const vehicles = [car('first', 20, 1380), car('second', 80, 11040)]
    const { node } = open(base({ vehicles }))
    await flush()
    const nodes = vehicles.map(vehicle => node(`car/${vehicle.id}`)!)
    expect(nodes.map(item => item.querySelectorAll('.car-soc-bar.filled').length)).toEqual([1, 4])
    expect(nodes.map(item => item.querySelector('.power-ring')?.getAttribute('data-fraction'))).toEqual(['0.5', '0.5'])
    expect(nodes[0]!.style.getPropertyValue('--y')).not.toBe(nodes[1]!.style.getPropertyValue('--y'))
    const wires = root.querySelector('.wire')?.getAttribute('d') ?? ''
    const pulses = [...root.querySelectorAll('.pulse.car')].map(path => path.getAttribute('d'))
    expect(pulses).toHaveLength(2)
    expect(new Set(pulses).size).toBe(2)
    for (const d of pulses) expect(wires).toContain(d)
  })

  it('greys offline and unplugged cars independently and never animates their retained power', async () => {
    const { node, messages } = open(base({ vehicles: [car('active', 40, 7000),
      car('offline', 70, 7000, { live: { car: 7000, car_soc: 70, car_connected: false, car_available: false } }),
      car('unplugged', 10, 7000, { live: { car: 7000, car_connected: false, car_available: true } })] }))
    await flush()
    expect(node('car/active')?.classList.contains('vehicle-inactive')).toBe(false)
    for (const id of ['offline', 'unplugged']) {
      const item = node(`car/${id}`)!
      expect(item.classList.contains('vehicle-inactive')).toBe(true)
      expect(item.querySelector('strong')?.hidden).toBe(true)
      expect(item.querySelector('.power-ring')?.getAttribute('data-fraction')).toBe('')
    }
    expect([...root.querySelectorAll('.pulse.car')].map(path => path.classList.contains('inactive'))).toEqual([false, true, true])
    expect(node('car/offline')?.title).not.toBe(node('car/unplugged')?.title)
    expect(node('car/offline')?.getAttribute('aria-label')).toContain(messages['vehicle.unavailable'])
  })

  it('never borrows a missing SoC or power from another vehicle and shows retained values with their age', async () => {
    const { node } = open(base({ vehicles: [car('known', 100, 7000), car('missing', null, null),
      car('retained', null, null, { display: { car_soc: { value: 0 }, car: { value: 1400, estimated: true, age_s: 120 } } })] }))
    await flush()
    const missing = node('car/missing')!
    expect(missing.querySelector('strong')?.textContent).toBe('—')
    expect(missing.querySelector('span:not(.orb)')?.textContent).toBe('Auto missing')
    expect(missing.querySelector('.car-soc')?.hasAttribute('hidden')).toBe(true)
    const retained = node('car/retained')!
    expect(retained.querySelector('strong')?.textContent).toBe('≈ 1,4 kW')
    expect(retained.querySelector('span:not(.orb)')?.textContent).toBe('Auto retained · 0 %')
    expect(retained.title).toMatch(/2/)
  })

  it('fits eight vehicles in separate rows, keeps nodes between refreshes and drops removed ones', async () => {
    const { node, update } = open(base({ vehicles: Array.from({ length: 8 }, (_, index) => car(`ev${index}`, index * 10, 0)) }))
    await flush()
    const nodes = [...root.querySelectorAll<HTMLElement>('.node.car')]
    expect(new Set(nodes.map(item => item.style.getPropertyValue('--y'))).size).toBe(8)
    expect(root.querySelector<HTMLElement>('.flow')?.style.height).toBe(`${10 * 144}px`)
    const first = node('car/ev0')
    await update({ live: { ...base().live, solar: 2000 } })
    expect(node('car/ev0')).toBe(first)
    await update({ vehicles: [car('ev7', 70, 0)] })
    expect(root.querySelectorAll('.node.car')).toHaveLength(1)
    expect(root.querySelectorAll('.pulse.car')).toHaveLength(1)
    await update({ features: { car: false, heat: false } })
    expect(root.querySelectorAll('.node.car')).toHaveLength(0)
    expect(node('heat')).toBeNull()
  })

  it('keeps the single-car node and SoC of an installation without a vehicle list', async () => {
    const { node } = open(base({ live: { ...base().live, car_soc: 60 } }))
    await flush()
    expect(node('car')?.querySelector('span:not(.orb)')?.textContent).toMatch(/60 %/)
  })

  it('shows vehicle names as text and restores the power after plugging in again', async () => {
    const vehicle = car('ev', 30, 1400, { name: '<img src=x onerror=alert(1)>' })
    const { node, update } = open(base({ vehicles: [vehicle] }))
    await flush()
    expect(node('car/ev')?.querySelector('span:not(.orb)')?.textContent).toBe('<img src=x onerror=alert(1)> · 30 %')
    expect(root.querySelector('img')).toBeNull()
    await update({ vehicles: [{ ...vehicle, live: { ...vehicle.live, car_connected: false } }] })
    expect(node('car/ev')?.querySelector('strong')?.hidden).toBe(true)
    await update({ vehicles: [vehicle] })
    expect(node('car/ev')?.querySelector('strong')?.textContent).toBe('1,4 kW')
    expect(node('car/ev')?.classList.contains('vehicle-inactive')).toBe(false)
  })

  it('marks the nodes the backend maps open notices to, including one vehicle of a fleet', async () => {
    const { node, update, messages } = open(base({ vehicles: [car('a', 40, 3700), car('b', 50, 0)], node_problems: { 'car/b': 'error', battery: 'warning' } }))
    await flush()
    expect(node('car/b')?.classList.contains('problem-error')).toBe(true)
    expect(node('car/a')?.classList.contains('problem-error')).toBe(false)
    expect(node('battery')?.classList.contains('problem-warning')).toBe(true)
    expect(node('car/b')?.querySelector('.flag')).not.toBeNull()
    expect(node('car/b')?.getAttribute('aria-label')).toContain(messages['flow.problem_error'])
    await update({ node_problems: {} })
    expect(node('car/b')?.querySelector('.flag')).toBeNull()
  })
})

describe('overview figures and EOS plan', () => {
  it('show PV today, price, grid direction and battery state', async () => {
    const { text } = open(base({ pv_today_kwh: 12.4, pv_daily_forecast: [{ kwh: 6 }], live: { ...base().live, grid: -800, price: 31.2, battery: 1500 } }))
    await flush()
    const cards = [...root.querySelectorAll('#overview-kpis > div')].map(card => [...card.children].map(item => item.textContent))
    expect(cards).toEqual([
      ['PV heute', '12,4 kWh', 'Restprognose 6 kWh'],
      ['Strompreis jetzt', '31,2 ct/kWh', 'Bezug'],
      ['Netzanschluss', '0,8 kW', 'Einspeisung'],
      ['Speicher', '60 %', 'Lädt · 1,5 kW'],
    ])
    expect(text('.flow-footer .tag')).toMatch(/13:00/)
  })

  it('places plan segments by time, so many short EOS changes cannot push the plan before now', async () => {
    const timeline = [{ start: NOW - 3 * HOUR, end: NOW, mode: 'SELF_CONSUMPTION', kind: 'history' }]
    for (let index = 0; index < 48; index++) timeline.push({ start: NOW + index * 15 * 60_000, end: NOW + (index + 1) * 15 * 60_000, mode: index % 2 ? 'NON_EXPORT' : 'FORCED_CHARGE', kind: 'plan' })
    open(base({ mode_timeline: { battery: timeline } }))
    await flush()
    const span = 15 * HOUR
    const segments = [...root.querySelectorAll<HTMLElement>('.plan-track .mode-segment')].map(item => [Number(item.style.getPropertyValue('--start')), Number(item.style.getPropertyValue('--duration'))])
    expect(segments).toHaveLength(49)
    expect(segments[0]).toEqual([0, 3 * HOUR / span])
    segments.slice(1).forEach(([start, duration], index) => {
      expect(Math.abs(start! - (3 * HOUR + index * 15 * 60_000) / span)).toBeLessThan(1e-12)
      expect(Math.abs(duration! - 15 * 60_000 / span)).toBeLessThan(1e-12)
    })
    expect(parseFloat(root.querySelector<HTMLElement>('.plan-now')?.style.left ?? '')).toBe(20)
    root.querySelectorAll<HTMLButtonElement>('.plan-track .mode-segment')[0]?.click()
    await flush()
    expect(root.querySelector('#plan-panel .mode-detail')?.textContent).toMatch(/Eigenverbrauch$/)
  })

  it('reads upcoming battery and car changes as everyday sentences with time and price', async () => {
    for (const code of ['de', 'en'] as const) {
      reset()
      const data = { live: { battery_mode: 'NON_EXPORT', car_mode: 'IDLE' }, features: { car: true }, vehicle_name: 'E-Auto',
        forecast: [{ time: at(0), end: at(6), price: 30.4 }, { time: at(6), end: at(30), price: 24.1 }],
        plan: { battery: [{ time: at(1), mode: 'SELF_CONSUMPTION' }, { time: at(2), mode: 'SELF_CONSUMPTION' }, { time: at(8), mode: 'FORCED_CHARGE' }], car: [{ time: at(9), mode: 'FORCED_CHARGE' }] } }
      const { messages } = open(base({ ...data, plan_events: backend('planEvents', data, { now: NOW }) }), code)
      await flush()
      const rows = [...root.querySelectorAll('.next-details .row')].map(row => row.textContent ?? '')
      expect(rows).toHaveLength(3)
      expect(rows[0]).toContain(messages['plan_event.battery_SELF_CONSUMPTION'])
      expect(rows[0]).toContain(code === 'de' ? '30,4 ct/kWh' : '30.4 ct/kWh')
      expect(rows[1]).toContain(messages['plan_event.battery_FORCED_CHARGE'])
      expect(rows[2]).toContain('E-Auto')
      expect(root.querySelector('.next-details summary .tag')?.textContent).toBe('3')
    }
  })

  it('names what the battery does from the forecast and keeps the EOS mode as detail', async () => {
    const forecast = [{ time: at(0), end: at(1), price: 28.1, battery: 2600, solar: 0 }, { time: at(1), end: at(3), price: 28.4, battery: 0, solar: 0 }]
    const data = { live: { battery_mode: 'FORCED_CHARGE' }, features: { car: true }, forecast, plan: { battery: [{ time: at(1), mode: 'NON_EXPORT' }] } }
    const { messages, text } = open(base({ ...data, plan_events: backend('planEvents', data, { now: NOW }) }))
    await flush()
    expect(text('.next-details .row b')).toBe(messages['plan_event.effect_hold'])
    expect(text('.next-details .row small')).toContain('PV-Laden')
  })

  it('stays calm without a plan and remembers a collapsed event list per viewer', async () => {
    const { text, messages } = open(base({ plan_events: [] }))
    await flush()
    expect(text('#plan-panel > .footnote')).toBe(messages['plan.no_valid'])
    expect(text('.next-details .list')).toBe(messages['status.no_next_mode'])
    const details = root.querySelector<HTMLDetailsElement>('.next-details')!
    expect(details.open).toBe(true)
    details.open = false
    details.dispatchEvent(new Event('toggle'))
    await flush()
    expect(localStorage.getItem('eos-energiezentrale.next-events-open')).toBe('0')
    reset()
    open(base())
    await flush()
    expect(root.querySelector<HTMLDetailsElement>('.next-details')?.open).toBe(false)
    localStorage.clear()
  })

  it('keeps working when the browser blocks storage', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('denied') })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('denied') })
    open(base())
    await flush()
    const details = root.querySelector<HTMLDetailsElement>('.next-details')!
    expect(details.open).toBe(true)
    details.open = false
    expect(() => details.dispatchEvent(new Event('toggle'))).not.toThrow()
  })
})
