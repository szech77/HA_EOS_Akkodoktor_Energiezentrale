/**
 * Energy flow of the overview: where each node sits, how its wire runs and what it shows.
 * Pure functions on backend values; the component only draws the result.
 */
import type { Host } from '@/types/host'
import type { DeviceSnapshot, RetainedValue } from '@/types/device'
import type { OverviewSnapshot } from '@/types/overview'
import { consumerEnabled, vehicleName } from '@/utils/devicePage'
import { isNumber, type Format } from '@/utils/format'

export type FlowKey = 'solar' | 'grid' | 'battery' | 'house' | 'car' | 'heat'

const LEFT: readonly FlowKey[] = ['solar', 'grid', 'battery']
const NAMES: Readonly<Record<FlowKey, string>> = { solar: 'node.solar', grid: 'node.grid', battery: 'node.battery', house: 'node.house', car: 'node.car', heat: 'device.heat' }
const LINKS: Readonly<Record<FlowKey, string>> = { solar: '#usage/pv', grid: '#usage/grid', battery: '#battery', house: '#usage/house', car: '#car', heat: '#usage/heat' }

/** One node of the diagram: a device, or one vehicle of the vehicle list. */
export interface FlowEntry {
  readonly id: string
  readonly key: FlowKey
  readonly side: 'l' | 'r'
  readonly href: string
  /** The vehicle's own data for a vehicle of the list. */
  readonly vehicle?: (OverviewSnapshot & { readonly id?: string; readonly name?: string }) | undefined
  readonly x: number
  readonly y: number
  /** Wire from the node into the hub. */
  readonly d: string
}

export interface FlowLayout {
  readonly entries: readonly FlowEntry[]
  /** Height of the diagram in px: room for every consumer row. */
  readonly height: number
  /** All wires as one path, drawn under the pulses. */
  readonly wires: string
}

/** Vehicle bars and battery bars fill in the same 20 % steps; null hides them. */
export const socBars = (soc: unknown): number | null => (isNumber(soc) && soc >= 0 && soc <= 100 ? Math.ceil(soc / 20) : null)

/** Fill of a power ring: |power| against the reference power; null without a usable reference. */
export function powerFraction(watts: unknown, maximum: unknown): number | null {
  if (!isNumber(watts) || !isNumber(maximum) || maximum <= 0) return null
  return Math.max(0, Math.min(1, Math.abs(watts) / maximum))
}

/** A vehicle (or the fleet: any of its vehicles) is present unless the backend says it is not connected. */
export function vehicleActive(source: Pick<DeviceSnapshot, 'vehicles' | 'live'>): boolean {
  if (source.vehicles?.length) return source.vehicles.some(vehicle => vehicleActive(vehicle as DeviceSnapshot))
  return source.live?.car_connected !== false
}

/**
 * Sources left, consumers right; equal counts share the same rows and mirrored wires. Narrow
 * screens spread the columns outwards so the diagram uses the width.
 */
export function flowLayout(snapshot: OverviewSnapshot, narrow: boolean): FlowLayout {
  const vehicles = consumerEnabled(snapshot, 'car') ? snapshot.vehicles ?? [] : []
  const enabled = (key: FlowKey) => consumerEnabled(snapshot, key) && !(key === 'car' && vehicles.length)
  const device = (key: FlowKey) => ({ id: key, key, href: LINKS[key] })
  const left = LEFT.filter(enabled).map(device)
  const cars = vehicles.map(vehicle => ({ id: `car/${vehicle.id ?? ''}`, key: 'car' as const, href: `#car/${encodeURIComponent(vehicle.id ?? '')}`, vehicle: vehicle as FlowEntry['vehicle'] }))
  const right = [
    ...(enabled('house') ? [device('house')] : []),
    ...(vehicles.length ? cars : enabled('car') ? [device('car')] : []),
    ...(enabled('heat') ? [device('heat')] : []),
  ]
  const row = (index: number, count: number) => Math.round((index + 0.5) * 1000 / count) / 10
  const outer = narrow ? 17 : 30
  const edge = narrow ? 41 : 44
  const bend = (value: number) => Math.round(value * 10) / 10
  const near = bend(outer + (edge - outer) * 0.57)
  const far = bend(100 - outer - (100 - outer - (100 - edge)) * 0.57)
  const entries: FlowEntry[] = [
    ...left.map((entry, index) => {
      const y = row(index, left.length)
      // The battery wire runs from the hub: charging is positive.
      const d = entry.key === 'battery' ? `M${edge} 50 Q${near} ${y} ${outer} ${y}` : y === 50 ? `M${outer} 50 H${edge}` : `M${outer} ${y} Q${near} ${y} ${edge} 50`
      return { ...entry, side: 'l' as const, x: outer, y, d }
    }),
    ...right.map((entry, index) => {
      const y = row(index, right.length)
      return { ...entry, side: 'r' as const, x: 100 - outer, y, d: y === 50 ? `M${100 - edge} 50 H${100 - outer}` : `M${100 - edge} 50 Q${far} ${y} ${100 - outer} ${y}` }
    }),
  ]
  return { entries, height: Math.max(360, right.length * 144), wires: entries.map(entry => entry.d).join(' ') }
}

