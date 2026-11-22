<script setup lang="ts">
import { computed } from 'vue'
import { useHost } from '@/composables/useHost'
import WeatherIcon from '@/components/weather/WeatherIcon.vue'
import { usePvWeatherStore } from '@/stores/pvWeather'

const host = useHost()
const { forecast, labels } = usePvWeatherStore()
const days = computed(() => (forecast.data.value?.days ?? []).map(day => ({ day, text: labels.day(day) })))
</script>

<template>
  <div class="wx-days" role="list" :aria-label="host.t('pv.days_aria')">
    <div v-for="{ day, text } in days" :key="day.date" class="wx-day" role="listitem">
      <div class="hd"><b>{{ text.name }}</b><WeatherIcon v-if="day.condition" :condition="day.condition" /></div>
      <small>{{ text.weather }}</small>
      <strong>{{ text.energy }}</strong>
      <small v-if="text.note">{{ text.note }}</small>
    </div>
  </div>
</template>
