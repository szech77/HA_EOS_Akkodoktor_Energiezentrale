<script setup lang="ts">
import { computed } from 'vue'
import { useCar } from '../state'

/** "All vehicles" and one link per vehicle; only with several vehicles. */
const { host, vehicles, route } = useCar()
const links = computed(() => [
  { href: '#car', label: host.t('fleet.all'), current: route.value.vehicleId === null },
  ...vehicles.value.map(vehicle => ({
    href: `#car/${encodeURIComponent(vehicle.id ?? '')}`,
    label: vehicle.name ?? '',
    current: vehicle.id === route.value.vehicleId,
  })),
])
</script>

<template>
  <nav v-if="vehicles.length > 1" class="subnav car-nav" :aria-label="host.t('fleet.choose')">
    <a v-for="link in links" :key="link.href" :href="link.href" :aria-current="link.current ? 'page' : undefined">{{ link.label }}</a>
  </nav>
</template>
