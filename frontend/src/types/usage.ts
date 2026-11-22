/**
 * Consumption and cost report as the backend sends it (accounting.py, action "accounting").
 * The browser only words and draws these values; it never derives prices or shares itself.
 */
type Num = number | null | undefined

export type Source = 'pv' | 'battery' | 'grid' | 'unknown'
export type Period = 'day' | 'month' | 'year'
export type ChartUnit = 'kw' | 'kwh' | 'eur'

export interface Amount {
  readonly kwh: number
  readonly cost_eur?: Num
  readonly cost_available?: boolean
  readonly cost_partial?: boolean
  readonly estimated?: boolean
  readonly energy_estimated?: boolean
  readonly average_price_ct?: Num
  readonly share_percent?: Num
  readonly sources: Readonly<Partial<Record<Source, SourceAmount>>>
}

export type SourceAmount = Omit<Amount, 'sources'>

export interface Bin extends Amount {
  readonly time: string
}

export interface ConsumerEntry {
  readonly total: Amount
  readonly bins: readonly Bin[]
}

export interface OriginPart {
  readonly kwh: number
  readonly price_ct?: Num
  readonly cost_eur?: Num
}

export interface Fact {
  readonly id: string
  readonly unit?: 'hour' | 'day' | 'month'
  readonly time?: string
  readonly key?: string
  readonly kwh?: number
  readonly eur?: number
  readonly percent?: Num
  readonly count?: number
  readonly days?: number
  readonly cost_available?: boolean
  readonly cost_eur?: Num
  readonly self_percent?: Num
  readonly self_price_ct?: Num
  readonly grid_price_ct?: Num
  readonly export_kwh?: number
  readonly import_kwh?: number
}

export interface ReportView {
  readonly self_percent?: Num
  readonly per_day_kwh?: Num
  readonly pv_kwh?: Num
  readonly battery_own_kwh?: Num
  readonly savings_eur?: Num
  readonly grid_price_ct?: Num
  readonly grid_kwh?: number
  readonly grid_cost_eur?: Num
  readonly self_kwh?: number
  readonly self_price_ct?: Num
  readonly self_cost_eur?: Num
  readonly self_origin?: Readonly<Partial<Record<'pv_direct' | 'battery_pv' | 'battery_grid' | 'battery_unknown', OriginPart>>>
  readonly unknown_kwh?: number
  readonly cost_available?: boolean
  readonly cost_partial?: boolean
  readonly cost_eur?: Num
  readonly facts?: readonly Fact[]
}

export type PvFlowKey = 'house' | 'car' | 'heat' | 'storage' | 'export'
export type PvGapKey = 'battery_pv' | 'battery_grid' | 'battery_unknown' | 'grid' | 'unknown'

export interface BalanceBin {
  readonly time: string
  readonly pv_kwh?: number
  readonly grid_import_kwh?: number
  readonly grid_import_eur?: Num
  readonly export_kwh?: number
  readonly export_eur?: Num
  readonly cost_partial?: boolean
  readonly pv_flow?: Readonly<Partial<Record<PvFlowKey, number>>>
  readonly pv_gap?: Readonly<Partial<Record<PvGapKey, number>>>
}

export interface Balance {
  readonly pv_kwh: number
  readonly export_kwh: number
  readonly export_eur?: Num
  readonly feed_in_price_ct?: Num
  readonly grid_import_kwh: number
  readonly grid_import_cost_eur?: Num
  readonly grid_import_price_ct?: Num
  readonly grid_balance_eur?: Num
  readonly storage_grid_kwh?: number
  readonly self_consumption_percent?: Num
  readonly autarky_percent?: Num
  readonly own_kwh?: Num
  readonly total_cost_eur?: Num
  readonly net_eur?: Num
  readonly base_days: number
  readonly base_price_eur_month?: number
  readonly base_eur?: number
  readonly cost_partial?: boolean
  readonly bins?: readonly BalanceBin[]
  readonly pv_flow?: Readonly<Record<PvFlowKey, number>>
  readonly pv_use?: Readonly<Record<'direct' | 'storage' | 'export', { readonly kwh: number; readonly share_percent?: Num }>>
  readonly pv_gap?: Readonly<Partial<Record<PvGapKey, number>>>
}

export interface ProfilePoint {
  readonly time: string
  readonly source_estimated?: boolean
  readonly solar?: Num
  readonly grid?: { readonly import?: Num; readonly export?: Num }
  readonly pv_flow?: Readonly<Partial<Record<PvFlowKey, number>>>
  readonly pv_gap?: Readonly<Partial<Record<PvGapKey, number>>>
  readonly [consumer: string]: unknown
}

export interface PowerProfile {
  readonly step_s?: number
  readonly gap_s?: number
  readonly points: readonly ProfilePoint[]
}

export interface PvForecast {
  readonly kwh: number
  readonly complete?: boolean
  readonly bins?: readonly { readonly time: string; readonly kwh?: number }[]
  readonly points?: readonly { readonly time: string; readonly end: string; readonly w?: number }[]
}

export interface Report {
  readonly date: string
  readonly end: string
  readonly hours?: readonly string[]
  readonly consumers: Readonly<Record<string, ConsumerEntry>>
  readonly total?: ConsumerEntry
  readonly views?: Readonly<Record<string, ReportView>>
  readonly balance?: Balance | null
  readonly overview?: { readonly consumers?: Readonly<Record<string, Amount | null>>; readonly total?: Amount | null }
  readonly power_profile?: PowerProfile | null
  readonly pv_forecast?: PvForecast | null
  readonly historical_error?: boolean
  readonly reconstructed?: boolean
  readonly started?: string | null
}

/** Cost settings and their effective values (action "accounting" with period "day"). */
export interface CostSettings {
  readonly settings: Readonly<Record<string, string | number | null | undefined>>
  readonly pv_price_ct?: Num
  readonly effective?: { readonly charge_efficiency: number; readonly discharge_efficiency: number; readonly capacity_wh: number } | null
}
