import { computed, inject, ref, shallowRef, type ComputedRef, type InjectionKey, type Ref, type ShallowRef } from 'vue'
import type { Host } from '@/types/host'
import type { Notice, StatusSnapshot } from '@/types/status'
import { createFormat } from '@/utils/format'
import { createStateLabels } from '@/utils/modes'
import { createStatusTexts, sortNotices, type ControlAction, type StatusTexts } from '@/utils/status'

/** Status band, notice cards and the notices page; shared by every page of the panel. */
export interface StatusStore {
  readonly host: Host
  readonly snapshot: ShallowRef<StatusSnapshot>
  /** Current panel route; the notices page hides the compact cards. */
  readonly route: ShallowRef<string>
  /** Browser-side problems (connection, view loading) from app.js. */
  readonly browserNotices: ShallowRef<readonly Notice[]>
  /** Backend and browser notices, most severe first. */
  readonly notices: ComputedRef<Notice[]>
  /** The band is shown once the backend reported a control status. */
  readonly ready: ComputedRef<boolean>
  /** Take-over and release need settings from the backend first. */
  readonly controllable: ComputedRef<boolean>
  readonly car: ComputedRef<boolean>
  readonly confirming: Ref<ControlAction | null>
  readonly busy: Ref<boolean>
  readonly result: Ref<string>
  readonly texts: StatusTexts
  ask(action: ControlAction): void
  cancel(): void
  /** Send the confirmed take-over or release; the backend confirms the device release. */
  confirm(): Promise<void>
}

export const STATUS_STORE: InjectionKey<StatusStore> = Symbol('eos-status')

export function createStatusStore(host: Host, initial: StatusSnapshot): StatusStore {
  const snapshot = shallowRef(initial)
  const browserNotices = shallowRef<readonly Notice[]>([])
  const confirming = ref<ControlAction | null>(null)
  const busy = ref(false)
  const result = ref('')
  const format = createFormat(host, () => snapshot.value.zone)
  return {
    host,
    snapshot,
    route: shallowRef('overview'),
    browserNotices,
    notices: computed(() => sortNotices([...(snapshot.value.notices ?? []), ...browserNotices.value])),
    ready: computed(() => 'control_status' in snapshot.value),
    controllable: computed(() => 'schedule' in (snapshot.value.settings ?? {})),
    car: computed(() => snapshot.value.features?.car !== false),
    confirming,
    busy,
    result,
    texts: createStatusTexts(host, format, createStateLabels(host)),
    ask(action) {
      confirming.value = action
      result.value = ''
    },
    cancel() {
      confirming.value = null
    },
    async confirm() {
      const action = confirming.value
      if (!action || busy.value) return
      // The confirmation sends an explicit boolean.
      const enabled = action === 'take'
      busy.value = true
      try {
        await host.request('control', { enabled })
        result.value = host.t(enabled ? 'control.taken' : 'control.released')
      } catch (error) {
        result.value = error instanceof Error ? error.message : String(error)
      }
      busy.value = false
      confirming.value = null
      await host.refresh()
    },
  }
}

export function useStatusStore(): StatusStore {
  const store = inject(STATUS_STORE)
  if (!store) throw new Error('Status store is not provided')
  return store
}
