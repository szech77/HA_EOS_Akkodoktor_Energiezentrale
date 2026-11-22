<script setup lang="ts">
import { computed } from 'vue'
import { isNumber } from '@/utils/format'

/** Car symbol with five SoC bars (as in the energy flow); no bars without a valid SoC. */
const props = defineProps<{ soc?: number | null | undefined }>()
const filled = computed(() => (isNumber(props.soc) && props.soc >= 0 && props.soc <= 100 ? Math.ceil(props.soc / 20) : null))
const bars = [0, 1, 2, 3, 4].map(index => ({ index, x: (6.4 + index * 2.2).toFixed(1) }))
</script>

<template>
  <svg class="vehicle-soc-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
    <path d="M4 18H2v-6l3-2 2.5-5h6.8L18 10l3 1.5a1.5 1.5 0 0 1 1 1.4V18h-2M8 18h8M5 10h13M11.5 5v5" />
    <circle cx="6" cy="18" r="2" />
    <circle cx="18" cy="18" r="2" />
    <g class="car-soc" :hidden="filled === null">
      <rect v-for="bar in bars" :key="bar.index" class="car-soc-bar" :class="{ filled: filled !== null && bar.index < filled }" :x="bar.x" y="10.8" width="1.5" height="4.4" rx=".35" />
    </g>
  </svg>
</template>
