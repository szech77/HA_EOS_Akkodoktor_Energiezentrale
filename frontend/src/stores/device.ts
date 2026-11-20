import { computed, inject, shallowRef, type ComputedRef, type InjectionKey, type ShallowRef } from 'vue'
import type { Host } from '@/types/host'
import type { DeviceKey, DeviceSnapshot, PanelHistory } from '@/types/device'
import { createDevicePage, vehicleName, type DevicePage, type PageData } from '@/utils/devicePage'
import { createFormat, type Format } from '@/utils/format'
import { createStateLabels, type StateLabels } from '@/utils/modes'

/** A device page: "battery", "energy", "car" (fleet or the only vehicle) or "car/<encoded id>". */
export interface DeviceRoute {
  /** Route as in the address; also the key of the usage report. */
  readonly key: string
  readonly device: DeviceKey
  /** Decoded vehicle id of "car/<id>", otherwise null. */
  readonly vehicleId: string | null
}

const DEVICES: ReadonlySet<string> = new Set<DeviceKey>(['solar', 'grid', 'battery', 'house', 'heat', 'car', 'energy'])

/** Device route of an address; null for other pages or a broken vehicle id encoding. */
export function parseDeviceRoute(key: string): DeviceRoute | null {
  if (DEVICES.has(key)) return { key, device: key as DeviceKey, vehicleId: null }
  if (!key.startsWith('car/')) return null
  try {
    return { key, device: 'car', vehicleId: decodeURIComponent(key.slice(4)) }
  } catch {
    return null
  }
}

/** A vehicle of the list merged over the installation snapshot, with its own history (as app.js did). */
export function vehiclePage(snapshot: DeviceSnapshot, history: PanelHistory, vehicleId: string): PageData | null {
  const vehicle = snapshot.vehicles?.find(item => item.id === vehicleId) as (DeviceSnapshot & { id: string }) | undefined
  if (!vehicle) return null
  return {
    snapshot: { ...snapshot, ...vehicle, vehicles: [], vehicle_name: vehicle.name ?? '', display: vehicle.display ?? {}, flow_display: vehicle.flow_display ?? {} },
    history: { local: history.vehicles?.[vehicleId] ?? vehicle.history ?? [], influx: [] },
  }
}

export interface DeviceStore {
  readonly host: Host
  readonly snapshot: ShallowRef<DeviceSnapshot>
  readonly history: ShallowRef<PanelHistory>
  readonly route: ShallowRef<DeviceRoute>
  /** Time of the shown snapshot: "now" of charts and plans. */
  readonly now: ShallowRef<number>
  /** Snapshot and history of the shown page; null for an unknown vehicle. */
  readonly data: ComputedRef<PageData | null>
  /** "All vehicles": the car page of an installation with a vehicle list. */
  readonly fleet: ComputedRef<boolean>
  readonly title: ComputedRef<string>
  readonly format: Format
  readonly states: StateLabels
  readonly page: DevicePage
}

export const DEVICE_STORE: InjectionKey<DeviceStore> = Symbol('eos-device')

export function createDeviceStore(host: Host, snapshot: DeviceSnapshot, history: PanelHistory): DeviceStore {
  const state = {
    snapshot: shallowRef(snapshot),
    history: shallowRef(history),
    route: shallowRef<DeviceRoute>({ key: 'energy', device: 'energy', vehicleId: null }),
    now: shallowRef(host.now()),
  }
  const format = createFormat(host, () => state.snapshot.value.zone)
  const states = createStateLabels(host)
  const data = computed<PageData | null>(() => {
    const { vehicleId } = state.route.value
    return vehicleId === null ? { snapshot: state.snapshot.value, history: state.history.value } : vehiclePage(state.snapshot.value, state.history.value, vehicleId)
  })
  const fleet = computed(() => state.route.value.key === 'car' && Boolean(state.snapshot.value.vehicles?.length))
  return {
    host,
    ...state,
    data,
    fleet,
    title: computed(() => {
      const { device, vehicleId } = state.route.value
      if (fleet.value) return host.t('fleet.title')
      if (vehicleId !== null) return data.value?.snapshot.vehicle_name ?? ''
      return host.t(`device.${device}`, { vehicle: vehicleName(state.snapshot.value) })
    }),
    format,
    states,
    page: createDevicePage(host, format, states),
  }
}

export function useDeviceStore(): DeviceStore {
  const store = inject(DEVICE_STORE)
  if (!store) throw new Error('Device store is not provided')
  return store
}
