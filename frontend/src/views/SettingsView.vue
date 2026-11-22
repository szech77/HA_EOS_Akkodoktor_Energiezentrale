<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import BasePriceHistory from '@/components/settings/BasePriceHistory.vue'
import Connections from '@/components/settings/Connections.vue'
import ControlAreas from '@/components/settings/ControlAreas.vue'
import SettingField from '@/components/settings/SettingField.vue'
import SourceDiagnostics from '@/components/settings/SourceDiagnostics.vue'
import { catholicAllowed, localityAllowed, useSettingsStore, type Section, type SettingsSnapshot } from '@/stores/settings'
import type { BatteryGroup } from '@/utils/batteryGroup'
import { createFormat, isNumber } from '@/utils/format'
import type { DiagnosticsView } from '@/utils/sourceDiagnostics'

type Snapshot = SettingsSnapshot & {
  readonly eos_status?: string
  readonly plugins?: Readonly<Record<string, { name: string; features: Record<string, boolean>; measurements?: string[] } | null>>
  readonly battery_group?: (BatteryGroup & { readonly capacity_wh?: number | null }) | null
  readonly source_diagnostics?: DiagnosticsView | null
}

/**
 * Settings in five sections: battery, car, holiday calendar, costs and system (control areas,
 * connections and source diagnostics). Daily and cost settings share one save bar.
 */
const props = defineProps<{ snapshot: Snapshot; historyStatus: string | undefined }>()
const store = useSettingsStore()
const { host, section, daily, cost, dirty, saving, focus, costInfo, costMessage, capacityLocked } = store
const { t } = host
const format = createFormat(host, () => props.snapshot.zone)
const root = ref<HTMLElement | null>(null)

const car = computed(() => props.snapshot.features?.car !== false)
const sections = computed(() => [
  { key: 'battery' as const, shown: true },
  { key: 'car' as const, shown: car.value },
  { key: 'calendar' as const, shown: car.value },
  { key: 'costs' as const, shown: true },
  { key: 'system' as const, shown: true },
])
const available = (key: Section) => sections.value.some(item => item.key === key && item.shown)
const show = (key: Section) => store.show(key, available)

// Without local edits the form follows backend changes, e.g. from native HA entities.
watch(() => props.snapshot, () => {
  store.sync()
  if (!available(section.value)) show('battery')
}, { immediate: true })
if (section.value === 'costs') void store.ensureCost()

const limits = computed(() => t(`settings.battery_limits_${props.snapshot.battery_limits_status ?? 'unmanaged'}`, {
  minimum: String(props.snapshot.settings?.['battery_min_soc'] ?? ''),
  maximum: String(props.snapshot.settings?.['battery_max_soc'] ?? ''),
}))
const pvPriceLocked = computed(() => cost['pv_price_source'] === 'eos')
const pvEffective = computed(() => {
  const value = costInfo.value?.pv_price_ct
  return `${t('billing.pv_effective')}: ${isNumber(value) ? format.price(value) : t('billing.pv_missing')}`
})
const costEffective = computed(() => {
  const effective = costInfo.value?.effective
  return effective
    ? `${t('billing.effective')}: ${format.percentText(effective.charge_efficiency * 100)} / ${format.percentText(effective.discharge_efficiency * 100)} · ${host.decimal(effective.capacity_wh / 1000, 2)} kWh`
    : t('billing.efficiency_missing')
})
const changes = computed(() => (dirty.value.length === 1 ? t('settings.one_change') : t('settings.changes', { count: dirty.value.length })))

const field = (name: string) => root.value?.querySelector<HTMLInputElement | HTMLSelectElement>(`[name="${name}"]`) ?? null
const readable = (name: string) => {
  if (name === 'base_price_history') {
    return Array.from(root.value?.querySelectorAll<HTMLInputElement | HTMLSelectElement>('[data-base-prices] input, [data-base-prices] select') ?? []).every(element => element.checkValidity())
  }
  const element = field(name)
  return !element || element.disabled || element.checkValidity()
}

// Show the first rejected field: its section, a collapsed expert block and the input itself.
watch(focus, async target => {
  if (!target) return
  await nextTick()
  const element = field(target.field)
  element?.closest('details')?.setAttribute('open', '')
  element?.focus()
})

