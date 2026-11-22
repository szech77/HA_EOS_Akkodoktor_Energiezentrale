import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { BackendRequest } from '@/types/host'
import { flush, testContext, type TestContext } from '@/test/host'
import { mountPvWeather } from '@/test/mount'
import { RELOAD_MS } from '@/composables/usePvForecast'
import { forecastAnswer, NOW, snapshot, solarRows } from '@/test/fixtures/pvWeather'

const MOUNT_ID = 'pv-root'
let root: HTMLElement

beforeEach(() => {
  root = document.createElement('div')
  root.id = MOUNT_ID
  document.body.append(root)
})
afterEach(() => root.remove())

function open(options: { request?: BackendRequest; code?: 'de' | 'en'; values?: Parameters<typeof snapshot>[0] } = {}) {
  const request = options.request ?? vi.fn(async () => forecastAnswer()) as unknown as BackendRequest
  const context: TestContext = testContext({ code: options.code ?? 'de', snapshot: snapshot(options.values), request, now: NOW })
  const view = mountPvWeather(context, MOUNT_ID)
  view.open()
  return { context, view, request, text: (selector: string) => root.querySelector(selector)?.textContent?.trim() ?? '' }
}

describe('PV & weather view', () => {
  it('leads with live power, today and tomorrow, and compares PV now with the forecast', async () => {
    const { text } = open()
    await flush()
    expect(text('.pv-head .dim')).toBe('1,8 kW jetzt · heute 9 kWh erzeugt · Rest ≈ 3 kWh · morgen ≈ 16 kWh')
    expect(text('.wx-now')).toContain('Sonnig')
    expect(text('.wx-now')).toContain('Bewölkung 10 %')
    expect(text('.wx-now')).toContain('PV jetzt 1,8 kW · ≈ 90 % der Prognose')
    expect(text('.panel-heading .tag')).toBe('<provider> · Stand 14:29')
    expect(root.querySelector('[role=status]')).toBeNull()
  })

  it('shows backend text as text, never as markup', async () => {
    const { text } = open()
    await flush()
    expect(root.innerHTML).not.toContain('<provider>')
    expect(root.querySelector('provider')).toBeNull()
    expect(text('.panel-heading .tag')).toContain('<provider>')
  })

  it('shows the hourly strip with the folded night and explains a tapped hour', async () => {
    const { text } = open()
    await flush()
    const hours = [...root.querySelectorAll<HTMLButtonElement>('.wx-h')]
    expect(hours[0]?.classList.contains('now')).toBe(true)
    expect(hours[0]?.querySelector('.t')?.textContent).toBe('Jetzt')
    expect(root.querySelectorAll('.wx-gap')).toHaveLength(1)
    expect(text('.wx-gap')).toMatch(/^Nacht\s*Bewölkt · bis 4°\s*16:00–08:00$/)
    expect(hours[2]?.querySelector('.t')?.textContent).toBe('Do 08:00')
    expect(hours[2]?.querySelector('.cc')?.textContent).toBe('☁ 90 %')
    expect(text('.mode-detail')).toBe('Stunde antippen für Details. Balken: erwarteter PV-Ertrag in kWh pro Stunde.')
    hours[1]?.click()
    await flush()
    expect(text('.mode-detail')).toBe('15:00 · Sonnig, 7° · Bewölkung 10 % · Regenwahrscheinlichkeit 20 % · PV ≈ 2 kWh')
    expect(hours[1]?.getAttribute('aria-pressed')).toBe('true')
    expect(hours[0]?.getAttribute('aria-pressed')).toBe('false')
  })

  it('shows day cards with weather and the expected PV without a range', async () => {
    open()
    await flush()
    const days = root.querySelector('.wx-days')?.textContent ?? ''
    expect(days).toContain('Heute')
    expect(days).toContain('≈ 12 kWh')
    expect(days).toContain('9 kWh bereits erzeugt')
    expect(days).toContain('≈ 16 kWh')
    expect(days).toContain('1,2 mm Regen')
    expect(days).toContain('Prognose unvollständig')
  })

  it('lists plan effects from the backend with links into the matching view', async () => {
    const { text } = open({ values: { vehicle_name: 'ID.4', pv_effects: [
      { id: 'tomorrow_low', kwh: 6, today_kwh: 20 },
      { id: 'battery_grid', start: '2026-11-19T01:00:00Z', end: '2026-11-19T03:00:00Z', kwh: 6, price_ct: 24, soc: 90 },
      { id: 'car_grid', kwh: 25.4, start: '2026-11-19T01:00:00Z', price_ct: 24.1, vehicle_id: 'a/b' },
      { id: 'unknown_kind' },
    ] } })
    await flush()
    const rows = [...root.querySelectorAll('.list > .row, .list > a')]
    expect(rows).toHaveLength(3)
    expect(rows[0]?.textContent).toContain('Morgen ≈ 6 kWh PV erwartet, heute 20 kWh.')
    expect(rows[1]?.getAttribute('href')).toBe('#battery')
    expect(rows[1]?.textContent).toContain('6 kWh zu Ø 24 ct/kWh. Danach 90 %.')
    // The vehicle id is one encoded route segment.
    expect(rows[2]?.getAttribute('href')).toBe('#car/a%2Fb')
    expect(rows[2]?.textContent).toContain('ID.4 lädt aus dem Netz')
    expect(text('.pv-links')).toContain('Verlauf & Diagramme')
  })

  it('says when there is nothing special in the plan', async () => {
    const { text } = open()
    await flush()
    expect(text('.list')).toContain('nichts Besonderes')
  })

  it('keeps PV visible with missing weather and reloads only for a new PV forecast', async () => {
    const answer = forecastAnswer({ status: 'missing_source' })
    const request = vi.fn(async () => answer) as unknown as BackendRequest
    const { context, view, text } = open({ request })
    await flush()
    expect(text('[role=status]')).toMatch(/Wetter/)
    expect(root.querySelectorAll('.wx-h').length).toBeGreaterThan(0)
    view.update()
    await flush()
    expect(request).toHaveBeenCalledTimes(1)
    context.snapshot = { ...context.snapshot, forecast: [{ ...solarRows[0]!, solar: 500 }, ...solarRows.slice(1)] }
    view.update()
    await flush()
    expect(request).toHaveBeenCalledTimes(2)
  })

  it('does not reload for poll-driven totals or vehicle rows and keeps the strip while reloading', async () => {
    let release: (value: unknown) => void = () => undefined
    let calls = 0
    const request = vi.fn(async () => {
      calls++
      if (calls > 1) await new Promise(resolve => { release = resolve })
      return forecastAnswer()
    }) as unknown as BackendRequest
    const { context, view } = open({ request })
    await flush()
    const strip = root.querySelector('.wx-strip')?.innerHTML
    context.snapshot = { ...context.snapshot, pv_forecast_totals: [{ kwh: 2.9 }, { kwh: 16 }],
      forecast: [...solarRows, { time: new Date(NOW).toISOString(), end: new Date(NOW + 60_000).toISOString() }] }
    view.update()
    await flush()
    expect(calls).toBe(1)
    context.clock.now = NOW + RELOAD_MS
    view.update()
    await flush()
    expect(calls).toBe(2)
    expect(root.querySelector('.wx-strip')?.innerHTML).toBe(strip)
    expect(root.querySelector('[role=status]')).toBeNull()
    release(undefined)
    await flush()
    expect(root.querySelectorAll('.wx-h').length).toBeGreaterThan(0)
  })

  it('reports unavailable weather after a failed load and ignores a late older answer', async () => {
    let resolveFirst: (value: unknown) => void = () => undefined
    const answers: Array<Promise<unknown>> = [new Promise(resolve => { resolveFirst = resolve }), Promise.reject(new Error('offline'))]
    const request = vi.fn(() => answers.shift()) as unknown as BackendRequest
    const { view, text } = open({ request })
    view.open()
    await flush()
    expect(text('[role=status]')).toMatch(/nicht verfügbar/i)
    resolveFirst(forecastAnswer())
    await flush()
    expect(text('[role=status]')).toMatch(/nicht verfügbar/i)
  })

  it('discards answers after the view is closed', async () => {
    let resolve: (value: unknown) => void = () => undefined
    const request = vi.fn(() => new Promise(done => { resolve = done })) as unknown as BackendRequest
    const { view } = open({ request })
    view.close()
    resolve(forecastAnswer())
    await flush()
    expect(root.querySelectorAll('.wx-h')).toHaveLength(0)
  })

  it('renders the same structure in English', async () => {
    const { text } = open({ code: 'en' })
    await flush()
    expect(text('.pv-head .dim')).toMatch(/^1\.8 kW now · 9 kWh generated today/)
    expect(text('.wx-days')).toContain('Today')
    expect(text('.wx-gap')).toContain('Night')
  })

})
