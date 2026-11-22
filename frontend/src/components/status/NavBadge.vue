<script setup lang="ts">
import { computed } from 'vue'
import { useStatusStore } from '@/stores/status'
import { toneOf } from '@/utils/status'

/** Number of open notices in the navigation, in the tone of the most severe one. */
const { notices } = useStatusStore()
const first = computed(() => notices.value[0])
</script>

<template>
  <span id="nav-badge"><span v-if="first" class="badge" :class="`tone-${toneOf(first.severity)}`">{{ notices.length }}</span></span>
</template>
