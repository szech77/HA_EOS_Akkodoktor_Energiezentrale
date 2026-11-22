/**
 * Settings: one save bar for the daily settings and the cost settings. The backend validates
 * every value; its allow-listed field names and reasons mark the affected fields.
 */
import { computed, inject, reactive, ref, shallowRef, type ComputedRef, type InjectionKey, type Ref, type ShallowRef } from 'vue'
import type { Host } from '@/types/host'
import type { ControlKey, StatusSnapshot } from '@/types/status'
import type { BasePrice, CostSettings } from '@/types/usage'
import { RequestError } from '@/utils/bridge'
import { isNumber } from '@/utils/format'

export type Section = 'battery' | 'car' | 'calendar' | 'costs' | 'system' | 'wizard'
export type FieldValue = string | number | boolean
export type Values = Record<string, FieldValue>

export const NUMBER_FIELDS = ['reserve_w', 'regulation_interval_s', 'battery_min_soc', 'battery_max_soc', 'battery_pv_min_soc', 'battery_pv_wait_s', 'battery_pv_surplus_w'] as const
export const SWITCH_FIELDS = ['battery_pv_support', 'battery_pv_start', 'holiday_catholic'] as const
export const TEXT_FIELDS = ['holiday_state', 'holiday_locality'] as const
export const DAILY_FIELDS: readonly string[] = [...NUMBER_FIELDS, ...SWITCH_FIELDS, ...TEXT_FIELDS]
export const COST_FIELDS = ['pv_price_source', 'pv_price_ct', 'capacity_wh', 'base_price_eur_month', 'base_price_history', 'efficiency_source', 'charge_efficiency', 'discharge_efficiency', 'initial_price_ct'] as const

/** Section of each field, to show the first field the backend rejected. */
const SECTION_OF: Readonly<Record<string, Section>> = {
  battery_pv_start: 'car', battery_pv_surplus_w: 'car',
  holiday_state: 'calendar', holiday_locality: 'calendar', holiday_catholic: 'calendar',
  ...Object.fromEntries(COST_FIELDS.map(name => [name, 'costs'])),
}
export const sectionOf = (field: string): Section => SECTION_OF[field] ?? 'battery'

/** Holiday regions: localities exist only in Bavaria, the Catholic option in BY, SN and TH. */
export const localityAllowed = (state: unknown) => state === 'BY'
export const catholicAllowed = (state: unknown) => ['BY', 'SN', 'TH'].includes(String(state))

export interface SettingsSnapshot extends StatusSnapshot {
  readonly battery_limits_status?: string
  readonly battery_group?: { readonly battery_count?: number; readonly capacity_wh?: number | null } | null
}

export interface SettingsStore {
  readonly host: Host
  readonly section: Ref<Section>
  readonly daily: Values
  readonly cost: Values
  /** Field name → message of a rejected or unreadable field. */
  readonly errors: Record<string, string>
  /** The first rejected field; the view shows and focuses it. */
  readonly focus: ShallowRef<{ readonly field: string } | null>
  readonly costInfo: ShallowRef<CostSettings | null>
  readonly costMessage: Ref<string>
  readonly saving: Ref<boolean>
  /** Settings arrived from the backend; control changes wait for them. */
  readonly ready: Ref<boolean>
  readonly dirty: ComputedRef<readonly { readonly group: 'daily' | 'cost'; readonly key: string }[]>
  readonly capacityLocked: ComputedRef<boolean>
  /** Follow backend settings while there are no local edits (e.g. changes from native HA entities). */
  sync(): void
  show(section: Section, available: (section: Section) => boolean): void
  ensureCost(): Promise<void>
  holidayChanged(): void
  clearError(field: string): void
  /** `readable` reports fields the browser cannot parse (empty or out of the input's range). */
  save(readable: (field: string) => boolean): Promise<void>
  discard(): void
  readonly control: {
    readonly confirming: Ref<ControlKey | null>
    readonly busy: Ref<boolean>
    readonly result: Ref<string>
    ask(key: ControlKey): void
    cancel(): void
    confirm(key: ControlKey): Promise<void>
  }
}

export const SETTINGS_STORE: InjectionKey<SettingsStore> = Symbol('eos-settings')

