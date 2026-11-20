import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mountDevice } from '@/test/mount'
import { history, NOW, snapshot } from '@/test/fixtures/device'
import { flush, testContext, type TestContext } from '@/test/host'
import type { BackendRequest, PanelSnapshot } from '@/types/host'

const MOUNT_ID = 'device-root'
let root: HTMLElement

beforeEach(() => {
  root = document.createElement('div')
  root.id = MOUNT_ID
  document.body.append(root)
})
afterEach(() => root.remove())

function open(route: string, data: object = snapshot(), panelHistory: object = history()) {
  const request = vi.fn(async () => ({})) as unknown as BackendRequest
  const context: TestContext & { getHistory: () => unknown } = {
    ...testContext({ snapshot: data as PanelSnapshot, request, now: NOW }),
    getHistory: () => panelHistory,
  }
  const view = mountDevice(context, MOUNT_ID)
  view.show(route)
  const text = (selector: string) => root.querySelector(selector)?.textContent?.replace(/\s+/g, ' ').trim() ?? ''
  const cards = () => [...root.querySelectorAll('.kpis > div')].map(card => [...card.children].map(item => item.textContent))
  const charts = () => [...root.querySelectorAll('#charts > section h2')].map(title => title.textContent)
  return { view, text, cards, charts }
}

/** A pointer at a position of the chart (0 = −24 h, 0.5 = now, 1 = +24 h). */
function pointAt(svg: SVGElement, ratio: number) {
  svg.getBoundingClientRect = () => ({ left: 0, width: 400, top: 0, height: 100, right: 400, bottom: 100, x: 0, y: 0, toJSON: () => ({}) })
  svg.dispatchEvent(Object.assign(new Event('pointermove'), { clientX: ratio * 400 }))
}

describe('device pages', () => {
  it('show the battery with mode timeline, charts and the next EOS instructions', async () => {
    const { text, cards, charts } = open('battery')
    await flush()
    expect(text('h1')).toBe('Hausspeicher')
    expect(cards()).toEqual([
      ['Aktuelle Leistung', '1,5 kW', 'Gemessen'],
      ['Ladezustand', '62 %', 'Gemessen'],
      ['EOS-Modus', 'PV-Laden', expect.any(String)],
    ])
    expect(charts()).toEqual(['Ladeleistung (+) und Entladung (−) · kW', 'Ladezustand · %', 'Bezugsstrompreis · ct/kWh'])
    expect(text('#charts .series-legend')).toContain('PV-Produktion')
    expect(text('#timeline h2')).toBe('EOS-Speichermodi')
    expect(text('#timeline .mode-detail')).toBe('PV-Laden')
    expect(text('#plan h2')).toBe('Nächste EOS-Anweisungen')
    expect(text('#plan dd')).toBe('Eigenverbrauch')
  })

  it('explain a tapped interval of the mode timeline', async () => {
    const { text } = open('battery')
    await flush()
    const segments = [...root.querySelectorAll<HTMLButtonElement>('.mode-track .mode-segment')]
    expect(segments.map(segment => segment.classList.contains('future'))).toEqual([false, true])
    segments[0]?.click()
    await flush()
    expect(text('#timeline .mode-detail')).toMatch(/^Verlauf · .* bis .* · Eigenverbrauch$/)
    expect(segments[0]?.getAttribute('aria-pressed')).toBe('true')
  })

  it('show measured and forecast values under the pointer and with the keyboard', async () => {
    open('battery')
    await flush()
    const svg = root.querySelector<SVGElement>('[data-chart="battery"] svg')
    const tooltip = root.querySelector<HTMLElement>('[data-chart="battery"] .chart-tooltip')
    expect(tooltip?.style.display).toBe('none')
    // Just before now: the last measurement within six minutes.
    pointAt(svg!, 0.4999)
    await flush()
    expect(tooltip?.style.display).toBe('')
    expect(tooltip?.textContent).toContain('Messwerte')
    expect(tooltip?.textContent).toContain('1,5 kW')
    // Half an hour ahead: the forecast slot.
    pointAt(svg!, 0.51)
    await flush()
    expect(tooltip?.textContent).toContain('Prognose')
    expect(tooltip?.textContent).toContain('1,2 kW')
    svg!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flush()
    expect(tooltip?.style.display).toBe('none')
    svg!.dispatchEvent(new FocusEvent('focus'))
    await flush()
    expect(tooltip?.style.display).toBe('')
  })

  it('show the energy balance with every enabled node and the sign note', async () => {
    const { text, cards, charts } = open('energy', snapshot({ features: { heat: false } }))
    await flush()
    expect(text('h1')).toBe('Alle Energieflüsse')
    expect(cards().map(card => card[0])).toEqual(['PV', 'Netz', 'Speicher', 'Haus', 'ID.4'])
    expect(charts()).toEqual(['Energieflüsse · kW', 'Bezugsstrompreis · ct/kWh'])
    expect(text('#charts .series-legend')).toContain('Haus gesamt · Prognose')
    expect(text('#charts .series-legend')).not.toContain('Wärmepumpe')
    expect(text('#charts > .footnote')).toContain('Bezug positiv')
    expect(text('#plan')).toContain('Prognose')
  })

  it('show PV with today and the forecast days', async () => {
    const { cards, charts } = open('solar')
    await flush()
    expect(cards()).toEqual([
      ['Aktuelle Leistung', '4,2 kW', 'Gemessen'],
      ['PV heute', '12,4 kWh', 'Aus verfügbaren Messintervallen'],
      ['PV · heute erwartet', '≈ 18,4 kWh', 'Messintervalle bisher + Restprognose'],
      ['PV · Prognose morgen', '21 kWh', 'Vollständiger Kalendertag'],
      ['PV · Prognose übermorgen', '—', 'Keine Prognosedaten verfügbar'],
    ])
    expect(charts()).toEqual(['PV-Produktion · kW'])
    expect(root.querySelector('#plan')).toBeNull()
  })

  it('mark a retained value as approximate with its age', async () => {
    const { cards } = open('grid', snapshot({ live: { ...snapshot().live, grid: null }, display: { grid: { value: -650, age_s: 170 } } }))
    await flush()
    expect(cards()[0]).toEqual(['Aktuelle Leistung', '≈ 0,65 kW', 'Stand vor 3 min'])
    expect(cards()[1]).toEqual(['Richtung', 'Einspeisung', 'Netzanschluss'])
  })

  it('link house and heat pump to their usage report', async () => {
    const house = open('house')
    await flush()
    expect(root.querySelector('.usage-link')?.getAttribute('href')).toBe('#usage/house')
    expect(house.charts()).toEqual(['Haus ohne Auto und Wärmepumpe · kW', 'Hausgesamtlast · kW'])
  })

  it('say when a chart has no data', async () => {
    const { text } = open('heat', snapshot(), history({ local: [] }))
    await flush()
    expect(text('#charts section')).toContain('Keine Daten verfügbar.')
  })

  it('ignore other routes', () => {
    const { view } = open('battery')
    expect(view.show('settings')).toBe(false)
    expect(view.show('car/%E0%A4%A')).toBe(false)
  })
})

