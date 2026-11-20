<script setup lang="ts">
import { computed } from 'vue'
import { useHost, useSnapshot } from '@/host/context'
import { isNumber } from '@/shared/format'
import WeatherIcon from '@/shared/WeatherIcon.vue'
import { usePvWeather } from '../state'
import type { ForecastHour } from '../types'

const host = useHost()
const snapshot = useSnapshot()
const { forecast, labels } = usePvWeather()

const weather = computed(() => snapshot.value.live?.weather ?? null)
const currentHour = computed(() =>
  (forecast.data.value?.hours ?? []).find((entry): entry is ForecastHour => entry.kind === 'hour' && entry.now === true))
const temperature = computed(() => {
  const value = weather.value?.temperature
  return isNumber(value) ? `${host.decimal(value, 0)} ${weather.value?.unit ?? ''}`.trim() : '—'
})
const meta = computed(() => labels.currentMeta(snapshot.value, currentHour.value))
</script>

<template>
  <div class="wx-now">
    <WeatherIcon :condition="weather?.condition" />
    <span class="temp">{{ temperature }}</span>
    <div class="wx-now-text">
      <b>{{ weather ? labels.condition(weather.condition) : host.t('pv.no_weather') }}</b>
      <div class="meta"><span v-for="item in meta" :key="item">{{ item }}</span></div>
    </div>
  </div>
</template>
