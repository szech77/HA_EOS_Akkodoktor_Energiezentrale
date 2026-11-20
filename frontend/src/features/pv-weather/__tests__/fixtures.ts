/** Backend-shaped data (as pv_view.py prepares it) for 2026-11-18 14:30 in Berlin. */
import type { PanelSnapshot } from '@/host/types'
import type { WeatherForecast } from '../types'

export const NOW = Date.parse('2026-11-18T13:30:00Z')
const HOUR = 3_600_000
const iso = (ms: number) => new Date(ms).toISOString()
const TOP = Date.parse('2026-11-18T13:00:00Z')

export const solarRows = Array.from({ length: 40 }, (_, index) => {
  const local = (14 + index) % 24
  return { time: iso(TOP + index * HOUR), end: iso(TOP + (index + 1) * HOUR), solar: local >= 8 && local < 16 ? 2000 : 0 }
})

export function snapshot(values: Partial<PanelSnapshot> = {}): PanelSnapshot {
  return {
    zone: 'Europe/Berlin',
    live: { solar: 1800, weather: { condition: 'sunny', temperature: 7, unit: '°C' } },
    pv_today_kwh: 9,
    pv_forecast_totals: [{ kwh: 3 }, { kwh: 16 }],
    pv_now: { power_w: 1800, ratio: 0.9 },
    pv_effects: [],
    forecast: solarRows,
    ...values,
  }
}

const hour = (offset: number, values: Record<string, unknown> = {}) => ({
  kind: 'hour' as const,
  start: iso(TOP + offset * HOUR),
  end: iso(TOP + (offset + 1) * HOUR),
  pv_kwh: 2,
  condition: 'sunny',
  temperature: 7,
  cloud_coverage: 10,
  precipitation: 0,
  precipitation_probability: 20,
  ...values,
})

export function forecastAnswer(values: Partial<WeatherForecast> = {}): WeatherForecast {
  return {
    status: 'available',
    source: '<provider>',
    fetched_at: iso(NOW - 60_000),
    hours: [
      hour(0, { now: true, pv_kwh: 1 }),
      hour(1),
      // 16:00 local until 08:00 local next day.
      { kind: 'night', start: iso(TOP + 2 * HOUR), end: iso(TOP + 18 * HOUR), condition: 'cloudy', low: 4 },
      hour(18, { condition: 'cloudy', cloud_coverage: 90 }),
      hour(19, { condition: 'cloudy', cloud_coverage: 90 }),
    ],
    days: [
      { date: '2026-11-18', today: true, pv_kwh: 12, measured_kwh: 9, complete: true, condition: 'sunny', high: 8, low: 2 },
      { date: '2026-11-19', pv_kwh: 16, complete: true, condition: 'cloudy', high: 9, low: 3, precipitation: 1.2 },
      { date: '2026-11-20', pv_kwh: null, complete: false, condition: null },
    ],
    ...values,
  }
}
