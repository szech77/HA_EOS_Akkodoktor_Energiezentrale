<script setup lang="ts">
import type { Card } from '@/utils/devicePage'

/** Key figures of a device page; `inactive` greys them out, e.g. for a disconnected vehicle. */
defineProps<{ cards: readonly Card[]; inactive?: boolean }>()
</script>

<template>
  <div class="kpis" :class="{ 'vehicle-inactive': inactive }">
    <div v-for="card in cards" :key="card.title">
      <small>{{ card.title }}</small><strong>{{ card.value }}</strong><small>{{ card.context }}</small>
    </div>
  </div>
</template>
