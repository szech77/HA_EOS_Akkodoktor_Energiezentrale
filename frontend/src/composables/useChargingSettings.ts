import { computed, reactive, ref, watch, type ComputedRef } from 'vue'
import type { Host } from '@/types/host'
import type { VehicleData } from '@/types/car'

export type SwitchName = 'pv' | 'fast' | 'phase_auto'
export type LimitName = 'pv_target_soc' | 'fast_target_soc'

/** Backend setting behind each limit field. */
const LIMIT_SETTING: Readonly<Record<LimitName, 'pv_target_soc' | 'target_soc'>> = { pv_target_soc: 'pv_target_soc', fast_target_soc: 'target_soc' }

/**
 * Charging switches and limits of one vehicle, saved immediately with only the changed value.
 *
 * Switches follow the backend on every refresh, except while a save runs. A limit field follows
 * the backend only while the user is not editing it, so a refresh never overwrites typing.
 */
export function useChargingSettings(host: Host, vehicle: ComputedRef<VehicleData | null>) {
  const switches = reactive<Record<SwitchName, boolean>>({ pv: false, fast: false, phase_auto: false })
  const limits = reactive<Record<LimitName, number | ''>>({ pv_target_soc: '', fast_target_soc: '' })
  const editing = reactive<Record<LimitName, boolean>>({ pv_target_soc: false, fast_target_soc: false })
  const status = ref('')
  const saving = ref(false)

  const phaseSwitching = computed(() => vehicle.value?.plugins?.wallbox?.features?.phase_switching !== false)
  const identity = computed(() => vehicle.value?.id ?? '')

  function followBackend() {
    const settings = vehicle.value?.settings
    if (!settings) return
    if (!saving.value) {
      switches.pv = settings.pv
      switches.fast = settings.fast
      switches.phase_auto = phaseSwitching.value && settings.phase_auto
    }
    for (const name of Object.keys(LIMIT_SETTING) as LimitName[]) {
      if (!editing[name]) limits[name] = settings[LIMIT_SETTING[name]]
    }
  }
  // The page mounts a new form per vehicle, so this state always belongs to one vehicle.
  watch(() => vehicle.value?.settings, () => followBackend(), { immediate: true })

  async function save(values: Record<string, unknown>, revert?: () => void) {
    if (identity.value) values.vehicle_id = identity.value
    saving.value = true
    status.value = host.t('car.saving')
    try {
      await host.request('settings', values)
      status.value = host.t('settings.saved')
    } catch (error) {
      revert?.()
      status.value = error instanceof Error ? error.message : String(error)
    } finally {
      saving.value = false
    }
    await host.refresh()
  }

  return {
    switches,
    limits,
    editing,
    status,
    phaseSwitching,
    async toggle(name: SwitchName) {
      const value = switches[name]
      await save({ [name]: value }, () => { switches[name] = !value })
    },
    /** Save a limit after the field was changed or its slider released; invalid input is not sent. */
    async commitLimit(name: LimitName) {
      editing[name] = false
      const value = limits[name]
      if (value === '' || !Number.isFinite(value) || value < 1 || value > 100) {
        status.value = host.t('car.invalid')
        return
      }
      await save({ [LIMIT_SETTING[name]]: value })
    },
  }
}
