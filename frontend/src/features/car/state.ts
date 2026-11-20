import { computed, inject, ref, shallowRef, type ComputedRef, type InjectionKey, type Ref, type ShallowRef } from 'vue'
import type { Host } from '@/host/types'
import { createFormat, type Format } from '@/shared/format'
import { createStateLabels, type StateLabels } from '@/shared/modes'
import { createLabels, type CarLabels } from './labels'
import type { CarSnapshot, VehicleData } from './types'

/** Which car page is shown: the fleet ("All vehicles") or one vehicle. */
export interface CarRoute {
  /** Route as in the address, e.g. "car" or "car/<encoded id>"; also the usage report key. */
  readonly key: string
  /** Decoded vehicle id, or null for "car". */
  readonly vehicleId: string | null
}

/** "car/<encoded id>" → vehicle id; anything else, including a broken encoding, is not a vehicle page. */
export function parseCarRoute(key: string): CarRoute | null {
  if (key === 'car') return { key, vehicleId: null }
  if (!key.startsWith('car/')) return null
  try {
    return { key, vehicleId: decodeURIComponent(key.slice(4)) }
  } catch {
    return null
  }
}

/** The vehicle a page shows: one entry of the vehicle list, merged over the snapshot like app.js. */
export function vehicleOf(snapshot: CarSnapshot, vehicleId: string | null): VehicleData | null {
  const vehicles = snapshot.vehicles ?? []
  if (vehicleId === null) {
    // Without a vehicle list the snapshot itself is the only vehicle.
    return vehicles.length || !snapshot.live || !snapshot.settings ? null : (snapshot as VehicleData)
  }
  const vehicle = vehicles.find(item => item.id === vehicleId)
  return vehicle ? ({ ...snapshot, ...vehicle, vehicles: [] } as VehicleData) : null
}

export interface CarState {
  readonly host: Host
  readonly snapshot: ShallowRef<CarSnapshot>
  /** Time of the shown snapshot; the plan track starts here. */
  readonly now: ShallowRef<number>
  readonly route: ShallowRef<CarRoute>
  readonly vehicles: ComputedRef<readonly VehicleData[]>
  /** Null on the fleet page or while the requested vehicle is not in the snapshot. */
  readonly vehicle: ComputedRef<VehicleData | null>
  readonly fleet: ComputedRef<boolean>
  /** Set by the host when the user asked for the charging plan (e.g. "To the charging plan"). */
  readonly scrollToPlan: Ref<boolean>
  readonly format: Format
  readonly states: StateLabels
  readonly labels: CarLabels
}

export const CAR: InjectionKey<CarState> = Symbol('eos-car')

export function createCarState(host: Host, initial: CarSnapshot): CarState {
  const snapshot = shallowRef(initial)
  const route = shallowRef<CarRoute>({ key: 'car', vehicleId: null })
  const format = createFormat(host, () => snapshot.value.zone)
  const states = createStateLabels(host)
  const vehicles = computed(() => snapshot.value.vehicles ?? [])
  return {
    host,
    snapshot,
    now: shallowRef(host.now()),
    route,
    vehicles,
    vehicle: computed(() => vehicleOf(snapshot.value, route.value.vehicleId)),
    fleet: computed(() => route.value.vehicleId === null && vehicles.value.length > 0),
    scrollToPlan: ref(false),
    format,
    states,
    labels: createLabels(host, format, states),
  }
}

export function useCar(): CarState {
  const state = inject(CAR)
  if (!state) throw new Error('Car state is not provided')
  return state
}
