<script setup lang="ts">
import type { StartupFailure } from '@/stores/app'
import { reloadPanel } from '@/utils/reload'

/** Why the panel cannot be shown, a retry that reloads all UI files and the technical details. */
defineProps<{ failure: StartupFailure; t: (key: string) => string }>()
</script>

<template>
  <div class="startup-failure">
    <p class="startup-notice" role="status">{{ failure.message }}</p>
    <button type="button" class="startup-retry" @click="reloadPanel()">{{ t('startup.retry') }}</button>
    <details class="startup-details"><summary>{{ t('startup.details') }}</summary><code>{{ failure.detail }}</code></details>
  </div>
</template>
