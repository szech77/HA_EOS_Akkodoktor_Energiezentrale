<script setup lang="ts">
import { computed } from 'vue'
import { isNumber } from '@/shared/format'
import { useCar } from '../state'
import CarIcon from './CarIcon.vue'

/** One card per vehicle: power, SoC, mode, goal and departure; opens the vehicle page. */
const { host, vehicles, labels, format, states } = useCar()

const cards = computed(() => vehicles.value.map(vehicle => {
  const live = vehicle.live
  const active = labels.vehicleActive(vehicle)
  // A missing power reading shows the retained value as an approximation.
  const retained = !isNumber(live.car) && isNumber(vehicle.display?.car?.value)
  return {
    id: vehicle.id ?? '',
    href: `#car/${encodeURIComponent(vehicle.id ?? '')}`,
    name: vehicle.name ?? '',
    active,
    soc: isNumber(live.car_soc) ? live.car_soc : vehicle.display?.car_soc?.value,
    power: active ? (retained ? '≈ ' : '') + format.power(isNumber(live.car) ? live.car : vehicle.display?.car?.value) : labels.vehicleStatus(vehicle),
    state: `${format.percentText(live.car_soc)} · ${states.mode(live.car_mode)}`,
    goal: `${host.t('metric.target')} ${format.percentText(vehicle.charge_target_soc ?? vehicle.settings.target_soc)} · ${live.departure ? format.whenDated(live.departure) : host.t('metric.no_departure')}`,
  }
}))
</script>

<template>
  <div class="kpis fleet-cards">
    <a v-for="card in cards" :key="card.id" class="vehicle-card" :class="{ 'vehicle-inactive': !card.active }" :href="card.href">
      <small class="vehicle-heading"><CarIcon :soc="card.soc" />{{ card.name }}</small>
      <strong>{{ card.power }}</strong>
      <span>{{ card.state }}</span>
      <span class="dim">{{ card.goal }}</span>
    </a>
  </div>
</template>
