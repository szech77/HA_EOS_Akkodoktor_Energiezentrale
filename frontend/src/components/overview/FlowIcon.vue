<script setup lang="ts">
import type { FlowKey } from '@/utils/energyFlow'

/** Line icon of a flow node; battery and car show their SoC as five bars (null hides the car bars). */
defineProps<{ device: FlowKey; bars: number | null }>()
const BATTERY_BARS = [4, 7, 10, 13, 16]
const CAR_BARS = ['6.4', '8.6', '10.8', '13', '15.2']
</script>

<template>
  <svg viewBox="0 0 24 24" focusable="false">
    <template v-if="device === 'solar'">
      <circle cx="12" cy="12" r="4" /><path d="M12 2.5v2.4M12 19.1v2.4M2.5 12h2.4M19.1 12h2.4M5.3 5.3 7 7M17 17l1.7 1.7M5.3 18.7 7 17M17 7l1.7-1.7" />
    </template>
    <path v-else-if="device === 'grid'" d="m8 21 3-18h2l3 18M7 7h10M5 12h14M9.2 14l5.5 5M14.8 14l-5.5 5M3 7v3m18-3v3M2 7h5m10 0h5M3 12v3m18-3v3M3 21h5m8 0h5" />
    <template v-else-if="device === 'battery'">
      <rect x="2" y="7" width="18" height="10" rx="2" /><path d="M22 10v4" />
      <rect v-for="(x, index) in BATTERY_BARS" :key="x" class="battery-bar" :class="{ filled: bars !== null && index < bars }" :x="x" y="9" width="2" height="6" rx="0.45" />
    </template>
    <template v-else-if="device === 'house'">
      <path d="M3 10.5 12 3l9 7.5M5.5 9v11h13V9M10 20v-6h4v6M16 4v3" /><path d="M8 11h.01M16 11h.01" />
    </template>
    <template v-else-if="device === 'car'">
      <path d="M4 18H2v-6l3-2 2.5-5h6.8L18 10l3 1.5a1.5 1.5 0 0 1 1 1.4V18h-2M8 18h8M5 10h13M11.5 5v5" /><circle cx="6" cy="18" r="2" /><circle cx="18" cy="18" r="2" />
      <g class="car-soc" :hidden="bars === null">
        <rect v-for="(x, index) in CAR_BARS" :key="x" class="car-soc-bar" :class="{ filled: bars !== null && index < bars }" :x="x" y="10.8" width="1.5" height="4.4" rx=".35" />
      </g>
    </template>
    <path v-else d="M3 6c3-5 6 5 9 0s6 5 9 0M3 12c3-5 6 5 9 0s6 5 9 0M3 18c3-5 6 5 9 0s6 5 9 0" />
  </svg>
</template>
