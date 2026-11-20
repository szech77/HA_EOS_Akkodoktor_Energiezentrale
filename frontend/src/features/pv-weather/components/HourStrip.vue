<script setup lang="ts">
import { computed } from 'vue'
import { useHost } from '@/host/context'
import { isNumber } from '@/shared/format'
import WeatherIcon from '@/shared/WeatherIcon.vue'
import { usePvWeather } from '../state'
import type { ForecastHour } from '../types'

const host = useHost()
const { forecast, selected, format, labels } = usePvWeather()

const entries = computed(() => forecast.data.value?.hours ?? [])
// Bars are relative to the strongest hour; at least 0.1 kWh keeps dark days flat.
const maximum = computed(() =>
  Math.max(0.1, ...entries.value.flatMap(entry => (entry.kind === 'hour' && isNumber(entry.pv_kwh) ? [entry.pv_kwh] : []))))
const barHeight = (item: ForecastHour) => (isNumber(item.pv_kwh) ? `${Math.round((item.pv_kwh / maximum.value) * 100)}%` : '0%')
</script>

<template>
  <div class="wx-strip" role="list" :aria-label="host.t('pv.strip_aria')">
    <p v-if="!entries.length" class="footnote">{{ host.t('pv.no_hours') }}</p>
    <template v-for="(item, index) in entries" :key="item.start">
      <div v-if="item.kind === 'night'" class="wx-gap" role="listitem">
        {{ host.t('pv.night') }}<br />{{ labels.nightText(item) }}<br />
        <small>{{ format.clock(item.start) }}–{{ format.clock(item.end) }}</small>
      </div>
      <button v-else type="button" role="listitem" class="wx-h" :class="{ now: item.now }"
              :aria-pressed="selected === item.start" :aria-label="labels.hourText(item)" @click="selected = item.start">
        <span class="t">{{ labels.hourLabel(item, index, entries) }}</span>
        <WeatherIcon :condition="item.condition" />
        <span class="tmp">{{ format.temperature(item.temperature) }}</span>
        <span class="pvbar"><i :style="{ height: barHeight(item) }" /></span>
        <span class="kwh">{{ isNumber(item.pv_kwh) ? host.decimal(item.pv_kwh, 1) : '—' }}</span>
        <span class="cc">{{ isNumber(item.cloud_coverage) ? `☁ ${host.decimal(item.cloud_coverage, 0)} %` : '' }}</span>
      </button>
    </template>
  </div>
</template>
