<script setup lang="ts">
import { computed, ref } from 'vue'
import { useDeviceStore } from '@/stores/device'
import type { ModeInterval } from '@/types/device'
import { DAY } from '@/utils/chartSeries'
import { MODES } from '@/utils/modes'

/** EOS modes of the last and next 24 h; a tapped interval explains itself below the track. */
const props = defineProps<{ device: 'battery' | 'car'; intervals: readonly ModeInterval[]; mode: string | null | undefined; vehicle?: string }>()
const { host, format, states, now } = useDeviceStore()
const { t } = host

const title = computed(() => (props.device === 'car' ? t('timeline.car_title', { vehicle: props.vehicle || 'E-Auto' }) : t('timeline.battery_title')))
const segments = computed(() => props.intervals.flatMap(({ start, end, mode, kind }) => {
  const label = mode ? states.mode(mode) : t('timeline.no_data')
  const color = mode && MODES[mode] ? MODES[mode][1] : 'edge'
  // Placed by time, so the centre line is "now" however many intervals EOS sends.
  const first = Math.max(start, now.value - DAY)
  const last = Math.min(end, now.value + DAY)
  if (last <= first) return []
  return [{
    id: `${kind}:${start}`,
    label,
    color,
    future: kind === 'plan',
    info: t('timeline.interval', { kind: t(`timeline.${kind}`), start: format.dateTime(start), end: format.dateTime(end), mode: label }),
    style: { '--start': (first - now.value + DAY) / (2 * DAY), '--duration': (last - first) / (2 * DAY), '--mode': `var(--${color})` },
  }]
}))
const legend = computed(() => [...new Map(segments.value.map(item => [item.label, item.color])).entries()])
const selected = ref<string | null>(null)
const detail = computed(() => segments.value.find(item => item.id === selected.value)?.info ?? states.mode(props.mode))
</script>

<template>
  <h2>{{ title }}</h2>
  <div class="mode-halves"><span>{{ t('timeline.history_range') }}</span><span>{{ t('timeline.plan_range') }}</span></div>
  <div class="mode-track" role="group" :aria-label="t('timeline.aria')">
    <button
      v-for="item in segments"
      :key="item.id"
      type="button"
      class="mode-segment"
      :class="{ future: item.future }"
      :style="item.style"
      :aria-label="item.info"
      :aria-pressed="selected === item.id"
      @click="selected = item.id"
    />
  </div>
  <div class="mode-legend"><span v-for="[label, color] in legend" :key="label"><i :style="{ '--mode': `var(--${color})` }" />{{ label }}</span></div>
  <p class="mode-detail" aria-live="polite">{{ detail }}</p>
</template>
