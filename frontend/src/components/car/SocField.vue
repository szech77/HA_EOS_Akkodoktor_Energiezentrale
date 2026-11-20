<script setup lang="ts">
import { computed } from 'vue'
import { useCarStore } from '@/stores/car'

/**
 * SoC input with a slider; both edit the same value and show the expected range.
 * `edit` fires while typing or dragging, `commit` when the field changes or the slider is released.
 */
const props = defineProps<{ label: string; name?: string; factor: number | null }>()
const value = defineModel<number | ''>({ required: true })
const emit = defineEmits<{ edit: []; commit: [] }>()
const { host, labels } = useCarStore()

const known = computed(() => value.value !== '' && value.value >= 1 && value.value <= 100)
const shown = computed(() => (known.value ? labels.socWithRange(Number(value.value), props.factor) : ''))

function typed(event: Event) {
  const text = (event.target as HTMLInputElement).value
  value.value = text === '' ? '' : Number(text)
  emit('edit')
}
function slid(event: Event) {
  value.value = Math.max(1, Math.min(100, Math.round(Number((event.target as HTMLInputElement).value))))
  emit('edit')
}
</script>

<template>
  <div class="soc-field">
    <label>
      <span>{{ label }}</span>
      <input :name="name" type="number" min="1" max="100" required :value="value" @input="typed" @change="emit('commit')">
    </label>
    <div class="soc-slide">
      <span>{{ host.t('car.slider_soc_label') }}</span>
      <input type="range" class="soc-slider" min="1" max="100" step="1" :value="known ? value : 50" :aria-label="host.t('car.slider_soc')" @input="slid" @change="emit('commit')">
      <output aria-live="polite">{{ shown }}</output>
    </div>
  </div>
</template>
