<script setup lang="ts">
import { computed } from 'vue'
import { useHost, useSnapshot } from '@/composables/useHost'
import CurrentWeather from '@/components/weather/CurrentWeather.vue'
import DayCards from '@/components/weather/DayCards.vue'
import HourStrip from '@/components/weather/HourStrip.vue'
import PlanEffects from '@/components/weather/PlanEffects.vue'
import { usePvWeatherStore } from '@/stores/pvWeather'
import type { ForecastHour } from '@/types/pvWeather'

const host = useHost()
const snapshot = useSnapshot()
const { forecast, selected, format, labels } = usePvWeatherStore()

const status = forecast.status
const loaded = computed(() => status.value !== 'loading')
const source = computed(() => {
  const data = forecast.data.value
  return [data?.source, data?.fetched_at ? host.t('pv.updated', { time: format.clock(data.fetched_at) }) : ''].filter(Boolean).join(' · ')
})
const detail = computed(() => {
  const item = (forecast.data.value?.hours ?? []).find((entry): entry is ForecastHour => entry.kind === 'hour' && entry.start === selected.value)
  return item ? labels.hourText(item) : host.t('pv.hour_hint')
})
</script>

<template>
  <div class="pv-head">
    <p class="eyebrow">{{ host.t('pv.eyebrow') }}</p>
    <h1>{{ host.t('pv.title') }}</h1>
    <p class="dim">{{ labels.lead(snapshot) }}</p>
  </div>
  <section class="plan-panel">
    <div class="panel-heading">
      <h2>{{ host.t('pv.forecast_title') }}</h2>
      <span v-if="source" class="tag">{{ source }}</span>
    </div>
    <CurrentWeather />
    <p v-if="status !== 'available'" class="footnote" role="status">{{ host.t('forecast.' + status) }}</p>
    <template v-if="loaded">
      <HourStrip />
      <p class="mode-detail" aria-live="polite">{{ detail }}</p>
      <DayCards />
    </template>
  </section>
  <section class="plan-panel">
    <h2>{{ host.t('pv.effects_title') }}</h2>
    <PlanEffects />
  </section>
  <div class="pv-links">
    <a class="plan-link" href="#solar">{{ host.t('pv.history_link') }}</a>
    <a class="plan-link" href="#usage/grid">{{ host.t('pv.grid_link') }}</a>
  </div>
</template>