describe('car charts', () => {
  const MINUTE = 60_000
  const iso = (ms: number) => new Date(ms).toISOString()
  const row = (offset: number, soc: number) => ({ time: iso(NOW + offset), end: iso(NOW + offset + 15 * MINUTE), car_soc: soc })
  const fleet = (count: number) => snapshot({
    vehicles: Array.from({ length: count }, (_, index) => ({
      id: `ev${index}`, name: `Auto ${index}`, vehicle_forecast_source: index ? 'constant' : 'eos',
      live: { car_soc: 30 + index * 10, car_connected: true }, settings: { pv: true, fast: false, phase_auto: true, pv_target_soc: 80, target_soc: 80 },
      forecast: [row(0, 30 + index * 10), row(15 * MINUTE, 50 + index * 10)], charge_plan_view: [],
    })),
  })
  const vehicleHistory = history({ vehicles: { ev0: [{ time: iso(NOW - MINUTE), car_soc: 20 }], ev1: [{ time: iso(NOW - MINUTE), car_soc: 21 }] } })

  it('show total power and every vehicle\'s SoC with its own history, forecast and source note', async () => {
    const { charts, text } = open('car', fleet(2), vehicleHistory)
    await flush()
    expect(charts()).toEqual(['Gesamte Autoladeleistung · kW', 'Auto 0 · Ladezustand · %', 'Auto 1 · Ladezustand · %'])
    const curves = (id: string) => [...root.querySelectorAll(`[data-chart="${id}"] path.curve`)].map(path => path.getAttribute('d'))
    // Measured 20 % a minute ago, then the forecast from 30 % to 50 %.
    expect(curves('vehicle_soc_ev0')).toEqual(['M49.965,80.000', 'M50.000,70.000 L50.521,50.000'])
    expect(curves('vehicle_soc_ev1')[0]).toBe('M49.965,79.000')
    expect(text('#charts')).toContain('SoC-Prognose aus EOS.')
    expect(text('#charts')).toContain('Aktueller SoC fortgeschrieben')
    expect(text('#plan')).toContain('ein Fahrzeug wählen')
    expect(root.querySelector('.kpis:not(.fleet-cards)')).toBeNull()
  })

  it('show one vehicle\'s power, SoC and price with its history', async () => {
    const { charts, text } = open('car/ev0', fleet(2), vehicleHistory)
    await flush()
    expect(text('h1')).toBe('Auto 0')
    expect(charts()).toEqual(['Wallbox-Leistung · kW', 'Ladezustand · %', 'Bezugsstrompreis · ct/kWh'])
    expect(root.querySelector('[data-chart="car_soc"] path.curve')?.getAttribute('d')).toBe('M49.965,80.000')
    expect(text('#charts')).toContain('SoC-Prognose aus EOS.')
    expect(text('#timeline h2')).toBe('Auto 0 · Lademodi')
  })
})
