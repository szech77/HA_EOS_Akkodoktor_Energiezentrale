<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import CarNav from '@/components/car/CarNav.vue'
import ChargePlanPanel from '@/components/car/ChargePlanPanel.vue'
import ChargingForm from '@/components/car/ChargingForm.vue'
import FleetCards from '@/components/car/FleetCards.vue'
import GoalCard from '@/components/car/GoalCard.vue'
import GoalsEditor from '@/components/car/GoalsEditor.vue'
import { useCarStore } from '@/stores/car'

/**
 * Car pages: "All vehicles" compares the vehicles; a vehicle page shows its goal, charging
 * switches, EOS plan and goals. Title, key figures and charts stay in the panel (app.js).
 */
const { host, route, vehicle, fleet, scrollToPlan } = useCarStore()
const plan = computed(() => vehicle.value?.charge_plan ?? null)
const planPanel = ref<InstanceType<typeof ChargePlanPanel> | null>(null)

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
</template>
