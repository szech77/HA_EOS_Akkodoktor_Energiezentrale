<script setup lang="ts">
import { computed, ref } from 'vue'
import { useSettingsStore } from '@/stores/settings'
import { createDiagnostics, type DiagnosticsView } from '@/utils/sourceDiagnostics'

/** Measurement sources with values, ages and the balance check; copied or saved as plain text. */
const props = defineProps<{ view: DiagnosticsView | null | undefined; zone: string | undefined }>()
const { host } = useSettingsStore()
const { t } = host
const diagnostics = createDiagnostics(host, () => props.zone)
const model = computed(() => diagnostics.model(props.view))
const result = ref('')

async function copy() {
  const text = diagnostics.text(props.view)
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    // Fallback where the async clipboard is unavailable (e.g. plain HTTP).
    const area = document.createElement('textarea')
    area.value = text
    area.setAttribute('readonly', '')
    area.style.cssText = 'position:fixed;left:-9999px;top:0;'
    document.body.append(area)
    area.select()
    const copied = typeof document.execCommand === 'function' && document.execCommand('copy')
    area.remove()
    if (!copied) {
      result.value = t('diagnostics.copy_failed')
      return
    }
  }
  result.value = t('diagnostics.copied')
}

function save() {
  const link = document.createElement('a')
  link.href = URL.createObjectURL(new Blob([diagnostics.text(props.view)], { type: 'text/plain;charset=utf-8' }))
  link.download = diagnostics.fileName(props.view, new Date().toISOString())
  document.body.append(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(link.href), 1000)
  result.value = t('diagnostics.exported', { file: link.download })
}
</script>

<template>
  <details id="source-diagnostics-panel">
    <summary>{{ t('diagnostics.title') }}</summary>
    <p class="footnote">{{ t('diagnostics.info') }}</p>
    <div class="form-footer">
      <button id="diagnostics-copy" type="button" class="diagnostics-action" @click="copy">{{ t('diagnostics.copy') }}</button>
      <button id="diagnostics-export" type="button" class="diagnostics-action" @click="save">{{ t('diagnostics.export') }}</button>
      <output id="diagnostics-result" role="status">{{ result }}</output>
    </div>
    <div id="source-diagnostics">
      <p v-if="!model">{{ t('diagnostics.empty') }}</p>
      <template v-else>
        <p class="footnote">{{ model.time }}</p>
        <div class="diagnostics-scroll">
          <table class="diagnostics">
            <thead>
              <tr>
                <th>{{ t('diagnostics.measurement') }}</th><th>{{ t('diagnostics.source') }}</th><th class="num">{{ t('diagnostics.value') }}</th>
                <th class="num">{{ t('diagnostics.age') }}</th><th>{{ t('diagnostics.status') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, index) in model.sources" :key="index" :class="{ warn: row.warn }">
                <td>{{ row.measurement }}</td>
                <td>{{ row.kind }}<code v-if="row.code">{{ row.source }}</code><template v-else>{{ row.source }}</template></td>
                <td class="num">{{ row.value }}</td><td class="num">{{ row.age }}</td><td>{{ row.status }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <h3>{{ t('diagnostics.derived') }}</h3>
        <div class="diagnostics-scroll">
          <table class="diagnostics">
            <thead><tr><th>{{ t('diagnostics.measurement') }}</th><th class="num">{{ t('diagnostics.value') }}</th></tr></thead>
            <tbody>
              <tr v-for="(row, index) in model.derived" :key="index">
                <td><strong v-if="row.strong">{{ row.label }}</strong><template v-else>{{ row.label }}</template></td><td class="num">{{ row.value }}</td>
              </tr>
              <tr :class="{ warn: model.state.warn }"><td colspan="2"><strong>{{ model.state.text }}</strong></td></tr>
            </tbody>
          </table>
        </div>
        <template v-if="model.estimates.length">
          <h3>{{ t('diagnostics.estimates') }}</h3>
          <div class="diagnostics-scroll">
            <table class="diagnostics">
              <thead><tr><th>{{ t('diagnostics.measurement') }}</th><th>{{ t('diagnostics.reason') }}</th></tr></thead>
              <tbody><tr v-for="(row, index) in model.estimates" :key="index"><td>{{ row.measurement }}</td><td>{{ row.reason }}</td></tr></tbody>
            </table>
          </div>
        </template>
        <template v-if="model.devices.length">
          <h3>{{ t('diagnostics.devices') }}</h3>
          <template v-for="(device, index) in model.devices" :key="index">
            <h3>{{ device.title }}</h3>
            <p class="footnote">{{ device.status }}</p>
            <div class="diagnostics-scroll">
              <table class="diagnostics">
                <thead><tr><th>{{ t('diagnostics.measurement') }}</th><th class="num">{{ t('diagnostics.value') }}</th></tr></thead>
                <tbody><tr v-for="(row, part) in device.values" :key="part"><td>{{ row.measurement }}</td><td class="num">{{ row.value }}</td></tr></tbody>
              </table>
            </div>
          </template>
        </template>
        <template v-if="model.vehicles.length">
          <h3>{{ t('diagnostics.vehicles') }}</h3>
          <div class="diagnostics-scroll">
            <table class="diagnostics">
              <thead><tr><th>{{ t('source.vehicle') }}</th><th class="num">{{ t('measurement.car') }}</th><th class="num">{{ t('measurement.car_soc') }}</th></tr></thead>
              <tbody><tr v-for="(row, index) in model.vehicles" :key="index"><td>{{ row.name }}</td><td class="num">{{ row.power }}</td><td class="num">{{ row.soc }}</td></tr></tbody>
            </table>
          </div>
        </template>
      </template>
    </div>
  </details>
</template>
