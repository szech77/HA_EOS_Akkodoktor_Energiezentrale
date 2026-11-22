/** Backend data of the device pages (live values, history, forecast rows and EOS mode timeline). */
import type { CarSnapshot } from '@/types/car'

/** Device pages with their own route; "car" also has the vehicle pages "car/<id>". */
export type DeviceKey = 'solar' | 'grid' | 'battery' | 'house' | 'heat' | 'car' | 'energy'

/** One row of the local/Influx history or of the EOS forecast: a time slot with values by key. */
export interface SeriesRow {
  readonly time: string
  readonly end?: string
  readonly [key: string]: unknown
}

export interface PanelHistory {
  readonly local: readonly SeriesRow[]
  readonly influx: readonly SeriesRow[]
  /** Local history per vehicle id. */
  readonly vehicles?: Readonly<Record<string, readonly SeriesRow[]>>
}

/** A displayed value retained or aligned by the backend while the live reading is missing. */
export interface RetainedValue {
  readonly value?: number | null
  readonly age_s?: number
  readonly transition_held?: boolean
  readonly aligned?: boolean
}

export interface ModeInterval {
  /** Milliseconds since the epoch. */
  readonly start: number
  readonly end: number
  readonly mode: string | null
  readonly kind: 'history' | 'plan'
}

export interface PvForecastTotal {
  readonly kwh?: number | null
  readonly total_kwh?: number | null
  readonly includes_measured?: boolean
  readonly complete?: boolean
}

export interface DeviceSnapshot extends Omit<CarSnapshot, 'live' | 'display' | 'pv_forecast_totals' | 'forecast'> {
  readonly live: Readonly<Record<string, unknown>> & CarSnapshot['live']
  readonly display?: Readonly<Record<string, RetainedValue | null | undefined>>
  readonly flow_display?: Readonly<Record<string, RetainedValue | null | undefined>>
  readonly forecast?: readonly SeriesRow[]
  readonly history?: readonly SeriesRow[]
  readonly mode_timeline?: Readonly<Partial<Record<'battery' | 'car', readonly ModeInterval[]>>>
  readonly upcoming_plan?: Readonly<Partial<Record<'battery' | 'car', readonly { readonly time: string; readonly mode: string }[]>>>
  readonly pv_forecast_totals?: readonly PvForecastTotal[]
  readonly features?: Readonly<Record<string, boolean>>
  readonly vehicle_forecast_source?: string | null
}
