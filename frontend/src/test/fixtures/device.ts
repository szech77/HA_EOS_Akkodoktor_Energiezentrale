/** Installation snapshot and history around 2026-11-16 12:00 UTC (13:00 in Berlin). */
import type { PanelHistory } from '@/types/device'

export const NOW = Date.parse('2026-11-16T12:00:00Z')
const MINUTE = 60_000
const HOUR = 60 * MINUTE
const iso = (ms: number) => new Date(ms).toISOString()

/** Forecast slots of one hour from now on. */
const slot = (hours: number, values: Record<string, number>) => ({ time: iso(NOW + hours * HOUR), end: iso(NOW + (hours + 1) * HOUR), ...values })

export function snapshot(values: Record<string, unknown> = {}) {
  return {
    zone: 'Europe/Berlin',
    vehicle_name: 'ID.4',
    live: {
      time: iso(NOW), solar: 4200, grid: -800, battery: 1500, battery_soc: 62, house: 900, house_total: 1900, heat: 1000, car: 0,
      car_soc: 55, battery_mode: 'NON_EXPORT', battery_control: 'applied', car_mode: 'IDLE', car_connected: true, soc_source: 'vehicle', price: 31.2,
    },
    settings: { pv: true, fast: false, phase_auto: true, pv_target_soc: 80, target_soc: 90 },
    charge_target_soc: 90,
    features: {},
    pv_today_kwh: 12.4,
    pv_forecast_totals: [
      { kwh: 6, total_kwh: 18.4, includes_measured: true, complete: true },
      { kwh: 21, total_kwh: 21, complete: true },
      { kwh: null, total_kwh: null },
    ],
    forecast: [slot(0, { solar: 4000, battery: 1200, battery_soc: 64, price: 30, house_total: 2000 }), slot(1, { solar: 3000, battery: 800, battery_soc: 70, price: 28, house_total: 1800 })],
    mode_timeline: {
      battery: [
        { start: NOW - 6 * HOUR, end: NOW, mode: 'SELF_CONSUMPTION', kind: 'history' },
        { start: NOW, end: NOW + 4 * HOUR, mode: 'NON_EXPORT', kind: 'plan' },
      ],
    },
    upcoming_plan: { battery: [{ time: iso(NOW + 4 * HOUR), mode: 'SELF_CONSUMPTION' }] },
    ...values,
  }
}

export function history(values: Partial<PanelHistory> = {}): PanelHistory {
  return {
    local: [
      { time: iso(NOW - 2 * MINUTE), solar: 4100, battery: 1400, battery_soc: 61, grid: -700, price: 31 },
      { time: iso(NOW - MINUTE), solar: 4200, battery: 1500, battery_soc: 62, grid: -800, price: 31.2 },
    ],
    influx: [],
    ...values,
  }
}
