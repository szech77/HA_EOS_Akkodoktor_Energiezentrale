/**
 * Time series of the device charts: 24 h of measurements and 24 h of forecast around "now".
 * Pure functions; the component only draws the result.
 */
import type { PanelHistory, SeriesRow } from '@/types/device'

export const DAY = 86_400_000
/** Measured samples further apart than this are not joined by a line (a gap). */
const ACTUAL_GAP = 360_000
const FORECAST_GAP = 3_600_000

export interface Point {
  readonly stamp: number
  readonly end: number
  readonly value: number
}

export interface SeriesSpec {
  readonly key: string
  readonly label: string
  readonly divisor: number
  /** Colour token of the panel (CSS variable name). */
  readonly color: string
  /** False hides the measured or the forecast part of this series. */
  readonly actual?: boolean
  readonly future?: boolean
}

export interface ChartSpec {
  readonly id: string
  readonly title: string
  readonly unit: string
  readonly series: readonly SeriesSpec[]
  readonly history: PanelHistory
  readonly forecast: readonly SeriesRow[]
  /** Footnote below the chart (e.g. how a vehicle forecast was made). */
  readonly note?: string
}

export interface Series extends Omit<SeriesSpec, 'actual' | 'future'> {
  readonly actual: readonly Point[]
  readonly future: readonly Point[]
}

export interface ChartModel {
  readonly series: readonly Series[]
  readonly min: number
  readonly max: number
  readonly paths: readonly { readonly d: string; readonly forecast: boolean; readonly color: string }[]
}

const finite = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value)

/** Samples of one key between start and end, sorted by time. */
export function points(rows: readonly SeriesRow[], key: string, start: number, end: number): Point[] {
  return rows.flatMap(row => {
    const stamp = Date.parse(row.time)
    const value = row[key]
    if (!Number.isFinite(stamp) || stamp < start || stamp > end || !finite(value)) return []
    return [{ stamp, end: Date.parse(row.end ?? ''), value }]
  }).sort((a, b) => a.stamp - b.stamp)
}

/** Influx rows only before the first local row with a value, then the local rows. */
export function measured(history: PanelHistory, key: string): SeriesRow[] {
  const influx = history.influx.filter(row => finite(row[key]))
  const local = history.local.filter(row => finite(row[key]))
  const first = Date.parse(local[0]?.time ?? '')
  return [...influx.filter(row => !first || Date.parse(row.time) < first), ...local]
}

/** Value under the pointer: the forecast slot containing the time, or the nearest measurement within 6 minutes. */
export function sampleAt(series: Series, stamp: number, now: number): { point: Point; forecast: boolean } | null {
  if (stamp > now) {
    const point = series.future.find(row => row.stamp <= stamp && stamp < row.end)
    return point ? { point, forecast: true } : null
  }
  let nearest: Point | null = null
  for (const point of series.actual) {
    if (!nearest || Math.abs(point.stamp - stamp) < Math.abs(nearest.stamp - stamp)) nearest = point
  }
  return nearest && Math.abs(nearest.stamp - stamp) <= ACTUAL_GAP ? { point: nearest, forecast: false } : null
}

/** Scale and paths of a chart; null without any value to draw. */
export function chartModel(spec: ChartSpec, now: number): ChartModel | null {
  const series: Series[] = spec.series.map(item => ({
    ...item,
    actual: item.actual === false ? [] : points(measured(spec.history, item.key), item.key, now - DAY, now),
    future: item.future === false ? [] : points(spec.forecast, item.key, now - DAY, now + DAY).filter(row => row.end > now),
  }))
  const numbers = series.flatMap(item => [...item.actual, ...item.future].map(row => row.value / item.divisor))
  if (!numbers.length) return null
  const key = spec.series[0]?.key ?? ''
  const min = key === 'price' ? Math.floor(Math.min(...numbers) - 1) : Math.min(0, ...numbers)
  const max = key.endsWith('_soc') ? 100 : Math.max(min + 1, Math.ceil(Math.max(...numbers) + (key === 'price' ? 1 : 0)))
  const curve = (rows: readonly Point[], item: Series, gap: number) => {
    let previous: number | undefined
    return rows.map(row => {
      const x = Math.max(0, Math.min(100, 50 + (row.stamp - now) * 50 / DAY))
      const y = (max - row.value / item.divisor) * 100 / (max - min)
      const command = previous !== undefined && row.stamp - previous <= gap ? 'L' : 'M'
      previous = row.stamp
      return `${command}${x.toFixed(3)},${y.toFixed(3)}`
    }).join(' ')
  }
  const paths = series.flatMap(item => [
    { d: curve(item.actual, item, ACTUAL_GAP), forecast: false, color: item.color },
    { d: curve(item.future, item, FORECAST_GAP), forecast: true, color: item.color },
  ])
  return { series, min, max, paths }
}
