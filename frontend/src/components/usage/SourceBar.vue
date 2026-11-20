<script setup lang="ts">
import type { SourceBarModel } from '@/utils/usage'

/** Shares of PV, battery and grid (or of the PV uses) as one bar. */
defineProps<{ bar: SourceBarModel }>()
</script>

<template>
  <div v-if="bar.empty" class="source-bar empty"></div>
  <div v-else class="source-bar" :role="bar.label ? 'img' : undefined" :aria-label="bar.label || undefined" :aria-hidden="bar.label ? undefined : 'true'">
    <span v-for="(part, index) in bar.parts" :key="index" :style="{ width: `${part.share}%`, background: part.color }" :title="part.title || undefined"></span>
  </div>
</template>
