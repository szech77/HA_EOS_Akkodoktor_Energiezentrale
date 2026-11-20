/**
 * Hash routes of the panel (#overview, #battery, #car/<id>, #usage/<key>, …). The panel lives in an
 * iframe of Home Assistant, so the address hash is its whole navigation state.
 */
import { onBeforeUnmount, shallowRef, type ShallowRef } from 'vue'

export type DeviceKey = 'solar' | 'grid' | 'battery' | 'house' | 'heat' | 'car' | 'energy'

export type Page =
  | { readonly name: 'overview' }
  | { readonly name: 'device'; readonly device: DeviceKey }
  | { readonly name: 'pv' }
  | { readonly name: 'notices' }
  | { readonly name: 'settings' }
  | { readonly name: 'usage'; readonly report: string }

export interface ResolvedRoute {
  /** The shown route as in the address (without "#"). */
  readonly key: string
  readonly page: Page
  /** Navigation entry to highlight. */
  readonly section: 'overview' | 'car' | 'notices' | 'settings'
}

/** What the routes depend on: which consumers exist and which vehicles are configured. */
export interface RouteContext {
  readonly features?: Readonly<Record<string, boolean>> | undefined
  readonly vehicles?: readonly { readonly id?: string | undefined }[] | undefined
}

const DEVICES: ReadonlySet<string> = new Set<DeviceKey>(['solar', 'grid', 'battery', 'house', 'heat', 'car', 'energy'])

/** Car and heat pump can be switched off; their pages are then unavailable. */
export const consumerEnabled = (context: RouteContext, key: string) => !['car', 'heat'].includes(key) || context.features?.[key] !== false

const vehicles = (context: RouteContext) => (consumerEnabled(context, 'car') ? context.vehicles ?? [] : [])

/** Decoded vehicle id of a "car/<encoded id>" segment; null for anything else or a broken encoding. */
export function vehicleIdOf(key: string): string | null {
  if (!key.startsWith('car/')) return null
  try {
    return decodeURIComponent(key.slice(4))
  } catch {
    return null
  }
}

const knownVehicle = (context: RouteContext, key: string) => {
  const id = vehicleIdOf(key)
  return id !== null && vehicles(context).some(vehicle => vehicle.id === id)
}

/** Report pages: PV, house, car(s), heat pump, grid and the total balance. */
function reportAvailable(context: RouteContext, report: string): boolean {
  if (['total', 'grid', 'pv', 'house'].includes(report)) return true
  if (report === 'heat' || report === 'car') return consumerEnabled(context, report)
  return knownVehicle(context, report)
}

/**
 * The page of an address. With exactly one vehicle "#car" is that vehicle's page; the caller
 * replaces the address so the back button keeps the previous page.
 */
export function resolveRoute(hash: string, context: RouteContext): ResolvedRoute & { readonly redirect?: string } {
  const requested = hash.replace(/^#/, '')
  const list = vehicles(context)
  if (requested === 'car' && list.length === 1) {
    const key = `car/${encodeURIComponent(list[0]?.id ?? '')}`
    return { ...resolveRoute(key, context), redirect: key }
  }
  const route = (key: string, page: Page): ResolvedRoute => ({
    key,
    page,
    section: page.name === 'settings' || page.name === 'notices' ? page.name : key === 'car' || key.startsWith('car/') ? 'car' : 'overview',
  })
  if (requested.startsWith('usage/') && reportAvailable(context, requested.slice(6))) return route(requested, { name: 'usage', report: requested.slice(6) })
  if (DEVICES.has(requested) && consumerEnabled(context, requested)) return route(requested, { name: 'device', device: requested as DeviceKey })
  if (knownVehicle(context, requested)) return route(requested, { name: 'device', device: 'car' })
  if (requested === 'pv' || requested === 'notices' || requested === 'settings') return route(requested, { name: requested })
  return route('overview', { name: 'overview' })
}

/** The current address hash, following the browser's hash changes. */
export function useHash(target: Pick<Window, 'addEventListener' | 'removeEventListener' | 'location'> = window): ShallowRef<string> {
  const hash = shallowRef(target.location.hash)
  const follow = () => { hash.value = target.location.hash }
  target.addEventListener('hashchange', follow)
  onBeforeUnmount(() => target.removeEventListener('hashchange', follow))
  return hash
}
