<script setup lang="ts">
import DeviceLayout from '@/layouts/DeviceLayout.vue'
import { useDeviceStore } from '@/stores/device'
import CarView from '@/views/CarView.vue'
import DeviceView from '@/views/DeviceView.vue'

/** Chooses the device page for the route app.js passes; replaced by the Vue router later. */
const { route, title } = useDeviceStore()
</script>

<template>
  <DeviceLayout :title="title">
    <CarView v-if="route.device === 'car'" />
    <DeviceView v-else :key="route.key" />
  </DeviceLayout>
</template>
