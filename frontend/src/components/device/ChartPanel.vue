<script setup lang="ts">
import { useDeviceStore } from '@/stores/device'
import type { ChartSpec } from '@/utils/chartSeries'
import TimeSeriesChart from './TimeSeriesChart.vue'

/** Charts of a device page with the measured/forecast legend; the mode timeline goes in the slot. */
defineProps<{ charts: readonly ChartSpec[] }>()
const { host } = useDeviceStore()
</script>

<template>
  <section class="chart-panel">
    <div class="chart-legend">
      <span>{{ host.t('chart.measured') }}</span><span>{{ host.t('chart.forecast') }}</span><span>{{ host.t('chart.now_marker') }}</span>
    </div>
    <div id="timeline"><slot name="timeline" /></div>
    <div id="charts">
      <TimeSeriesChart v-for="chart in charts" :key="chart.id" :spec="chart" />
    </div>
  </section>
</template>
