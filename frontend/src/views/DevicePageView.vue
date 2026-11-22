<script setup lang="ts">
import DeviceLayout from '@/layouts/DeviceLayout.vue'
import { useDeviceStore } from '@/stores/device'
import CarView from '@/views/CarView.vue'
import DeviceView from '@/views/DeviceView.vue'

/** Device and car pages: the car pages have their own view, all others share the device view. */
const { route, title } = useDeviceStore()
</script>

<template>
  <div id="device-view">
    <DeviceLayout :title="title">
      <CarView v-if="route.device === 'car'" />
      <DeviceView v-else :key="route.key" />
    </DeviceLayout>
  </div>
</template>
