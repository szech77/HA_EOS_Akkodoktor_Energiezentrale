<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { useOverviewStore } from '@/stores/overview'
import type { WeatherNow } from '@/types/host'
import { flowLayout } from '@/utils/energyFlow'
import { isNumber } from '@/utils/format'
import { weatherShapes } from '@/utils/weatherShapes'
import FlowNode from './FlowNode.vue'

/** Live energy flow: sources left, consumers right, pulses scaled by power, weather and data age. */
const { host, snapshot, format, states, flow, logo } = useOverviewStore()
const { t } = host

// Narrow screens spread the columns outwards; follow the window size.
const width = ref(globalThis.innerWidth ?? 1000)
const resize = () => { width.value = globalThis.innerWidth ?? 1000 }
globalThis.addEventListener?.('resize', resize)
onBeforeUnmount(() => globalThis.removeEventListener?.('resize', resize))

const layout = computed(() => flowLayout(snapshot.value, width.value < 600))
const nodes = computed(() => layout.value.entries.map(entry => ({ entry, view: flow.node(entry, snapshot.value) })))

const weather = computed(() => {
  const value = snapshot.value.live['weather'] as WeatherNow | null | undefined
  if (!value) return null
  const temperature = isNumber(value.temperature) ? `${host.decimal(value.temperature)} ${value.unit ?? ''}`.trim() : '—'
  const description = `${states.state('weather', value.condition ?? undefined)} · ${temperature} · ${t('forecast.open')}`
  return { shapes: weatherShapes(value.condition), temperature, description }
})
const asOf = computed(() => {
  const time = Date.parse(String(snapshot.value.live['time'] ?? ''))
  if (!isNumber(time)) return t('status.no_readings')
  // A retained flow value makes the whole diagram as old as its oldest shown reading.
  const age = Math.max(0, ...(['solar', 'grid', 'car', 'battery'] as const).map(key => snapshot.value.flow_display?.[key]?.age_s ?? 0))
  return t('flow.as_of', { time: format.whenDated(time - age * 1000) })
})
const openWeather = () => { globalThis.location.hash = '#pv' }
</script>

<template>
  <div class="flow-panel">
    <div class="panel-heading">
      <h2>{{ t('flow.title') }}</h2>
      <button v-if="weather" type="button" class="flow-weather" :aria-label="weather.description" :title="weather.description" @click="openWeather">
        <svg viewBox="0 0 32 32" aria-hidden="true">
          <template v-for="(shape, index) in weather.shapes" :key="index">
            <circle v-if="'circle' in shape" :cx="shape.circle[0]" :cy="shape.circle[1]" :r="shape.circle[2]" />
            <path v-else :d="shape.path" />
          </template>
        </svg>
        <span>{{ weather.temperature }}</span>
      </button>
    </div>
    <div class="flow" :aria-label="t('flow.aria')" :style="{ height: `${layout.height}px` }">
      <svg class="wires" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
        <path class="wire" :d="layout.wires" />
        <path
          v-for="node in nodes"
          :key="node.entry.id"
          class="pulse"
          :class="[node.entry.key, { inactive: node.view.pulse.inactive, reverse: node.view.pulse.reverse }]"
          pathLength="100"
          :d="node.entry.d"
          :style="node.view.pulse.style"
        />
      </svg>
      <FlowNode v-for="node in nodes" :key="node.entry.id" :entry="node.entry" :view="node.view" />
      <a class="hub" href="#usage/total" :aria-label="t('flow.open_total')">
        <svg class="energy-logo" viewBox="0 0 128 128" aria-hidden="true" focusable="false"><use :href="logo" /></svg>
      </a>
    </div>
    <div class="flow-footer"><a class="plan-link" href="#energy">{{ t('flow.history_link') }}</a><span class="tag">{{ asOf }}</span></div>
  </div>
</template>
