/**
 * Content of the device pages from backend values: key figures, charts and the plan section.
 * Same rules as the former app.js detail view; nothing is calculated beyond presentation.
 */
import type { Host } from '@/types/host'
import type { DeviceKey, DeviceSnapshot, PanelHistory } from '@/types/device'
import type { VehicleData } from '@/types/car'
import type { ChartSpec, SeriesSpec } from '@/utils/chartSeries'
import { isNumber, type Format } from '@/utils/format'
import type { StateLabels } from '@/utils/modes'

export interface Card {
  readonly title: string
  readonly value: string
  readonly context: string
}

export interface PlanSection {
  readonly title?: string
  readonly text?: string
  /** Next EOS instructions; an empty list says that no valid plan exists. */
  readonly items?: readonly { readonly time: string; readonly mode: string }[]
}

/** Snapshot and history one page shows: the installation, or one vehicle merged over it. */
export interface PageData {
  readonly snapshot: DeviceSnapshot
  readonly history: PanelHistory
}

const NODES: readonly (readonly [DeviceKey, string])[] = [
  ['solar', 'node.solar'], ['grid', 'node.grid'], ['battery', 'node.battery'], ['house', 'node.house'], ['car', 'node.car'], ['heat', 'device.heat'],
]
const VEHICLE_FORECASTS = new Set(['eos', 'pv_estimate', 'fast_estimate', 'constant', 'unavailable'])

/** Car and heat pump can be switched off; their pages and figures then disappear. */
export const consumerEnabled = (snapshot: DeviceSnapshot, key: string) => !['car', 'heat'].includes(key) || snapshot.features?.[key] !== false

/** Name of the vehicle in texts such as "{vehicle} & Wallbox" (the panel's default name without one). */
export const vehicleName = (snapshot: DeviceSnapshot) => snapshot.vehicle_name || 'E-Auto'

