<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import CarNav from '@/components/car/CarNav.vue'
import ChargePlanPanel from '@/components/car/ChargePlanPanel.vue'
import ChargingForm from '@/components/car/ChargingForm.vue'
import FleetCards from '@/components/car/FleetCards.vue'
import GoalCard from '@/components/car/GoalCard.vue'
import GoalsEditor from '@/components/car/GoalsEditor.vue'
import ChartPanel from '@/components/device/ChartPanel.vue'
import KpiCards from '@/components/device/KpiCards.vue'
import ModeTimeline from '@/components/device/ModeTimeline.vue'
import PlanSection from '@/components/device/PlanSection.vue'
import { useCarStore } from '@/stores/car'
import { useDeviceStore } from '@/stores/device'

/**
 * Car pages. "All vehicles" compares the vehicles; a vehicle page answers goal and plan first,
 * then shows its charging switches, goals, charts and – without an EOS charging plan – key
 * figures and the next EOS instructions.
 */
const { host, route, vehicle, fleet, scrollToPlan } = useCarStore()
const { data, page } = useDeviceStore()
const plan = computed(() => vehicle.value?.charge_plan ?? null)
const planPanel = ref<InstanceType<typeof ChargePlanPanel> | null>(null)

const cards = computed(() => (data.value && !fleet.value && !plan.value ? page.cards('car', data.value) : []))
const charts = computed(() => (data.value ? (fleet.value ? page.fleetCharts(data.value) : page.charts('car', data.value)) : []))
const instructions = computed(() => {
  if (fleet.value) return { text: host.t('fleet.forecast_note') }
  return data.value && !plan.value ? page.plan('car', data.value) : null
})
const inactive = computed(() => Boolean(data.value && !page.vehicleActive(data.value.snapshot)))

async function showPlan() {
  scrollToPlan.value = false
  await nextTick()
  const element = (planPanel.value?.$el as HTMLElement | undefined) ?? null
  const reduced = globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? true
  element?.scrollIntoView?.({ block: 'start', behavior: reduced ? 'auto' : 'smooth' })
}
watch([scrollToPlan, plan], ([wanted, current]) => {
  if (wanted && current) void showPlan()
}, { immediate: true })
</script>

<template>
  <template v-if="data">
    <CarNav />
    <a class="back usage-link" :href="`#usage/${route.key}`">{{ host.t('billing.open') }}</a>
    <FleetCards v-if="fleet" />
    <div v-else-if="vehicle" id="car-view" :key="vehicle.id ?? ''">
      <div class="car-top">
        <GoalCard v-if="plan" :plan="plan" :live="vehicle.live" @to-plan="showPlan" />
        <ChargingForm />
      </div>
      <ChargePlanPanel v-if="plan" ref="planPanel" :plan="plan" />
    </div>
    <GoalsEditor v-if="vehicle && !fleet" :key="vehicle.id ?? ''" />
    <KpiCards v-if="cards.length" :cards="cards" :inactive="inactive" />
    <ChartPanel :charts="charts">
      <template v-if="!fleet" #timeline>
        <ModeTimeline device="car" :intervals="data.snapshot.mode_timeline?.car ?? []" :mode="vehicle?.live.car_mode" :vehicle="data.snapshot.vehicle_name ?? ''" />
      </template>
    </ChartPanel>
    <PlanSection v-if="instructions" :plan="instructions" />
  </template>
</template>
