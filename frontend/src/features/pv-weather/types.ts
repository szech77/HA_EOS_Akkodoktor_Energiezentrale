/** Backend answer of the `weather_forecast` action (prepared by pv_view.py). */

export const FORECAST_STATUSES = ['available', 'missing_source', 'unsupported', 'unavailable', 'empty'] as const
export type ForecastStatus = (typeof FORECAST_STATUSES)[number]
export type ViewStatus = ForecastStatus | 'loading'

export interface ForecastHour {
  readonly kind: 'hour'
  readonly start: string
  readonly end: string
  readonly now?: boolean
  readonly pv_kwh?: number | null
  readonly condition?: string | null
  readonly temperature?: number | null
  readonly cloud_coverage?: number | null
  readonly precipitation?: number | null
  readonly precipitation_probability?: number | null
}

export interface ForecastNight {
  readonly kind: 'night'
  readonly start: string
  readonly end: string
  readonly condition?: string | null
  readonly low?: number | null
}

export type ForecastEntry = ForecastHour | ForecastNight

export interface ForecastDay {
  readonly date: string
  readonly today?: boolean
  readonly pv_kwh?: number | null
  readonly measured_kwh?: number | null
  readonly complete?: boolean
  readonly condition?: string | null
  readonly high?: number | null
  readonly low?: number | null
  readonly precipitation?: number | null
}

export interface WeatherForecast {
  readonly status: string
  readonly source?: string | null
  readonly fetched_at?: string | null
  readonly hours?: readonly ForecastEntry[]
  readonly days?: readonly ForecastDay[]
}
