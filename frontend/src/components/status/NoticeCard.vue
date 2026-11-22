<script setup lang="ts">
import { computed } from 'vue'
import { useStatusStore } from '@/stores/status'
import type { Notice } from '@/types/status'

/** One notice: severity, text and – in full form – id, age and the page that helps. */
const props = defineProps<{ notice: Notice; compact?: boolean }>()
const { texts } = useStatusStore()
const card = computed(() => texts.card(props.notice, props.compact ?? false))
</script>

<template>
  <div class="notice-card" :class="`tone-${card.tone}`" :role="card.tone === 'crit' ? 'alert' : 'status'">
    <span class="sev">{{ card.severity }}</span>
    <div><b>{{ card.text }}</b><small v-if="card.meta">{{ card.meta }}</small></div>
    <a v-if="card.link" :href="card.link">{{ card.linkText }}</a>
    <span v-else />
  </div>
</template>
