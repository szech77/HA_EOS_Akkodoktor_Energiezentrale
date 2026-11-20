<script setup lang="ts">
import { useDeviceStore } from '@/stores/device'

/** Frame of the device pages: back to the overview, title and the way to the settings. */
defineProps<{ title: string }>()
const { host } = useDeviceStore()
</script>

<template>
  <a class="back" href="#overview">{{ host.t('nav.back') }}</a>
  <div class="page-top">
    <div><p class="eyebrow">{{ host.t('section.device') }}</p><h1>{{ title }}</h1></div>
    <a class="back" href="#settings">{{ host.t('nav.settings') }}</a>
  </div>
  <slot />
</template>
