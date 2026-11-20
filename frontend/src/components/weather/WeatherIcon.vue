<script setup lang="ts">
import { computed } from 'vue'
import { weatherShapes } from '@/utils/weatherShapes'

const props = defineProps<{ condition?: string | null | undefined }>()
const shapes = computed(() => weatherShapes(props.condition))
</script>

<template>
  <svg class="wx-ico" viewBox="0 0 32 32" aria-hidden="true" focusable="false">
    <template v-for="(shape, index) in shapes" :key="index">
      <circle v-if="'circle' in shape" :cx="shape.circle[0]" :cy="shape.circle[1]" :r="shape.circle[2]" />
      <path v-else :d="shape.path" />
    </template>
  </svg>
</template>
