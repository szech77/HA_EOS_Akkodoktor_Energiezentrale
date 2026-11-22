<script setup lang="ts">
import { computed } from 'vue'
import { useHost, useSnapshot } from '@/composables/useHost'
import { usePvWeatherStore } from '@/stores/pvWeather'

const host = useHost()
const snapshot = useSnapshot()
const { labels } = usePvWeatherStore()
// Effects are derived by the backend from the EOS plan; unknown kinds are skipped.
const effects = computed(() =>
  (snapshot.value.pv_effects ?? []).flatMap((item, index) => {
    const row = labels.effect(item, snapshot.value)
    return row ? [{ key: `${item.id}-${index}`, ...row }] : []
  }))
</script>

<template>
  <div class="list">
    <p v-if="!effects.length" class="footnote">{{ host.t('pv.effects_none') }}</p>
    <template v-for="row in effects" :key="row.key">
      <a v-if="row.href" class="row rowlink" :href="row.href">
        <span><b>{{ row.title }}</b><br /><small>{{ row.detail }}</small></span>
        <span class="tag accent">{{ row.tag }} →</span>
      </a>
      <div v-else class="row">
        <span><b>{{ row.title }}</b><br /><small>{{ row.detail }}</small></span>
        <span class="tag">{{ row.tag }}</span>
      </div>
    </template>
  </div>
</template>
