/**
 * Backend data of the car pages (charge_view.py and the vehicle/fleet snapshot). The backend
 * computes plan, segments, costs and goal schedules; Vue only presents them.
 */
import type { PanelSnapshot } from '@/host/types'

export type ChargeState = 'disconnected' | 'read_only' | 'suspended' | 'overridden' | 'reached' | 'active' | 'no_plan'
export type SegmentKind = 'pv' | 'grid' | 'pause' | 'ready'

export interface ChargeSegment {
  readonly start: string
  readonly end: string
  readonly kind: SegmentKind
  readonly kwh: number
  readonly power_w: number
  readonly phases?: number | null
  readonly price_ct?: number | null
  /** Feed-in tariff a PV segment is valued with. */
  readonly value_ct?: number | null
  readonly cost_eur?: number | null
  readonly soc_start?: number | null
  readonly soc_end?: number | null
}

export interface ChargeCost {
  readonly eur: number
  readonly price_ct?: number | null
  readonly reached_at?: string | null
}

export interface ChargePlan {
  readonly state: ChargeState
  readonly soc?: number | null
  readonly target_soc?: number | null
  readonly departure?: string | null
  readonly end: string
  readonly generated_at?: string | null
  readonly remaining_kwh?: number | null
  readonly segments?: readonly ChargeSegment[]
  readonly curve?: readonly { readonly time: string; readonly soc: number }[]
  readonly reached_at?: string | null
  readonly buffer_s?: number | null
  readonly pv_kwh: number
  readonly grid_kwh: number
  readonly pv_until?: string | null
  readonly grid_from?: string | null
  readonly grid_price_ct?: number | null
  readonly pv_price_ct?: number | null
  readonly plan_cost?: ChargeCost | null
  readonly immediate_cost?: ChargeCost | null
}

export type GoalSchedule = 'once' | 'weekly'

/** One charging goal as the backend shows it (plan_view). */
export interface ChargeGoal {
  readonly id: string
  readonly active: boolean
  readonly schedule: GoalSchedule
  readonly target_soc: number
  readonly departure_local?: string | null
  readonly departure_time?: string | null
  readonly weekdays?: readonly number[]
  readonly holidays?: boolean
  /** Undefined for a goal the backend has not seen yet. */
  readonly next_departure?: string | null | undefined
  readonly selected?: boolean
}

export interface VehicleLive {
  readonly car?: number | null
  readonly car_soc?: number | null
  readonly car_mode?: string | null
  readonly car_control?: string | null
  readonly car_connected?: boolean | null
  readonly car_available?: boolean | null
  readonly phases?: number | null
  readonly soc_source?: string | null
  readonly car_range?: number | null
  readonly car_range_source?: string | null
  readonly car_range_per_soc?: number | null
  readonly departure?: string | null
}

export interface VehicleSettings {
  readonly pv: boolean
  readonly fast: boolean
  readonly phase_auto: boolean
  readonly pv_target_soc: number
  readonly target_soc: number
}

interface Retained {
  readonly value?: number | null
}

/** One vehicle, or the whole snapshot of an installation without a vehicle list. */
export interface VehicleData {
  readonly id?: string
  readonly name?: string
  readonly live: VehicleLive
  readonly settings: VehicleSettings
  readonly charge_plan?: ChargePlan | null
  readonly charge_plan_view?: readonly ChargeGoal[]
  readonly charge_target_soc?: number | null
  readonly plugins?: { readonly wallbox?: { readonly features?: { readonly phase_switching?: boolean } } }
  readonly display?: { readonly car?: Retained | null; readonly car_soc?: Retained | null }
}

export interface CarSnapshot extends Omit<PanelSnapshot, 'live'>, Partial<Omit<VehicleData, 'live' | 'settings'>> {
  readonly live?: VehicleLive
  readonly settings?: VehicleSettings
  readonly vehicles?: readonly VehicleData[]
}
