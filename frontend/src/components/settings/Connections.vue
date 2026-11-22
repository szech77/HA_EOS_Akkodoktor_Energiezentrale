<script setup lang="ts">
import { computed } from 'vue'
import { useSettingsStore } from '@/stores/settings'
import { groupEntries, type BatteryGroup } from '@/utils/batteryGroup'
import { createFormat } from '@/utils/format'

interface Plugin {
  readonly name: string
  readonly features: Readonly<Record<string, boolean>>
  readonly measurements?: readonly string[]
}

/** Connections to EOS and InfluxDB, the configured plugins with their features and the battery group. */
const props = defineProps<{
  eosStatus: string | undefined
  historyStatus: string | undefined
  plugins: Readonly<Record<string, Plugin | null | undefined>> | undefined
  group: BatteryGroup | null | undefined
  zone: string | undefined
}>()
const { host } = useSettingsStore()
const { t } = host
const format = createFormat(host, () => props.zone)

const plugins = computed(() => Object.entries(props.plugins ?? {}).flatMap(([kind, plugin]) => {
  if (!plugin) return []
  const features = Object.entries(plugin.features).map(([feature, enabled]) => `${t(`plugin.feature.${feature}`)}: ${t(enabled ? 'plugin.yes' : 'plugin.no')}`).join(' · ')
  const measurements = (plugin.measurements ?? []).length ? ` · ${(plugin.measurements ?? []).map(key => t(`measurement.${key}`)).join(', ')}` : ''
  return [{ key: kind, name: plugin.name, text: features + measurements }]
}))
const group = computed(() => groupEntries(host, format, props.group))
</script>

<template>
  <dl id="connections">
    <dt>Akkudoktor EOS</dt><dd>{{ t(`status.${eosStatus ?? 'connecting'}`) }}</dd>
    <dt>InfluxDB</dt><dd>{{ t(`status.${historyStatus ?? 'connecting'}`) }}</dd>
    <template v-for="plugin in plugins" :key="plugin.key"><dt>{{ plugin.name }}</dt><dd>{{ plugin.text }}</dd></template>
    <template v-for="(entry, index) in group" :key="`g${index}`">
      <dt v-if="entry.term !== undefined">{{ entry.term }}</dt>
      <dd v-if="entry.device">
        <div>{{ entry.text }}</div>
        <div class="device-measurements"><span v-for="(item, part) in entry.device.values" :key="part">{{ item.label }}: <strong>{{ item.value }}</strong></span></div>
        <div v-if="entry.device.firmware">{{ entry.device.firmware.label }}: <strong>{{ entry.device.firmware.version }}</strong> {{ entry.device.firmware.detail }}</div>
      </dd>
      <dd v-else>{{ entry.text }}</dd>
    </template>
  </dl>
</template>
