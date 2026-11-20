<script setup lang="ts">
import { computed } from 'vue'
import { isNumber } from '@/shared/format'
import { useCar } from '../state'

const props = defineProps<{ soc?: number | null | undefined; target?: number | null | undefined }>()
const { labels } = useCar()

// Circumference of the r=48 circle; the dash length draws the SoC, a short dash marks the target.
const CIRCLE = 301.6
const text = computed(() => labels.ring(props.soc, props.target))
const value = computed(() => (isNumber(props.soc) ? Math.max(0, Math.min(100, props.soc)) : 0))
const goal = computed(() => (isNumber(props.target) ? (-props.target / 100 * CIRCLE).toFixed(1) : null))
</script>

<template>
  <svg class="soc-ring" viewBox="0 0 120 120" role="img" :aria-label="text.label">
    <circle class="t" cx="60" cy="60" r="48" />
    <circle class="v" cx="60" cy="60" r="48" :stroke-dasharray="`${(value / 100 * CIRCLE).toFixed(1)} ${CIRCLE}`" transform="rotate(-90 60 60)" />
    <circle v-if="goal !== null" class="goal" cx="60" cy="60" r="48" :stroke-dasharray="`2 ${CIRCLE}`" :stroke-dashoffset="goal" transform="rotate(-90 60 60)" />
    <text x="60" y="62" text-anchor="middle">{{ text.value }}</text>
    <text v-if="text.target" class="sub" x="60" y="80" text-anchor="middle">{{ text.target }}</text>
  </svg>
</template>
