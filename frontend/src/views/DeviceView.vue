<script setup lang="ts">
import { computed } from 'vue'
import ChartPanel from '@/components/device/ChartPanel.vue'
import KpiCards from '@/components/device/KpiCards.vue'
import ModeTimeline from '@/components/device/ModeTimeline.vue'
import PlanSection from '@/components/device/PlanSection.vue'
import { useDeviceStore } from '@/stores/device'

/** PV, grid, battery, house, heat pump and the energy balance: key figures, charts and plan. */
const { host, route, data, page } = useDeviceStore()
const device = computed(() => route.value.device)
const cards = computed(() => (data.value ? page.cards(device.value, data.value) : []))
const charts = computed(() => (data.value ? page.charts(device.value, data.value) : []))
const plan = computed(() => (data.value ? page.plan(device.value, data.value) : null))
const usage = computed(() => device.value === 'house' || device.value === 'heat')
</script>

<template>
  <a v-if="usage" class="back usage-link" :href="`#usage/${route.key}`">{{ host.t('billing.open') }}</a>
  <KpiCards :cards="cards" />
  <ChartPanel :charts="charts">
    <template v-if="device === 'battery' && data" #timeline>
      <ModeTimeline device="battery" :intervals="data.snapshot.mode_timeline?.battery ?? []" :mode="data.snapshot.live['battery_mode'] as string | undefined" />
    </template>
  </ChartPanel>
  <PlanSection v-if="plan" :plan="plan" />
</template>
