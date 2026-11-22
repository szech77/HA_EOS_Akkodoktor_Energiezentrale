<script setup lang="ts">
import { useOverviewStore } from '@/stores/overview'
import type { FlowEntry, FlowNodeView } from '@/utils/energyFlow'
import FlowIcon from './FlowIcon.vue'

/** One node of the energy flow with power ring, SoC, age of a retained value and problem flag. */
defineProps<{ entry: FlowEntry; view: FlowNodeView }>()
const { host } = useOverviewStore()
</script>

<template>
  <a
    class="node"
    :class="[entry.key, entry.side, {
      'vehicle-inactive': view.inactiveCar,
      'grid-disconnected': view.inactiveGrid,
      'battery-low': view.low,
      'problem-error': view.problem === 'error',
      'problem-warning': view.problem === 'warning',
    }]"
    :style="{ '--x': `${entry.x}%`, '--y': `${entry.y}%` }"
    :href="entry.href"
    :data-node="entry.id"
    :title="view.title || undefined"
    :aria-label="view.label"
  >
    <span class="orb" :class="{ 'power-ring-enabled': view.ring }" aria-hidden="true">
      <svg v-if="view.ring" class="power-ring" viewBox="0 0 56 56" aria-hidden="true" :data-fraction="view.fraction ?? ''">
        <circle class="ring-track" cx="28" cy="28" r="26" />
        <circle class="ring-value" cx="28" cy="28" r="26" pathLength="100" transform="rotate(-90 28 28)" :stroke-dasharray="`${view.fraction === null ? 0 : view.fraction * 100} 100`" />
      </svg>
      <FlowIcon :device="entry.key" :bars="view.bars" />
      <span v-if="view.problem" class="flag" aria-hidden="true">!</span>
    </span>
    <span>{{ view.name }}</span>
    <strong :hidden="view.hideValue">{{ view.value }}</strong>
    <small v-if="view.age" class="reading-age">{{ view.age }}</small>
    <span v-if="entry.key === 'grid' && view.inactiveGrid" class="backup-indicator" aria-hidden="true" :title="host.t('power_supply.backup')">
      <svg viewBox="0 0 24 24"><path d="m3 11 9-8 9 8M5 10v11h14V10" /><path class="backup-bolt" d="m13 8-5 7h4l-1 5 6-8h-4z" /></svg>
    </span>
  </a>
</template>