const STATES = [['BW', 'Baden-Württemberg'], ['BY', 'Bayern'], ['BE', 'Berlin'], ['BB', 'Brandenburg'], ['HB', 'Bremen'], ['HH', 'Hamburg'], ['HE', 'Hessen'],
  ['MV', 'Mecklenburg-Vorpommern'], ['NI', 'Niedersachsen'], ['NW', 'Nordrhein-Westfalen'], ['RP', 'Rheinland-Pfalz'], ['SL', 'Saarland'], ['SN', 'Sachsen'],
  ['ST', 'Sachsen-Anhalt'], ['SH', 'Schleswig-Holstein'], ['TH', 'Thüringen']] as const
</script>

<template>
  <section id="settings" ref="root">
    <div class="page-top"><div><p class="eyebrow">{{ t('section.daily') }}</p><h1>{{ t('nav.settings') }}</h1></div></div>
    <div class="settings-layout">
      <nav class="settings-side" :aria-label="t('settings.sections')">
        <template v-for="item in sections" :key="item.key">
          <a v-if="item.shown" href="#settings" :data-section="item.key" :aria-current="section === item.key" @click.prevent="show(item.key)">{{ t(`settings.section_${item.key}`) }}</a>
        </template>
      </nav>
      <div class="settings-body plan-panel">
        <form id="daily" novalidate @submit.prevent="store.save(readable)">
          <section v-show="section === 'battery'" data-settings-section="battery">
            <h2>{{ t('device.battery') }}</h2>
            <p class="footnote">{{ t('settings.battery_limits_info') }}</p>
            <div class="fields">
              <SettingField name="battery_min_soc" :label="t('settings.battery_min_soc')"><input v-model="daily.battery_min_soc" name="battery_min_soc" type="number" min="0" max="99" step="1" required></SettingField>
              <SettingField name="battery_max_soc" :label="t('settings.battery_max_soc')"><input v-model="daily.battery_max_soc" name="battery_max_soc" type="number" min="1" max="100" step="1" required></SettingField>
            </div>
            <p id="battery-limits-status" class="tag" role="status">{{ limits }}</p>
            <SettingField v-if="car" name="battery_pv_support" :label="t('settings.pv_support')" toggle><input v-model="daily.battery_pv_support" name="battery_pv_support" type="checkbox" class="toggle"></SettingField>
            <details v-if="car" class="expert">
              <summary>{{ t('settings.expert') }}</summary>
              <div class="fields">
                <SettingField name="reserve_w" :label="t('settings.reserve')"><input v-model="daily.reserve_w" name="reserve_w" type="number" min="0" max="500" step="1" required></SettingField>
                <SettingField name="regulation_interval_s" :label="t('settings.interval')"><input v-model="daily.regulation_interval_s" name="regulation_interval_s" type="number" min="5" max="120" step="1" required></SettingField>
                <SettingField name="battery_pv_min_soc" :label="t('settings.battery_pv_min_soc')"><input v-model="daily.battery_pv_min_soc" name="battery_pv_min_soc" type="number" min="0" max="98" step="1" required></SettingField>
                <SettingField name="battery_pv_wait_s" :label="t('settings.battery_pv_wait_s')"><input v-model="daily.battery_pv_wait_s" name="battery_pv_wait_s" type="number" min="10" max="600" step="1" required></SettingField>
              </div>
            </details>
          </section>
          <section v-show="section === 'car'" data-settings-section="car">
            <h2>{{ t('settings.general_car') }}</h2>
            <p class="footnote">{{ t('settings.car_help') }}</p>
            <SettingField name="battery_pv_start" :label="t('settings.battery_pv_start')" toggle><input v-model="daily.battery_pv_start" name="battery_pv_start" type="checkbox" class="toggle"></SettingField>
            <div class="fields">
              <SettingField name="battery_pv_surplus_w" :label="t('settings.battery_pv_surplus_w')"><input v-model="daily.battery_pv_surplus_w" name="battery_pv_surplus_w" type="number" min="1" max="5000" step="1" required></SettingField>
            </div>
            <p class="footnote">{{ t('settings.battery_pv_info') }}</p>
          </section>
          <section v-show="section === 'calendar'" data-settings-section="calendar">
            <h2>{{ t('plans.holiday_settings') }}</h2>
            <p class="footnote">{{ t('plans.region_note') }}</p>
            <div class="fields">
              <SettingField name="holiday_state" :label="t('plans.state')">
                <select v-model="daily.holiday_state" name="holiday_state" @change="store.holidayChanged()">
                  <option value="">{{ t('plans.national') }}</option>
                  <option v-for="[code, name] in STATES" :key="code" :value="code">{{ name }}</option>
                </select>
              </SettingField>
              <SettingField name="holiday_locality" :label="t('plans.locality')">
                <select v-model="daily.holiday_locality" name="holiday_locality" :disabled="!localityAllowed(daily.holiday_state)">
                  <option value="">{{ t('plans.no_locality') }}</option><option value="augsburg">Augsburg</option>
                </select>
              </SettingField>
            </div>
            <SettingField name="holiday_catholic" :label="t('plans.catholic')" toggle>
              <input v-model="daily.holiday_catholic" name="holiday_catholic" type="checkbox" class="toggle" :disabled="!catholicAllowed(daily.holiday_state)">
            </SettingField>
          </section>
        </form>
        <section v-show="section === 'costs'" data-settings-section="costs">
          <h2>{{ t('billing.settings') }}</h2>
          <p class="footnote">{{ t('billing.settings_note') }}</p>
          <form id="cost-settings" novalidate @submit.prevent="store.save(readable)">
            <div class="fields">
              <SettingField name="pv_price_source" :label="t('billing.pv_price_source')">
                <select v-model="cost.pv_price_source" name="pv_price_source"><option value="eos">{{ t('billing.from_eos') }}</option><option value="manual">{{ t('billing.manual') }}</option></select>
              </SettingField>
              <SettingField name="pv_price_ct" :label="t('billing.pv_price')"><input v-model="cost.pv_price_ct" name="pv_price_ct" type="number" min="-1000" max="1000" step="0.01" required :disabled="pvPriceLocked"></SettingField>
              <SettingField name="capacity_wh" :label="t('billing.capacity')"><input v-model="cost.capacity_wh" name="capacity_wh" type="number" min="100" max="1000000" step="1" required :disabled="capacityLocked"></SettingField>
            </div>
            <BasePriceHistory v-model="cost.base_price_history" :zone="snapshot.zone" />
            <p class="footnote">{{ costInfo ? pvEffective : '' }}</p>
            <details class="expert">
              <summary>{{ t('settings.cost_expert') }}</summary>
              <div class="fields">
                <SettingField name="efficiency_source" :label="t('billing.efficiency_source')">
                  <select v-model="cost.efficiency_source" name="efficiency_source"><option value="eos">{{ t('billing.from_eos') }}</option><option value="manual">{{ t('billing.manual') }}</option></select>
                </SettingField>
                <SettingField name="charge_efficiency" :label="t('billing.charge_efficiency')"><input v-model="cost.charge_efficiency" name="charge_efficiency" type="number" min="0.1" max="1" step="0.001" required></SettingField>
                <SettingField name="discharge_efficiency" :label="t('billing.discharge_efficiency')"><input v-model="cost.discharge_efficiency" name="discharge_efficiency" type="number" min="0.1" max="1" step="0.001" required></SettingField>
                <SettingField name="initial_price_ct" :label="t('billing.initial_price')"><input v-model="cost.initial_price_ct" name="initial_price_ct" type="number" min="-1000" max="1000" step="0.01"></SettingField>
              </div>
              <p class="footnote">{{ costInfo ? costEffective : '' }}</p>
            </details>
            <p class="footnote" role="status">{{ costMessage }}</p>
          </form>
        </section>
        <section v-show="section === 'system'" data-settings-section="system">
          <h2>{{ t('control.title') }}</h2>
          <p class="footnote">{{ t('control.restart_info') }}</p>
          <ControlAreas :control="snapshot.control" />
          <h2>{{ t('settings.setup') }}</h2>
          <p class="footnote">{{ t('settings.setup_info') }}</p>
          <Connections :eos-status="snapshot.eos_status" :history-status="historyStatus" :plugins="snapshot.plugins" :group="snapshot.battery_group" :zone="snapshot.zone" />
          <SourceDiagnostics :view="snapshot.source_diagnostics" :zone="snapshot.zone" />
        </section>
      </div>
    </div>
    <div v-if="dirty.length" id="savebar" class="savebar">
      <div>
        <span><b>{{ changes }}</b> <span class="footnote">{{ t('settings.unsaved') }}</span></span>
        <span class="savebar-actions">
          <button type="button" class="btn ghost" :disabled="saving" @click="store.discard()">{{ t('settings.discard') }}</button>
          <button type="button" class="btn primary" :disabled="saving" @click="store.save(readable)">{{ t('settings.save') }}</button>
        </span>
      </div>
    </div>
  </section>
</template>
