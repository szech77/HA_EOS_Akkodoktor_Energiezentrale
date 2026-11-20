<script setup lang="ts">
import { computed } from 'vue'
import { isNumber } from '@/shared/format'
import { useCar } from '../state'
import { useChargingSettings, type LimitName, type SwitchName } from '../useChargingSettings'
import SocField from './SocField.vue'

/** Charging switches and limits; every change is saved at once for the shown vehicle. */
const { host, vehicle } = useCar()
const settings = useChargingSettings(host, vehicle)
const factor = computed(() => {
  const value = vehicle.value?.live.car_range_per_soc
  return isNumber(value) && value > 0 ? value : null
})
const backend = computed(() => vehicle.value?.settings)

const switches = computed<{ name: SwitchName; title: string; hint: string; disabled: boolean }[]>(() => [
  { name: 'pv', title: host.t('settings.pv'), hint: host.t('car.pv_hint', { soc: host.decimal(backend.value?.pv_target_soc ?? 0, 0) }), disabled: false },
  { name: 'fast', title: host.t('settings.fast'), hint: host.t('car.fast_hint', { soc: host.decimal(backend.value?.target_soc ?? 0, 0) }), disabled: false },
  { name: 'phase_auto', title: host.t('settings.phase_auto'), hint: host.t('car.phase_hint'), disabled: !settings.phaseSwitching.value },
])
function toggled(name: SwitchName, event: Event) {
  settings.switches[name] = (event.target as HTMLInputElement).checked
  void settings.toggle(name)
}
const limits: { name: LimitName; label: string }[] = [
  { name: 'pv_target_soc', label: host.t('settings.pv_target_soc') },
  { name: 'fast_target_soc', label: host.t('plans.fast_target') },
]
</script>

<template>
  <form id="vehicle-daily" class="plan-panel" novalidate @submit.prevent>
    <div class="panel-heading">
      <h2>{{ host.t('car.charging') }}</h2>
      <output id="vehicle-switch-saved" class="tag" role="status">{{ settings.status.value }}</output>
    </div>
    <div class="switches">
      <label v-for="item in switches" :key="item.name" class="switch">
        <span><b>{{ item.title }}</b><small>{{ item.hint }}</small></span>
        <input :checked="settings.switches[item.name]" :name="item.name" type="checkbox" class="toggle" :disabled="item.disabled" @change="toggled(item.name, $event)">
      </label>
    </div>
    <details class="acc car-limits">
      <summary><h3>{{ host.t('car.limits') }}</h3></summary>
      <div class="fields">
        <SocField
          v-for="limit in limits"
          :key="limit.name"
          v-model="settings.limits[limit.name]"
          :name="limit.name"
          :label="limit.label"
          :factor="factor"
          @edit="settings.editing[limit.name] = true"
          @commit="settings.commitLimit(limit.name)"
        />
      </div>
    </details>
  </form>
</template>
