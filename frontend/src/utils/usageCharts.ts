/**
 * Chart models of the report pages: SVG geometry from the backend's bins and power profile.
 * Components only draw these models; positions follow the period's calendar slots, so a 23- or
 * 25-hour day keeps its real hours and a month keeps all of its days.
 */
import type { BalanceBin, Bin, ConsumerEntry, Period, PowerProfile, ProfilePoint, PvForecast, Report, Source } from '@/types/usage'
import { isNumber } from '@/utils/format'
import { PV_FLOWS, PV_GAPS, SOURCE_COLORS, type UsageText } from '@/utils/usage'

export interface Slot {
  /** Bin time: UTC hour (day), date (month) or month (year). */
  readonly key: string
  /** Date a click drills into. */
  readonly date: string
  readonly label: string
}

export interface Shape {
  readonly x: number
  readonly y: number
  readonly width: number
  readonly height: number
  readonly color: string
  readonly forecast?: boolean
}

export interface BinGroup {
  readonly date: string
  readonly tooltip: string
  /** Bars carry a native title; the power chart shows its pointer readout instead. */
  readonly title: boolean
  readonly shapes: readonly Shape[]
  readonly hit: { readonly x: number; readonly y: number; readonly width: number; readonly height: number }
}

export interface HoverPoint {
  readonly x: number
  readonly row: ProfilePoint & { readonly forecast?: number | undefined }
}

export interface ChartModel {
  readonly width: number
  readonly height: number
  readonly label: string
  readonly left: number
  readonly right: number
  readonly top: number
  readonly bottom: number
  readonly axis: readonly { readonly y: number; readonly label: string; readonly strong: boolean }[]
  readonly areas: readonly { readonly points: string; readonly color: string }[]
  readonly forecastLine: string | null
  readonly groups: readonly BinGroup[]
  readonly labels: readonly { readonly x: number; readonly y: number; readonly text: string }[]
  /** Power chart only: points of the pointer readout. */
  readonly hover: { readonly key: string; readonly reach: number; readonly points: readonly HoverPoint[] } | null
}

export interface Viewport {
  readonly width: number
}

const HEIGHT = 240
const LEFT = 44
const RIGHT = 12
const TOP = 18
const BOTTOM = 38
const HOUR = 3_600_000

const chartWidth = (viewport: Viewport) => Math.max(280, Math.min(1000, viewport.width - 100))

export function slotsOf(report: Report | null, period: Period, locale: string, zone: string | undefined): Slot[] {
  if (!report) return []
  if (period === 'day') {
    // Server bins carry actual UTC hours: repeated DST hours stay distinct.
    const keys = report.hours ?? [...new Set(Object.values(report.consumers).flatMap(item => item.bins.map(row => row.time)))].sort()
    const format = new Intl.DateTimeFormat(locale, { timeZone: zone, hour: '2-digit', minute: '2-digit', timeZoneName: 'short' })
    return keys.map(key => ({ key, date: report.date, label: format.format(new Date(key)) }))
  }
  const rows: Slot[] = []
  const end = new Date(`${report.end}T12:00:00Z`)
  const month = new Intl.DateTimeFormat(locale, { month: 'short', timeZone: 'UTC' })
  for (const cursor = new Date(`${report.date}T12:00:00Z`); cursor < end; period === 'year' ? cursor.setUTCMonth(cursor.getUTCMonth() + 1) : cursor.setUTCDate(cursor.getUTCDate() + 1)) {
    const date = cursor.toISOString().slice(0, 10)
    rows.push({ key: period === 'year' ? date.slice(0, 7) : date, date, label: period === 'year' ? month.format(cursor) : String(cursor.getUTCDate()) })
  }
  return rows
}

/**
 * Power profile of a day report for one page; null when the page has no profile points. The PV
 * page also draws when only the forecast exists, e.g. early in the morning.
 */
export function profileOf(report: Report | null, period: Period, key: string): PowerProfile | null {
  const profile = period === 'day' ? report?.power_profile ?? null : null
  const points = (profile?.points ?? []).filter(point => (key === 'grid' ? point.grid : key === 'pv' ? isNumber(point.solar) : point[key]))
  if (key === 'pv' && period === 'day' && (points.length || report?.pv_forecast?.points?.length)) return { ...(profile ?? {}), points }
  return points.length && profile ? { ...profile, points } : null
}

