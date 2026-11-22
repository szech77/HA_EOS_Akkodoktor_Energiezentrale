<script setup lang="ts">
import { computed } from 'vue'
import { useSettingsStore, type FieldValue } from '@/stores/settings'
import type { BasePrice } from '@/types/usage'
import { createFormat } from '@/utils/format'

const props = defineProps<{ zone?: string | undefined }>()
const model = defineModel<FieldValue | undefined>()
const { host, errors, clearError } = useSettingsStore()
const { t } = host
const rows = computed(() => JSON.parse(String(model.value || '[]')) as BasePrice[])
function update(index: number, key: keyof BasePrice, value: string) {
  model.value = JSON.stringify(rows.value.map((row, i) => i === index ? { ...row, [key]: value } : row))
  clearError('base_price_history')
}
function add() {
  model.value = JSON.stringify([...rows.value, { valid_from: createFormat(host, () => props.zone).dayKey(host.now()), period: 'month', amount_eur: 0 }])
  clearError('base_price_history')
}
function remove(index: number) {
  model.value = JSON.stringify(rows.value.filter((_, i) => i !== index))
  clearError('base_price_history')
}
</script>

<template>
  <fieldset data-base-prices name="base_price_history" tabindex="-1" :class="{ invalid: errors.base_price_history }">
    <legend>{{ t('billing.base_price_history') }}</legend>
    <p class="footnote">{{ t('billing.base_price_note') }}</p>
    <p class="footnote">{{ t('billing.grid_price_note') }}</p>
    <div v-for="(row, index) in rows" :key="index" class="base-price-row">
      <label>{{ t('billing.base_price_from') }}<input :name="`base_price_from_${index}`" type="date" min="2000-01-01" max="2100-12-31" :value="row.valid_from" @input="update(index, 'valid_from', ($event.target as HTMLInputElement).value)"><span v-if="!row.valid_from" class="footnote">{{ t('billing.base_price_start') }}</span></label>
      <label>{{ t('billing.base_price_period') }}<select :name="`base_price_period_${index}`" :value="row.period" @change="update(index, 'period', ($event.target as HTMLSelectElement).value)"><option value="month">{{ t('billing.base_price_monthly') }}</option><option value="day">{{ t('billing.base_price_daily') }}</option></select></label>
      <label>{{ t('billing.base_price_amount') }}<input :name="`base_price_amount_${index}`" type="number" min="0" max="1000" step="any" required :value="row.amount_eur" @input="update(index, 'amount_eur', ($event.target as HTMLInputElement).value)"></label>
      <label>{{ t('billing.grid_price_source') }}<select :name="`grid_price_source_${index}`" :value="row.grid_price_source ?? 'dynamic'" @change="update(index, 'grid_price_source', ($event.target as HTMLSelectElement).value)"><option value="dynamic">{{ t('billing.grid_price_dynamic') }}</option><option value="fixed">{{ t('billing.grid_price_fixed') }}</option></select></label>
      <label v-if="row.grid_price_source === 'fixed'">{{ t('billing.grid_price_ct') }}<input :name="`grid_price_ct_${index}`" type="number" min="-1000" max="1000" step="0.0001" required :value="row.grid_price_ct ?? ''" @input="update(index, 'grid_price_ct', ($event.target as HTMLInputElement).value)"></label>
      <button type="button" class="btn ghost" data-base-remove :aria-label="t('billing.base_price_remove')" @click="remove(index)">{{ t('billing.base_price_remove') }}</button>
    </div>
    <p v-if="errors.base_price_history" class="field-error">{{ errors.base_price_history }}</p>
    <button type="button" class="btn ghost" data-base-add :disabled="rows.length >= 128" @click="add">{{ t('billing.base_price_add') }}</button>
  </fieldset>
</template>
