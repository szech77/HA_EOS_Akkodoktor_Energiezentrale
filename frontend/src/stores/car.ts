import { computed, inject, ref, type ComputedRef, type InjectionKey, type Ref, type ShallowRef } from 'vue'
import type { Host } from '@/types/host'
import type { CarSnapshot, VehicleData } from '@/types/car'
import type { DeviceRoute, DeviceStore } from '@/stores/device'
import { createLabels, type CarLabels } from '@/utils/carLabels'
import type { Format } from '@/utils/format'
import type { StateLabels } from '@/utils/modes'

/** The vehicle a car page shows; null on "All vehicles" and for an unknown vehicle id. */
export function vehicleOf(snapshot: CarSnapshot, vehicleId: string | null): VehicleData | null {
  const vehicles = snapshot.vehicles ?? []
  if (vehicleId === null) {
    // Without a vehicle list the snapshot itself is the only vehicle.
    return vehicles.length || !snapshot.live || !snapshot.settings ? null : (snapshot as VehicleData)
  }
  const vehicle = vehicles.find(item => item.id === vehicleId)
  return vehicle ? ({ ...snapshot, ...vehicle, vehicles: [] } as VehicleData) : null
}

/** Vehicle-specific state of the car pages, on top of the device page store. */
export interface CarStore {
  readonly host: Host
  readonly snapshot: ShallowRef<CarSnapshot>
  /** Time of the shown snapshot; the plan track starts here. */
  readonly now: ShallowRef<number>
  readonly route: ShallowRef<DeviceRoute>
  readonly vehicles: ComputedRef<readonly VehicleData[]>
  readonly vehicle: ComputedRef<VehicleData | null>
  readonly fleet: ComputedRef<boolean>
  /** Set by the host when the user asked for the charging plan (e.g. "To the charging plan"). */
  readonly scrollToPlan: Ref<boolean>
  readonly format: Format
  readonly states: StateLabels
  readonly labels: CarLabels
}

export const CAR_STORE: InjectionKey<CarStore> = Symbol('eos-car')

export function createCarStore(device: DeviceStore): CarStore {
  const snapshot = device.snapshot as ShallowRef<CarSnapshot>
  return {
    host: device.host,
    snapshot,
    now: device.now,
    route: device.route,
    vehicles: computed(() => snapshot.value.vehicles ?? []),
    vehicle: computed(() => (device.route.value.device === 'car' ? vehicleOf(snapshot.value, device.route.value.vehicleId) : null)),
    fleet: device.fleet,
    scrollToPlan: ref(false),
    format: device.format,
    states: device.states,
    labels: createLabels(device.host, device.format, device.states),
  }
}

export function useCarStore(): CarStore {
  const store = inject(CAR_STORE)
  if (!store) throw new Error('Car store is not provided')
  return store
}
