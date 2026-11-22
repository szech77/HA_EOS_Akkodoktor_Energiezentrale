<script setup lang="ts">
import { useDeviceStore } from '@/stores/device'
import type { PlanSection } from '@/utils/devicePage'

/** Next EOS instructions of a device, or a short note on what the forecast covers. */
defineProps<{ plan: PlanSection }>()
const { host } = useDeviceStore()
</script>

<template>
  <section id="plan" class="plan-panel">
    <h2 v-if="plan.title">{{ plan.title }}</h2>
    <template v-if="plan.items">
      <dl v-if="plan.items.length">
        <template v-for="item in plan.items" :key="item.time">
          <dt>{{ item.time }}</dt><dd>{{ item.mode }}</dd>
        </template>
      </dl>
      <p v-else>{{ host.t('plan.no_valid') }}</p>
    </template>
    <p v-if="plan.text">{{ plan.text }}</p>
  </section>
</template>
