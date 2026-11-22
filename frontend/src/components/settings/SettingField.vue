<script setup lang="ts">
import { computed } from 'vue'
import { useSettingsStore } from '@/stores/settings'

/**
 * A labelled settings input with its field error. Editing the field removes the error; the
 * backend decides about the values, the browser only reports fields it cannot read.
 */
const props = defineProps<{ name: string; label: string; toggle?: boolean }>()
const { errors, clearError } = useSettingsStore()
const error = computed(() => errors[props.name])
</script>

<template>
  <label :class="{ switch: toggle, invalid: error }" @input="clearError(name)" @change="clearError(name)">
    <span v-if="toggle"><b>{{ label }}</b></span><span v-else>{{ label }}</span>
    <slot />
    <span v-if="error" class="field-error">{{ error }}</span>
  </label>
</template>