export function createFlowNodes(host: Host, format: Format) {
  const { t } = host
  const percent = (value: number) => `${host.decimal(value)} %`
  return {
    /** Name, value, age, SoC, ring, problem flag and pulse of one node. */
    node(entry: FlowEntry, snapshot: OverviewSnapshot) {
      const { key, vehicle } = entry
      const source = vehicle ?? snapshot
      const live = source.live
      const name = vehicle ? vehicle.name ?? '' : t(NAMES[key], { vehicle: vehicleName(snapshot) })
      const inactiveCar = key === 'car' && !vehicleActive(source)
      const inactiveGrid = key === 'grid' && snapshot.power_supply?.grid_active === false
      const retained: RetainedValue | null = source.flow_display?.[key] ?? source.display?.[key] ?? null
      const current = live[key]
      const stale = !inactiveGrid && isNumber(retained?.value) && Boolean(retained?.transition_held || retained?.aligned || !isNumber(current))
      const value = inactiveCar || inactiveGrid ? null : stale ? (retained?.value as number) : isNumber(current) ? current : null
      const socKey = `${key}_soc`
      const liveSoc = live[socKey]
      const soc = source.flow_display?.[socKey]?.value ?? (isNumber(liveSoc) ? liveSoc : source.display?.[socKey]?.value)
      const status = inactiveCar ? t(live.car_available === false ? 'vehicle.unavailable' : 'vehicle.disconnected') : ''
      const low = key === 'battery' && snapshot.battery_low === true
      const age = inactiveGrid ? t('power_supply.backup')
        : stale && retained ? t(retained.transition_held ? 'metric.waiting_car_power' : retained.aligned ? 'metric.aligned_age' : (retained as { estimated?: boolean }).estimated ? 'metric.estimated_age' : 'metric.last_report_age', { minutes: Math.ceil((retained.age_s ?? 0) / 60) })
          : ''
      const showAge = !inactiveCar && (inactiveGrid || (stale && !(retained?.aligned && (retained.age_s ?? 0) < 10)))

      // Power ring: PV, battery, car and – with a configured load sensor – the heat pump.
      const ring = ['solar', 'battery', 'car'].includes(key) || (key === 'heat' && snapshot.heat_load_configured === true)
      const reference = source.power_reference ?? {}
      const heatLoad = snapshot.live['heat_load']
      const fraction = !ring ? null : key === 'heat'
        ? (isNumber(heatLoad) ? Math.max(0, Math.min(1, heatLoad)) : null)
        : powerFraction(value, reference[key === 'battery' ? (isNumber(value) && value < 0 ? 'battery_discharge' : 'battery_charge') : key])
      const ringLabel = ring ? (fraction === null ? t('ring.unknown') : t('ring.load', { percent: host.decimal(fraction * 100) })) : ''

      const problem = snapshot.node_problems?.[vehicle ? `car/${vehicle.id ?? ''}` : key] ?? null
      const direction = !value ? '' : key === 'grid' ? t(value < 0 ? 'metric.export' : 'metric.import') : key === 'battery' ? t(value < 0 ? 'metric.discharging' : 'mode.charging') : ''
      const socText = (key === 'battery' || key === 'car') && isNumber(soc) ? [`${t('chart.soc')} ${percent(soc)}`, low ? t('battery.minimum_reached') : ''] : []
      const label = [name, inactiveGrid ? t('power_supply.backup') : inactiveCar ? status : format.power(value), direction, ...socText, ringLabel, problem ? t(`flow.problem_${problem}`) : '']

      // One shared power scale keeps sources and consumers comparable; square-root scaling keeps small loads visible.
      const magnitude = isNumber(value) ? Math.abs(value) : 0
      const intensity = Math.sqrt(Math.min(1, magnitude / 11000))
      const length = 2 + 6 * intensity
      return {
        name: socBars(soc) !== null ? `${name} · ${percent(soc as number)}` : name,
        value: inactiveCar ? '' : (stale && (retained as { estimated?: boolean }).estimated ? '≈ ' : '') + format.power(value),
        hideValue: inactiveCar,
        age: showAge ? age : '',
        title: [vehicle?.name ?? '', status, age, ringLabel].filter(Boolean).join(' · '),
        label: label.filter(Boolean).join(' · '),
        inactiveCar,
        inactiveGrid,
        low,
        bars: key === 'battery' ? (isNumber(soc) && soc >= 0 && soc <= 100 ? Math.ceil(soc / 20) : 0) : socBars(soc),
        ring,
        fraction,
        problem,
        pulse: {
          inactive: !isNumber(value) || Math.abs(value) < 10,
          reverse: isNumber(value) && value < 0,
          style: {
            '--speed': `${Math.max(1.4, 5 - magnitude / 2200)}s`,
            '--pulse-width': `${(3 + 9 * intensity).toFixed(2)}px`,
            '--pulse-dash': `${length.toFixed(2)} ${(100 - length).toFixed(2)}`,
          },
        },
      }
    },
  }
}

export type FlowNodes = ReturnType<typeof createFlowNodes>
export type FlowNodeView = ReturnType<FlowNodes['node']>
