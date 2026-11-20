/** Vehicle data as the backend sends it, 2026-11-18 15:00 in Berlin; the plan comes from charge_view.py. */
import { backend } from '@/test/backend'
import type { ChargeGoal, ChargePlan, VehicleData } from '@/types/car'

export const NOW = Date.parse('2026-11-18T14:00:00Z')
const HOUR = 3_600_000
const iso = (ms: number) => new Date(ms).toISOString()
const row = (hours: number, car: number, soc: number, { grid = 0, price = 30, solar = 0, length = 1 } = {}) =>
  ({ time: iso(NOW + hours * HOUR), end: iso(NOW + (hours + length) * HOUR), car, car_soc: soc, grid, price, solar, house_total: 500 })
const forecast = [row(0, 3700, 40, { solar: 5000 }), row(1, 0, 47.4, { price: 36 }), row(2, 0, 47.4, { price: 36 }), row(3, 0, 47.4, { price: 36 }),
  row(4, 7400, 47.4, { grid: 7900, price: 24 }), row(5, 7400, 62.2, { grid: 7900, price: 24 }), row(6, 3700, 77, { grid: 4200, price: 24, length: 0.5 }),
  row(6.5, 0, 80.7, { price: 25, length: 1.5 })]

/** Charge plan of the backend for the given vehicle inputs (fast charging, errors, read-only …). */
export function chargePlan(values: Record<string, unknown> = {}): ChargePlan {
  const data = {
    armed: true, live: { car_soc: 40, car_connected: true }, charge_target_soc: 80, charge_departure: iso(NOW + 8 * HOUR),
    charge_limits: { capacity_wh: 50000, efficiency: 1, maximum_w: 11000, max_current_a: 16, phases: null },
    vehicle_forecast_source: 'eos', settings: { fast: false }, errors: {}, plan_generated_at: iso(NOW - 2 * 60000), forecast, ...values,
  }
  return backend<ChargePlan>('chargePlan', data, { now: NOW, pv_price_ct: 8 })
}

export const goal: ChargeGoal = {
  id: 'morning', active: true, schedule: 'weekly', target_soc: 72, departure_time: '07:45', weekdays: [0, 2], holidays: true,
  next_departure: '2026-11-20T06:45:00Z', selected: true,
}

export function vehicle(id: string, name: string, values: Partial<VehicleData> = {}): VehicleData {
  return {
    id,
    name,
    live: { car: 3700, car_soc: 40, car_mode: 'CHARGING', car_connected: true, phases: 1, soc_source: 'vehicle', car_range_per_soc: 4 },
    settings: { pv: true, fast: false, phase_auto: true, pv_target_soc: 70, target_soc: 80 },
    charge_target_soc: 80,
    charge_plan: chargePlan(),
    charge_plan_view: [{ ...goal, id: `${id}_goal` }],
    ...values,
  }
}

/** A fleet of two vehicles; the second id needs URL encoding. */
export function fleet(first: Partial<VehicleData> = {}) {
  return {
    zone: 'Europe/Berlin',
    live: {},
    vehicles: [
      vehicle('id4', 'VW ID.4', first),
      vehicle('a/b', 'Leapmotor', { live: { car: null, car_soc: 76, car_mode: 'NON_EXPORT', car_connected: false }, display: { car: { value: 2100 } } }),
    ],
  }
}
