/** A local commissioning draft. Coordinates stay here until an explicit preview request. */
import { onBeforeUnmount, ref, shallowRef, toRaw, watch } from 'vue'
import type { Host } from '@/types/host'
import { RequestError } from '@/utils/bridge'

export interface SetupDevice {
  kind: 'batteries' | 'electric_vehicles'
  resource: string
  name: string
  capacity_wh: number
  charge_w: number
  discharge_w?: number
  profile: string
  min_soc: number
  max_soc: number
  locked?: string[]
}
export interface Plane {
  source: string
  name: string
  peakpower: number
  surface_tilt: number
  surface_azimuth: number
  inverter_paco: number
  loss: number
}
export interface SetupDraft {
  [key: string]: unknown
  devices: SetupDevice[]
  planes: Plane[]
}
export interface SetupLoad {
  draft: SetupDraft
  providers: Record<string, string[]>
  profiles: { battery: string[]; inverter: string[] }
  current_providers: Record<string, string | null>
  ha_location: { latitude: number; longitude: number; timezone: string }
}
export interface SetupPreview {
  token: string
  changes: { path: string; before: unknown; after: unknown }[]
  expires_seconds: number
}

export function useEOSSetup(host: Host) {
  const loaded = shallowRef<SetupLoad | null>(null)
  const draft = ref<SetupDraft | null>(null)
  const preview = shallowRef<SetupPreview | null>(null)
  const step = ref(0)
  const busy = ref(false)
  const message = ref('')
  const done = ref(false)
  const confirmed = ref(false)
  const locating = ref(false)
  const locationMessage = ref('')
  let mounted = true
  let locationGeneration = 0
  onBeforeUnmount(() => { mounted = false; locationGeneration++ })
  watch(draft, () => { preview.value = null; confirmed.value = false; done.value = false }, { deep: true })

  async function run(action: () => Promise<void>) {
    if (busy.value) return
    busy.value = true
    message.value = ''
    try { await action() } catch (error) {
      if (!mounted) return
      const reason = error instanceof RequestError ? error.reason : null
      const explanation = reason ? host.lookup(`wizard.error_${reason}`) : undefined
      message.value = explanation ?? host.t('wizard.error_request')
      const fields = error instanceof RequestError ? error.fields : []
      if (fields.length) message.value += ` ${fields.map(key => host.lookup(`wizard.field_${key}`) ?? host.t('wizard.check_fields')).join(', ')}`
    } finally { if (mounted) busy.value = false }
  }

  const load = () => run(async () => {
    const response = await host.request<SetupLoad>('eos_setup', { operation: 'load' })
    if (!mounted) return
    loaded.value = response
    draft.value = structuredClone(response.draft)
    step.value = 1
    done.value = false
  })
  const review = () => run(async () => {
    if (!draft.value) return
    const response = await host.request<SetupPreview>('eos_setup', { operation: 'preview', draft: structuredClone(toRaw(draft.value)) })
    if (!mounted) return
    preview.value = response
    confirmed.value = false
    step.value = 6
  })
  const apply = () => run(async () => {
    if (!preview.value || !confirmed.value) return
    const token = preview.value.token
    // A failed/timed-out apply needs a new review, never an automatic retry.
    preview.value = null
    confirmed.value = false
    await host.request('eos_setup', { operation: 'apply', token, confirm: true })
    if (!mounted) return
    done.value = true
    await host.refresh()
  })
  const release = () => run(async () => { await host.request('control', { enabled: false }); await host.refresh() })

  function useHomeLocation() {
    if (!draft.value || !loaded.value) return
    locationGeneration++
    locating.value = false
    Object.assign(draft.value, loaded.value.ha_location)
    locationMessage.value = host.t('wizard.location_home_used')
  }
  function locate() {
    if (locating.value || !draft.value) return
    if (!window.isSecureContext) { locationMessage.value = host.t('wizard.location_secure'); return }
    if (!navigator.geolocation) { locationMessage.value = host.t('wizard.location_unavailable'); return }
    locating.value = true
    locationMessage.value = ''
    const generation = ++locationGeneration
    try { navigator.geolocation.getCurrentPosition(position => {
      if (!mounted || !draft.value || generation !== locationGeneration) return
      draft.value['latitude'] = position.coords.latitude
      draft.value['longitude'] = position.coords.longitude
      locating.value = false
      locationMessage.value = host.t('wizard.location_used', { accuracy: host.decimal(position.coords.accuracy, 0) })
    }, error => {
      if (!mounted || generation !== locationGeneration) return
      locating.value = false
      locationMessage.value = host.t(error.code === 1 ? 'wizard.location_denied' : 'wizard.location_unavailable')
    }, { enableHighAccuracy: true, maximumAge: 0, timeout: 15000 }) } catch {
      locating.value = false
      locationMessage.value = host.t('wizard.location_unavailable')
    }
  }
  return { loaded, draft, preview, step, busy, message, done, confirmed, locating, locationMessage,
    load, review, apply, release, useHomeLocation, locate }
}
