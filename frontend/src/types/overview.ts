/** Backend data of the overview: live flow, references for the power rings and EOS plan events. */
import type { DeviceSnapshot } from '@/types/device'
import type { WeatherNow } from '@/types/host'

export interface PlanEvent {
  readonly time: string
  readonly device?: 'battery' | 'car'
  /** battery_full / car_target, otherwise a mode change. */
  readonly kind?: string
  readonly mode?: string
  /** What the battery does according to the forecast (hold, charge_pv, …); the EOS mode alone can mislead. */
  readonly effect?: string
  readonly soc?: number
  readonly price_ct?: number | null
  readonly vehicle_name?: string
}

export interface OverviewSnapshot extends DeviceSnapshot {
  readonly power_reference?: Readonly<Record<string, number>>
  readonly power_supply?: { readonly state?: string; readonly grid_active?: boolean | null } | null
  /** Open notices per flow node ("grid", "car/<id>" …), decided by the backend. */
  readonly node_problems?: Readonly<Record<string, 'error' | 'warning'>>
  readonly heat_load_configured?: boolean
  readonly battery_low?: boolean
  readonly plan_events?: readonly PlanEvent[]
  readonly pv_daily_forecast?: readonly { readonly kwh?: number | null }[]
  readonly weather?: WeatherNow
}