export function createSettingsStore(
  host: Host,
  snapshot: ShallowRef<SettingsSnapshot>,
  services: { readonly toast: (message: string) => void; readonly costsChanged: () => void },
): SettingsStore {
  const { t } = host
  const section = ref<Section>('battery')
  const daily = reactive<Values>({})
  const cost = reactive<Values>({})
  const errors = reactive<Record<string, string>>({})
  const focus = shallowRef<{ field: string } | null>(null)
  const costInfo = shallowRef<CostSettings | null>(null)
  const costMessage = ref('')
  const saving = ref(false)
  const ready = ref(false)
  let baseline: Values | null = null
  let costBaseline: Values | null = null
  let costLoading: Promise<void> | null = null
  // Baselines are plain objects; this counter makes the dirty list follow their replacement.
  const generation = ref(0)

  const differences = (values: Values, base: Values | null, group: 'daily' | 'cost') =>
    base ? Object.keys(values).filter(key => values[key] !== base[key]).map(key => ({ group, key })) : []
  const dirty = computed(() => {
    void generation.value
    return [...differences(daily, baseline, 'daily'), ...differences(cost, costBaseline, 'cost')]
  })
  const capacityLocked = computed(() => (snapshot.value.battery_group?.battery_count ?? 0) > 1)

  function applyHoliday(values: Values) {
    if (!localityAllowed(values['holiday_state'])) values['holiday_locality'] = ''
    if (!catholicAllowed(values['holiday_state'])) values['holiday_catholic'] = false
  }

  function fill() {
    const settings = snapshot.value.settings ?? {}
    for (const name of DAILY_FIELDS) {
      const value = settings[name]
      daily[name] = typeof value === 'boolean' || typeof value === 'number' || typeof value === 'string' ? value : SWITCH_FIELDS.includes(name as never) ? false : ''
    }
    applyHoliday(daily)
    baseline = { ...daily }
    generation.value++
  }

  async function loadCost() {
    const data = await host.request<CostSettings>('accounting', { period: 'day' })
    for (const name of COST_FIELDS) {
      const value = data.settings[name]
      if (name !== 'base_price_history') cost[name] = typeof value === 'number' || typeof value === 'string' ? value : ''
    }
    cost['base_price_history'] = JSON.stringify(data.settings['base_price_history'] ?? [{ valid_from: '', period: 'month', amount_eur: data.settings['base_price_eur_month'] ?? 0 }])
    if (capacityLocked.value && isNumber(snapshot.value.battery_group?.capacity_wh)) cost['capacity_wh'] = snapshot.value.battery_group.capacity_wh
    cost['pv_price_source'] = typeof data.settings['pv_price_source'] === 'string' ? data.settings['pv_price_source'] : 'eos'
    // With the EOS price the field shows the price EOS currently supplies.
    if (cost['pv_price_source'] === 'eos') cost['pv_price_ct'] = isNumber(data.pv_price_ct) ? Number(data.pv_price_ct.toFixed(6)) : ''
    costInfo.value = data
    costMessage.value = ''
  }

  function ensureCost(): Promise<void> {
    if (costBaseline) return Promise.resolve()
    costLoading ??= loadCost()
      .then(() => {
        costBaseline = { ...cost }
        generation.value++
      })
      .catch(error => {
        costMessage.value = error instanceof Error ? error.message : String(error)
      })
      .finally(() => {
        costLoading = null
      })
    return costLoading
  }

  function clearErrors() {
    for (const key of Object.keys(errors)) delete errors[key]
  }

  function showErrors(fields: readonly string[], reason: string | null): boolean {
    const known = fields.filter(field => field in daily || field in cost)
    for (const field of known) errors[field] = host.lookup(`settings.error_${reason}`) ?? t('settings.error_field')
    const first = known[0]
    if (first) {
      section.value = sectionOf(first)
      focus.value = { field: first }
    }
    return first !== undefined
  }

  const number = (value: FieldValue) => Number(value)
  function dailyValues(): Record<string, unknown> {
    const values: Record<string, unknown> = {}
    for (const name of NUMBER_FIELDS) values[name] = number(daily[name] ?? '')
    for (const name of SWITCH_FIELDS) values[name] = daily[name] === true
    for (const name of TEXT_FIELDS) values[name] = String(daily[name] ?? '')
    return values
  }
  function costValues(): Record<string, unknown> {
    const values: Record<string, unknown> = {}
    for (const name of ['pv_price_ct', 'charge_efficiency', 'discharge_efficiency', 'capacity_wh', 'base_price_eur_month']) values[name] = number(cost[name] ?? '')
    values['base_price_history'] = (JSON.parse(String(cost['base_price_history'] ?? '[]')) as BasePrice[]).map(row => ({
      ...row, amount_eur: Number(row.amount_eur),
      ...('grid_price_ct' in row ? { grid_price_ct: row.grid_price_ct == null || String(row.grid_price_ct) === '' ? null : Number(row.grid_price_ct) } : {}),
    }))
    values['pv_price_source'] = String(cost['pv_price_source'] ?? 'eos')
    values['efficiency_source'] = String(cost['efficiency_source'] ?? 'eos')
    values['initial_price_ct'] = cost['initial_price_ct'] === '' || cost['initial_price_ct'] === undefined ? null : number(cost['initial_price_ct'])
    return values
  }

  const confirming = ref<ControlKey | null>(null)
  const busy = ref(false)
  const result = ref('')

  return {
    host,
    section,
    daily,
    cost,
    errors,
    focus,
    costInfo,
    costMessage,
    saving,
    ready,
    dirty,
    capacityLocked,
    sync() {
      const settings = snapshot.value.settings ?? {}
      if (!('schedule' in settings)) return
      if (!ready.value || !dirty.value.some(item => item.group === 'daily')) {
        fill()
        ready.value = true
      }
    },
    show(target, available) {
      section.value = available(target) ? target : 'battery'
      if (section.value === 'costs') void ensureCost()
    },
    ensureCost,
    holidayChanged() {
      applyHoliday(daily)
    },
    clearError(field) {
      delete errors[field]
    },
    async save(readable) {
      if (saving.value) return
      clearErrors()
      const changes = dirty.value
      if (!changes.length) return
      // Browser input constraints only catch unparsable or empty numbers; the backend validates the values.
      const unreadable = changes.map(item => item.key).filter(field => !readable(field))
      if (unreadable.length) {
        showErrors(unreadable, 'input')
        services.toast(t('settings.fix_fields'))
        return
      }
      saving.value = true
      try {
        if (changes.some(item => item.group === 'daily')) {
          await host.request('settings', dailyValues())
          baseline = { ...daily }
          generation.value++
        }
        if (changes.some(item => item.group === 'cost')) {
          await host.request('accounting', { settings: costValues() })
          services.costsChanged()
          costBaseline = null
          await ensureCost()
        }
        services.toast(t('settings.saved'))
      } catch (error) {
        const failure = error instanceof RequestError ? error : null
        services.toast(showErrors(failure?.fields ?? [], failure?.reason ?? null) ? t('settings.fix_fields') : error instanceof Error ? error.message : String(error))
      } finally {
        saving.value = false
      }
      await host.refresh()
    },
    discard() {
      if (baseline) Object.assign(daily, baseline)
      if (costBaseline) Object.assign(cost, costBaseline)
      applyHoliday(daily)
      clearErrors()
      services.toast(t('settings.discarded'))
    },
    control: {
      confirming,
      busy,
      result,
      ask(key) {
        confirming.value = key
        result.value = ''
      },
      cancel() {
        confirming.value = null
      },
      async confirm(key) {
        if (confirming.value !== key || busy.value) return
        // Only this area changes; the backend rejects an area without a matching device.
        const view = snapshot.value.control?.[key]
        const enabled = !view?.enabled && !view?.release_pending
        busy.value = true
        try {
          await host.request('control', { [key]: enabled })
          result.value = t(enabled ? `control.area_taken.${key}` : `control.area_released.${key}`)
        } catch (error) {
          result.value = error instanceof Error ? error.message : String(error)
        }
        busy.value = false
        confirming.value = null
        await host.refresh()
      },
    },
  }
}

export function useSettingsStore(): SettingsStore {
  const store = inject(SETTINGS_STORE)
  if (!store) throw new Error('Settings store is not provided')
  return store
}