export function createDevicePage(host: Host, format: Format, states: StateLabels) {
  const { t } = host

  function live(snapshot: DeviceSnapshot) {
    const value = (key: string) => snapshot.live[key]
    const retained = (key: string) => snapshot.flow_display?.[key] ?? snapshot.display?.[key] ?? null
    /** Live value, else the value the backend retained or aligned for display. */
    const displayed = (key: string): number | null | undefined => {
      const flow = snapshot.flow_display?.[key]?.value
      if (flow !== undefined && flow !== null) return flow
      const current = value(key)
      return isNumber(current) ? current : snapshot.display?.[key]?.value
    }
    return {
      displayed,
      power: (key: string) => (snapshot.flow_display?.[key] || (snapshot.display?.[key] && !isNumber(value(key))) ? '≈ ' : '') + format.power(displayed(key)),
      /** How old a retained value is; null for a fresh measurement. */
      age(key: string): string | null {
        const item = retained(key)
        if (!item || !(item.transition_held || item.aligned || !isNumber(value(key)))) return null
        const minutes = Math.ceil((item.age_s ?? 0) / 60)
        return t(item.transition_held ? 'metric.waiting_car_power' : item.aligned ? 'metric.aligned_age' : 'metric.last_report_age', { minutes })
      },
    }
  }

  const vehicleActive = (snapshot: DeviceSnapshot) =>
    snapshot.vehicles?.length ? snapshot.vehicles.some(vehicle => vehicle.live.car_connected !== false) : snapshot.live.car_connected !== false
  const vehicleStatus = (snapshot: DeviceSnapshot) => t(snapshot.live.car_available === false ? 'vehicle.unavailable' : 'vehicle.disconnected')

  function solarForecastCards(snapshot: DeviceSnapshot): Card[] {
    const titles = ['metric.pv_forecast_today', 'metric.pv_forecast_tomorrow', 'metric.pv_forecast_day_after']
    return (snapshot.pv_forecast_totals ?? []).slice(0, 3).map((row, index) => {
      const total = row.includes_measured
      return {
        title: t(titles[index] ?? 'metric.pv_forecast_day_after'),
        value: isNumber(row.total_kwh) ? `${total ? '≈ ' : ''}${host.decimal(row.total_kwh)} ${t('unit.kwh')}` : '—',
        context: !isNumber(row.kwh) ? t('metric.forecast_missing')
          : total ? t('metric.forecast_today_total') + (row.complete ? '' : ` · ${t('metric.forecast_partial')}`)
            : index === 0 ? t('metric.forecast_remaining_only') : row.complete ? t('metric.forecast_complete') : t('metric.forecast_partial'),
      }
    })
  }

  return {
    live,
    vehicleActive,

    /** Key figures of a device page; the energy page shows every enabled node. */
    cards(key: DeviceKey, { snapshot }: PageData): Card[] {
      const values = live(snapshot)
      if (key === 'energy') {
        return NODES.filter(([node]) => consumerEnabled(snapshot, node))
          .map(([node, label]) => ({ title: t(label, { vehicle: vehicleName(snapshot) }), value: values.power(node), context: values.age(node) ?? t('metric.measured') }))
      }
      const inactiveCar = key === 'car' && !vehicleActive(snapshot)
      const current: Card = {
        title: t('metric.current_power'),
        value: inactiveCar ? vehicleStatus(snapshot) : values.power(key),
        context: inactiveCar ? '' : values.age(key) ?? (key === 'car' ? states.state('mode', snapshot.live.car_control ?? (snapshot.live['car_status'] as string | undefined)) : t('metric.measured')),
      }
      const grid = values.displayed('grid')
      const extra: Record<Exclude<DeviceKey, 'energy'>, Card[]> = {
        solar: [
          { title: t('metric.pv_today'), value: isNumber(snapshot.pv_today_kwh) ? `${host.decimal(snapshot.pv_today_kwh)} ${t('unit.kwh')}` : '—', context: t('metric.available_intervals') },
          ...solarForecastCards(snapshot),
        ],
        grid: [{ title: t('metric.direction'), value: isNumber(grid) ? t(grid < 0 ? 'metric.export' : 'metric.import') : '—', context: t('metric.grid_connection') }],
        battery: [
          { title: t('chart.soc'), value: format.percentText(values.displayed('battery_soc')), context: t('metric.measured') },
          { title: t('metric.eos_mode'), value: states.mode(snapshot.live['battery_mode'] as string | undefined), context: states.state('mode', snapshot.live['battery_control'] as string | undefined) },
        ],
        house: [{ title: t('metric.house_total'), value: values.power('house_total'), context: t('metric.house_includes') }],
        car: [
          { title: t('chart.soc'), value: format.percentText(values.displayed('car_soc')), context: states.state('source', snapshot.live.soc_source) },
          { title: t('metric.target'), value: format.percentText(snapshot.charge_target_soc ?? snapshot.settings?.target_soc), context: snapshot.live.departure ? format.dateTime(snapshot.live.departure) : t('metric.no_departure') },
        ],
        heat: [],
      }
      return [current, ...extra[key]]
    },

    /** Charts of a device page: power with the PV curve where a plan uses it, SoC and price. */
    charts(key: DeviceKey, data: PageData): ChartSpec[] {
      const { snapshot, history } = data
      const forecast = snapshot.forecast ?? []
      const chart = (id: string, title: string, unit: string, series: SeriesSpec[], note?: string): ChartSpec =>
        ({ id, title, unit, series, history, forecast, ...(note ? { note } : {}) })
      const kw = t('unit.kw')
      const price = chart('price', t('chart.price'), t('unit.price'), [{ key: 'price', label: t('chart.price'), divisor: 1, color: 'heat' }])
      if (key === 'energy') {
        const names = Object.fromEntries(NODES.map(([node, label]) => [node, t(label, { vehicle: vehicleName(snapshot) })]))
        const flows: SeriesSpec[] = (['grid', 'battery', 'house', 'car', 'heat'] as const).filter(node => consumerEnabled(snapshot, node))
          .map(node => ({ key: node, label: names[node] ?? node, divisor: 1000, color: node, future: node !== 'house' }))
        return [
          chart('solar', t('chart.energy'), kw, [
            { key: 'solar', label: t('chart.solar'), divisor: 1000, color: 'solar' },
            ...flows,
            { key: 'house_total', label: t('chart.house_forecast'), divisor: 1000, color: 'house', actual: false },
          ], t('chart.energy_signs')),
          price,
        ]
      }
      const withPlan = key === 'battery' || key === 'car'
      const title = t(`chart.${key}`)
      const power = chart(key, title, kw, [
        { key, label: title, divisor: 1000, color: key },
        ...(withPlan ? [{ key: 'solar', label: t('chart.solar'), divisor: 1000, color: 'solar' }] : []),
      ])
      const result = [power]
      if (key === 'house') result.push(chart('house_total', t('chart.house_total'), kw, [{ key: 'house_total', label: t('chart.house_total'), divisor: 1000, color: 'house' }]))
      if (withPlan) {
        const source = snapshot.vehicle_forecast_source
        const note = key === 'car' && source && VEHICLE_FORECASTS.has(source) ? t(`forecast.vehicle_${source}`) : undefined
        result.push(chart(`${key}_soc`, t('chart.soc'), '%', [{ key: `${key}_soc`, label: t('chart.soc'), divisor: 1, color: key }], note))
      }
      if (key !== 'solar' && key !== 'house') result.push(price)
      return result
    },

    /** Fleet page: total charging power and the SoC of every vehicle with its own history and forecast. */
    fleetCharts({ snapshot, history }: PageData): ChartSpec[] {
      const total: ChartSpec = { id: 'car', title: t('fleet.total'), unit: t('unit.kw'), history, forecast: snapshot.forecast ?? [],
        series: [{ key: 'car', label: t('fleet.total'), divisor: 1000, color: 'car' }] }
      return [total, ...(snapshot.vehicles ?? []).map(vehicle => {
        const data = vehicle as VehicleData & { forecast?: DeviceSnapshot['forecast']; history?: DeviceSnapshot['history']; vehicle_forecast_source?: string }
        const title = `${vehicle.name ?? ''} · ${t('chart.soc')}`
        const source = data.vehicle_forecast_source
        return {
          id: `vehicle_soc_${vehicle.id ?? ''}`,
          title,
          unit: '%',
          series: [{ key: 'car_soc', label: title, divisor: 1, color: 'car' }],
          history: { local: history.vehicles?.[vehicle.id ?? ''] ?? data.history ?? [], influx: [] },
          forecast: data.forecast ?? [],
          ...(source && VEHICLE_FORECASTS.has(source) ? { note: t(`forecast.vehicle_${source}`) } : {}),
        }
      })]
    },

    /** EOS instructions for battery and car; a short forecast note for house, heat pump and energy. */
    plan(key: DeviceKey, { snapshot }: PageData): PlanSection | null {
      if (key === 'energy') return { title: t('plan.forecast'), text: t('chart.energy_forecast_note') }
      if (key === 'heat') return { title: t('plan.forecast'), text: t('plan.no_heat') }
      if (key === 'house') return { title: t('plan.forecast'), text: t('plan.house_total') }
      if (key !== 'battery' && key !== 'car') return null
      return {
        title: t('plan.next'),
        items: (snapshot.upcoming_plan?.[key] ?? []).map(item => ({ time: format.dateTime(item.time), mode: states.mode(item.mode) })),
      }
    },
  }
}

export type DevicePage = ReturnType<typeof createDevicePage>