export function createUsageCharts(text: UsageText, host: { readonly t: (key: string) => string; readonly decimal: (value: number, digits?: number) => string; readonly locale: () => string }, zone: () => string | undefined) {
  const { t, decimal } = host
  const { energy, money, costWithPrice } = text

  const labelsOf = (slots: readonly Slot[], step: number, viewport: Viewport) => {
    const every = Math.max(1, Math.ceil(slots.length / (viewport.width < 600 ? 5 : 10)))
    return slots.flatMap((slot, index) => (index % every === 0 ? [{ x: LEFT + (index + 0.5) * step, y: HEIGHT - 12, text: slot.label }] : []))
  }
  const frame = (width: number, label: string, height = HEIGHT) => ({ width, height, label, left: LEFT, right: RIGHT, top: TOP, bottom: BOTTOM })

  const binTooltip = (row: Bin, slot: Slot) => `${slot.label} · ${energy(row.kwh)} · ${costWithPrice(row)}\n${Object.entries(row.sources)
    .map(([source, item]) => `${t(`billing.${source}`)}: ${energy(item?.kwh ?? 0)} · ${costWithPrice(item)}`).join('\n')}`
  const gridTooltip = (row: BalanceBin, slot: Slot) => {
    const amounts = isNumber(row.grid_import_eur) ? ` (${money(row.grid_import_eur)}${row.cost_partial ? ` ${t('billing.known_portion')}` : ''})` : ''
    const credit = isNumber(row.export_eur) ? ` (+${money(row.export_eur)})` : ''
    return `${slot.label} · ${t('usage.import')} ${energy(row.grid_import_kwh ?? 0)}${amounts} · ${t('usage.feed_in')} ${energy(row.export_kwh ?? 0)}${credit}`
  }
  const parts = <K extends string>(values: Readonly<Partial<Record<K, number>>> | undefined, names: readonly (readonly [K, string])[]) =>
    names.filter(([key]) => (values?.[key] ?? 0) > 0.005)
  const pvTooltip = (row: BalanceBin | undefined, slot: Slot, forecast: PvForecast | null | undefined) => {
    const ahead = forecast?.bins?.find(item => item.time === slot.key)?.kwh
    const flows = parts(row?.pv_flow, PV_FLOWS).map(([key]) => `${t(`usage.pv_to_${key}`)} ${energy(row?.pv_flow?.[key] ?? 0)}`).join(' · ')
    const gaps = parts(row?.pv_gap, PV_GAPS).map(([key]) => `${t(`usage.pv_gap_${key}`)} ${energy(row?.pv_gap?.[key] ?? 0)}`).join(' · ')
    return [slot.label, row ? `${t('usage.pv_produced')} ${energy(row.pv_kwh ?? 0)}${flows ? `: ${flows}` : ''}` : '',
      gaps ? `${t('usage.pv_uncovered')}: ${gaps}` : '', isNumber(ahead) && ahead > 0 ? `${t('usage.pv_forecast')} ${energy(ahead)}` : ''].filter(Boolean).join('\n')
  }

  /** Ticks at zero, the extremes and their halves; ticks closer than 14 px to zero are dropped. */
  const signedTicks = (maximum: number, minimum: number, y: (value: number) => number) =>
    [0, maximum, maximum / 2, minimum, minimum / 2].filter((value, index) => index === 0 || Math.abs(y(value) - y(0)) >= 14)

  /** Energy (kWh) or costs (€) per slot as stacked source bars. */
  function consumption(entry: ConsumerEntry | undefined, slots: readonly Slot[], cost: boolean, viewport: Viewport): ChartModel | null {
    const rows = entry?.bins ?? []
    if (!rows.length) return null
    const width = chartWidth(viewport)
    const value = (item: { kwh: number; cost_eur?: number | null | undefined } | undefined) => (cost ? item?.cost_eur ?? 0 : item?.kwh ?? 0)
    const sums = rows.map(row => Object.values(row.sources).reduce((sum, item) => sum + Math.max(0, value(item)), 0))
    const minimum = cost ? Math.min(0, ...rows.map(row => Object.values(row.sources).reduce((sum, item) => sum + Math.min(0, value(item)), 0))) : 0
    const maximum = Math.max(0.01, ...sums)
    const span = maximum - minimum
    const plot = HEIGHT - TOP - BOTTOM
    const y = (amount: number) => TOP + ((maximum - amount) / span) * plot
    const step = (width - LEFT - RIGHT) / Math.max(1, slots.length)
    const barWidth = Math.max(1, step * 0.7)
    return {
      ...frame(width, t(cost ? 'billing.cost_chart' : 'billing.energy_chart')),
      axis: Array.from({ length: 5 }, (_, index) => {
        const tick = minimum + (span * index) / 4
        return { y: y(tick), label: decimal(tick, cost && span < 10 ? 2 : 1), strong: false }
      }),
      areas: [],
      forecastLine: null,
      groups: slots.flatMap((slot, index) => {
        const row = rows.find(item => item.time === slot.key)
        if (!row) return []
        const x = LEFT + (index + 0.5) * step
        let positive = 0
        let negative = 0
        const shapes = Object.entries(row.sources).map(([source, item]) => {
          const amount = value(item)
          const from = amount >= 0 ? positive : negative
          const to = from + amount
          if (amount >= 0) positive = to
          else negative = to
          return { x: x - barWidth / 2, y: Math.min(y(from), y(to)), width: barWidth, height: Math.max(0, Math.abs(y(from) - y(to))), color: SOURCE_COLORS[source as Source] }
        })
        return [{ date: slot.date, tooltip: binTooltip(row, slot), title: true, shapes, hit: { x: x - step / 2, y: TOP, width: step, height: plot } }]
      }),
      labels: labelsOf(slots, step, viewport),
      hover: null,
    }
  }

  /** Grid import above zero and feed-in below, as energy or its cost and credit. */
  function grid(rows: readonly BalanceBin[], slots: readonly Slot[], cost: boolean, viewport: Viewport): ChartModel | null {
    if (!rows.length) return null
    const width = chartWidth(viewport)
    const up = (row: BalanceBin) => Math.max(0, (cost ? row.grid_import_eur : row.grid_import_kwh) ?? 0)
    const down = (row: BalanceBin) => Math.max(0, (cost ? row.export_eur : row.export_kwh) ?? 0)
    const maximum = Math.max(0.01, ...rows.map(up))
    const minimum = -Math.max(0.01, ...rows.map(down))
    const span = maximum - minimum
    const plot = HEIGHT - TOP - BOTTOM
    const y = (value: number) => TOP + ((maximum - value) / span) * plot
    const step = (width - LEFT - RIGHT) / Math.max(1, slots.length)
    const barWidth = Math.max(1, step * 0.7)
    // A small feed-in (or import) squeezes its ticks against zero; drop ticks that would overlap.
    const apart = (a: number, b: number) => Math.abs(y(a) - y(b)) >= 14
    const ticks = [0, ...[maximum, minimum].flatMap(edge => [edge, edge / 2].filter(value => apart(value, 0) && (value === edge || apart(value, edge))))]
    return {
      ...frame(width, t(cost ? 'usage.grid_cost_chart' : 'usage.grid_chart')),
      axis: ticks.map(value => ({ y: y(value), label: decimal(Math.abs(value), cost && span < 10 ? 2 : 1), strong: value === 0 })),
      areas: [],
      forecastLine: null,
      groups: slots.flatMap((slot, index) => {
        const row = rows.find(item => item.time === slot.key)
        if (!row) return []
        const x = LEFT + (index + 0.5) * step
        return [{
          date: slot.date,
          tooltip: gridTooltip(row, slot),
          title: true,
          shapes: [
            { x: x - barWidth / 2, y: y(up(row)), width: barWidth, height: Math.max(0, y(0) - y(up(row))), color: SOURCE_COLORS.grid },
            { x: x - barWidth / 2, y: y(0), width: barWidth, height: Math.max(0, y(-down(row)) - y(0)), color: SOURCE_COLORS.pv },
          ],
          hit: { x: x - step / 2, y: TOP, width: step, height: plot },
        }]
      }),
      labels: labelsOf(slots, step, viewport),
      hover: null,
    }
  }

  /** PV production by use above zero, uncovered consumption below and the forecast ahead (dashed). */
  function pv(rows: readonly BalanceBin[], forecast: PvForecast | null | undefined, slots: readonly Slot[], viewport: Viewport): ChartModel | null {
    const ahead = forecast?.bins ?? []
    if (!rows.length && !ahead.length) return null
    const width = chartWidth(viewport)
    const height = 280
    const step = (width - LEFT - RIGHT) / Math.max(1, slots.length)
    const barWidth = Math.max(1, step * 0.7)
    const row = (key: string) => rows.find(item => item.time === key)
    const total = <K extends string>(values: Readonly<Partial<Record<K, number>>> | undefined, names: readonly (readonly [K, string])[]) =>
      names.reduce((sum, [key]) => sum + Math.max(0, values?.[key] ?? 0), 0)
    const expected = (key: string) => ahead.find(item => item.time === key)?.kwh ?? 0
    const maximum = Math.max(0.1, ...slots.map(slot => total(row(slot.key)?.pv_flow, PV_FLOWS) + expected(slot.key)))
    const minimum = -Math.max(0.1, ...slots.map(slot => total(row(slot.key)?.pv_gap, PV_GAPS)))
    const span = maximum - minimum
    const plot = height - TOP - BOTTOM
    const y = (value: number) => TOP + ((maximum - value) / span) * plot
    return {
      ...frame(width, t('usage.pv_chart'), height),
      axis: signedTicks(maximum, minimum, y).map(value => ({ y: y(value), label: decimal(Math.abs(value), 1), strong: value === 0 })),
      areas: [],
      forecastLine: null,
      groups: slots.flatMap((slot, index) => {
        const bin = row(slot.key)
        const coming = expected(slot.key)
        if (!bin && !(coming > 0)) return []
        const x = LEFT + (index + 0.5) * step
        const rect = (from: number, to: number, color: string): Shape =>
          ({ x: x - barWidth / 2, y: Math.min(y(from), y(to)), width: barWidth, height: Math.max(0, Math.abs(y(from) - y(to))), color })
        const shapes: Shape[] = []
        let stack = 0
        for (const [key, color] of PV_FLOWS) {
          const from = stack
          stack += Math.max(0, bin?.pv_flow?.[key] ?? 0)
          if (stack > from) shapes.push(rect(from, stack, color))
        }
        let below = 0
        for (const [key, color] of PV_GAPS) {
          const from = below
          below -= Math.max(0, bin?.pv_gap?.[key] ?? 0)
          if (below < from) shapes.push(rect(from, below, color))
        }
        if (coming > 0) shapes.push({ x: x - barWidth / 2, y: y(stack + coming), width: barWidth, height: Math.max(0, y(stack) - y(stack + coming)), color: SOURCE_COLORS.pv, forecast: true })
        return [{ date: slot.date, tooltip: pvTooltip(bin, slot, forecast), title: true, shapes, hit: { x: x - step / 2, y: TOP, width: step, height: plot } }]
      }),
      labels: labelsOf(slots, step, viewport).map(label => ({ ...label, y: height - 12 })),
      hover: null,
    }
  }

  /** Day view: the backend's power profile (short averages of the minute history) in kW as stacked areas. */
  function power(key: string, profile: PowerProfile, report: Report, slots: readonly Slot[], viewport: Viewport): ChartModel {
    const width = chartWidth(viewport)
    const step = (width - LEFT - RIGHT) / Math.max(1, slots.length)
    const starts = slots.map(slot => Date.parse(slot.key))
    const half = (profile.step_s ?? 120) * 500
    const gap = (profile.gap_s ?? 600) * 1000
    const position = (stamp: number) => {
      let index = 0
      for (let slot = starts.length - 1; slot >= 0; slot--) {
        if ((starts[slot] as number) <= stamp) {
          index = slot
          break
        }
      }
      return LEFT + (index + Math.min(1, Math.max(0, (stamp - (starts[index] ?? stamp)) / HOUR))) * step
    }
    const isGrid = key === 'grid'
    const isPv = key === 'pv'
    const kw = (value: unknown) => (isNumber(value) ? value : 0) / 1000
    const consumer = (point: ProfilePoint) => (point[key] ?? {}) as Partial<Record<Source, number>>
    const layers: { color: string; value: (point: ProfilePoint) => number }[] = isGrid
      ? [{ color: SOURCE_COLORS.grid, value: point => kw(point.grid?.import) }, { color: SOURCE_COLORS.pv, value: point => -kw(point.grid?.export) }]
      : isPv
        ? [...PV_FLOWS.map(([name, color]) => ({ color, value: (point: ProfilePoint) => kw(point.pv_flow?.[name]) })),
          ...PV_GAPS.map(([name, color]) => ({ color, value: (point: ProfilePoint) => -kw(point.pv_gap?.[name]) }))]
        : (Object.entries(SOURCE_COLORS) as [Source, string][]).map(([source, color]) => ({ color, value: (point: ProfilePoint) => kw(consumer(point)[source]) }))
    // PV forecast power (backend, from now on) as a dashed step line over the measured area.
    const ahead = isPv ? report.pv_forecast?.points ?? [] : []
    const forecastAt = (stamp: number) => ahead.find(item => Date.parse(item.time) <= stamp && stamp < Date.parse(item.end))?.w
    const rows: ProfilePoint[] = []
    const xs: (number | null)[] = []
    let previous: number | null = null
    for (const point of profile.points) {
      const stamp = Date.parse(point.time) + half
      if (previous !== null && stamp - previous > gap) xs.push(null)
      rows.push(point)
      xs.push(position(stamp))
      previous = stamp
    }
    const sums = rows.map(row => layers.reduce((sum, layer) => sum + Math.max(0, layer.value(row)), 0))
    const lows = rows.map(row => layers.reduce((sum, layer) => sum + Math.min(0, layer.value(row)), 0))
    const maximum = Math.max(0.1, ...sums, ...ahead.map(item => kw(item.w)))
    const minimum = Math.min(0, ...lows)
    const span = maximum - minimum
    const plot = HEIGHT - TOP - BOTTOM
    const y = (value: number) => TOP + ((maximum - value) / span) * plot
    const ticks = minimum < 0 ? signedTicks(maximum, minimum, y) : Array.from({ length: 5 }, (_, index) => minimum + (span * index) / 4)
    // Areas: layers stack in order, positive values upwards and negative ones downwards; a gap splits them.
    const segments: { x: number; stack: [number, number][] }[][] = []
    let current: { x: number; stack: [number, number][] }[] = []
    let rowIndex = 0
    for (const x of xs) {
      if (x === null) {
        if (current.length) segments.push(current)
        current = []
        continue
      }
      const row = rows[rowIndex++] as ProfilePoint
      let positive = 0
      let negative = 0
      current.push({
        x,
        stack: layers.map(layer => {
          const value = layer.value(row)
          const from = value >= 0 ? positive : negative
          const to = from + value
          if (value >= 0) positive = to
          else negative = to
          return [from, to]
        }),
      })
    }
    if (current.length) segments.push(current)
    const areas = layers.flatMap((layer, index) => segments.flatMap(segment => {
      let points = segment.map(item => ({ x: item.x, from: item.stack[index]?.[0] ?? 0, to: item.stack[index]?.[1] ?? 0 }))
      if (!points.some(point => Math.abs(point.to - point.from) > 1e-9)) return []
      // A single sample between gaps becomes a narrow plateau instead of a line.
      if (points.length === 1) {
        const only = points[0] as { x: number; from: number; to: number }
        const offset = (0.35 * step) / 30
        points = [{ ...only, x: only.x - offset }, { ...only, x: only.x + offset }]
      }
      const edge = points.map(point => `${point.x.toFixed(1)},${y(point.to).toFixed(1)}`)
      const base = [...points].reverse().map(point => `${point.x.toFixed(1)},${y(point.from).toFixed(1)}`)
      return [{ points: `${edge.join(' ')} ${base.join(' ')}`, color: layer.color }]
    }))
    const hours: readonly (Bin | BalanceBin)[] = isGrid || isPv ? report.balance?.bins ?? [] : report.consumers[key]?.bins ?? []
    const groups: BinGroup[] = slots.flatMap((slot, index) => {
      const row = hours.find(item => item.time === slot.key)
      if (!row && !isPv) return []
      const tooltip = isGrid ? gridTooltip(row as BalanceBin, slot) : isPv ? pvTooltip(row as BalanceBin | undefined, slot, report.pv_forecast) : binTooltip(row as Bin, slot)
      return [{ date: slot.date, tooltip, title: false, shapes: [], hit: { x: LEFT + index * step, y: TOP, width: step, height: plot } }]
    })
    const measuredXs = xs.filter((x): x is number => x !== null)
    const measured: HoverPoint[] = rows.map((row, index) => ({
      x: measuredXs[index] as number,
      row: isPv ? { ...row, forecast: forecastAt(Date.parse(row.time) + half) } : row,
    }))
    // Ahead of the measurements the PV readout follows the forecast in 15-minute steps.
    const last = rows.length ? Date.parse((rows.at(-1) as ProfilePoint).time) + half : -Infinity
    const future: HoverPoint[] = ahead.flatMap(item => {
      const out: HoverPoint[] = []
      for (let stamp = Date.parse(item.time); stamp < Date.parse(item.end); stamp += 900_000) {
        if (stamp > last) out.push({ x: position(stamp), row: { time: new Date(stamp).toISOString(), forecast: item.w } })
      }
      return out
    })
    return {
      ...frame(width, t(isGrid ? 'usage.grid_power_chart' : isPv ? 'usage.pv_power_chart' : 'usage.power_chart')),
      axis: ticks.map(value => ({ y: y(value), label: decimal(Math.abs(value), span < 3 ? 2 : 1), strong: value === 0 && minimum < 0 })),
      areas,
      forecastLine: ahead.length
        ? ahead.flatMap(item => [Date.parse(item.time), Date.parse(item.end)].map(stamp => `${position(stamp).toFixed(1)},${y(kw(item.w)).toFixed(1)}`)).join(' ')
        : null,
      groups,
      labels: labelsOf(slots, step, viewport),
      hover: { key, reach: Math.max(6, (step * (profile.gap_s ?? 600)) / 7200), points: [...measured, ...future] },
    }
  }

  /** Values of the profile point under the pointer. */
  function readout(point: HoverPoint['row'], key: string): { title: string; lines: [string, string, string][] } {
    const kw = (value: unknown) => `${decimal((isNumber(value) ? value : 0) / 1000, 2)} kW`
    const stamp = new Intl.DateTimeFormat(host.locale(), { timeZone: zone(), hour: '2-digit', minute: '2-digit' }).format(new Date(point.time))
    if (key === 'grid') return { title: stamp, lines: [[t('usage.import'), kw(point.grid?.import), SOURCE_COLORS.grid], [t('usage.feed_in'), kw(point.grid?.export), SOURCE_COLORS.pv]] }
    if (key === 'pv') {
      const measured = isNumber(point.solar)
      const watts = <K extends string>(values: Readonly<Partial<Record<K, number>>> | undefined, names: readonly (readonly [K, string])[], prefix: string): [string, string, string][] =>
        measured ? names.filter(([name]) => (values?.[name] ?? 0) > 5).map(([name, color]) => [t(prefix + name), `${point.source_estimated ? '≈ ' : ''}${kw(values?.[name])}`, color]) : []
      return {
        title: measured ? `${stamp} · PV ${kw(point.solar)}` : stamp,
        lines: [...watts(point.pv_flow, PV_FLOWS, 'usage.pv_to_'), ...watts(point.pv_gap, PV_GAPS, 'usage.pv_gap_'),
          ...(isNumber(point.forecast) ? [[t('usage.pv_forecast'), kw(point.forecast), 'transparent'] as [string, string, string]] : [])],
      }
    }
    const values = (point[key] ?? {}) as Partial<Record<Source, number>>
    const total = Object.values(values).reduce((sum, value) => sum + (value ?? 0), 0)
    return {
      title: `${stamp} · ${kw(total)}`,
      lines: (Object.entries(SOURCE_COLORS) as [Source, string][]).filter(([source]) => (values[source] ?? 0) > 0).map(([source, color]) => [t(`billing.${source}`), `${point.source_estimated ? '≈ ' : ''}${kw(values[source])}`, color]),
    }
  }

  return { consumption, grid, pv, power, readout }
}

export type UsageCharts = ReturnType<typeof createUsageCharts>
