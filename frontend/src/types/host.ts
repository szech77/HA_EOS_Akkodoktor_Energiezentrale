/**
 * Services of the panel application (stores/app.ts) for the pages.
 *
 * The app owns the backend connection and the language pack; pages only present backend data.
 * All backend calculations stay in the integration; Home Assistant authenticates every request.
 */

export type Translate = (key: string, values?: Readonly<Record<string, string | number>>) => string

/** Locale-aware number formatting of the host (same rounding everywhere in the panel). */
export type FormatDecimal = (value: number, digits?: number) => string

/** Authenticated request to the integration backend through the panel bridge. */
export type BackendRequest = <T>(action: string, values?: Readonly<Record<string, unknown>>) => Promise<T>

export interface WeatherNow {
  readonly condition?: string | null
  readonly temperature?: number | null
  readonly unit?: string
}

export interface ForecastRow {
  readonly time: string
  readonly end: string
  readonly solar?: number | null
}

export interface PvTotal {
  readonly kwh?: number | null
}

export interface PvEffect {
  readonly id: string
  readonly kwh?: number
  readonly today_kwh?: number
  readonly soc?: number | null
  readonly start?: string
  readonly end?: string
  readonly price_ct?: number | null
  readonly vehicle_id?: string
  readonly vehicle_name?: string
}

/** The part of the panel snapshot the Vue pages read. */
export interface PanelSnapshot {
  readonly zone?: string
  readonly vehicle_name?: string
  readonly live?: { readonly solar?: number | null; readonly weather?: WeatherNow | null }
  readonly pv_today_kwh?: number | null
  readonly pv_forecast_totals?: readonly PvTotal[]
  readonly pv_now?: { readonly power_w?: number | null; readonly ratio?: number | null }
  readonly pv_effects?: readonly PvEffect[]
  readonly forecast?: readonly ForecastRow[]
}

/** What the app hands to a page. */
export interface Host {
  readonly request: BackendRequest
  readonly t: Translate
  readonly decimal: FormatDecimal
  readonly locale: () => string
  readonly now: () => number
  /** Text of a key, or undefined when the language pack has none (labels for backend states). */
  readonly lookup: (key: string) => string | undefined
  /** Reload the panel snapshot after a change, e.g. a saved setting. */
  readonly refresh: () => Promise<void>
}
