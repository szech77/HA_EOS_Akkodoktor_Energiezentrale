<script setup lang="ts">
import { computed } from 'vue'
import SourceBar from '@/components/usage/SourceBar.vue'
import { useUsageStore } from '@/stores/usage'
import type { Report } from '@/types/usage'

/** Today's consumption, feed-in and total on the overview; each tile opens its report. */
const props = defineProps<{ report: Report | null | undefined }>()
const { host, text } = useUsageStore()
const balance = computed(() => text.dayBalance(props.report))
</script>

<template>
  <section v-if="balance" id="day-balance" class="plan-panel">
    <div class="panel-heading"><h2>{{ host.t('billing.today') }}</h2><span>{{ host.t('billing.total') }}: {{ balance.total }}</span></div>
    <div class="balance-grid">
      <a v-for="tile in balance.tiles" :key="tile.href" class="balance-card" :class="{ feed: tile.feed }" :href="tile.href">
        <span>{{ tile.name }}</span><strong>{{ tile.value }}</strong><span>{{ tile.context }}</span>
        <SourceBar v-if="tile.bar" :bar="tile.bar" />
        <small class="more">{{ host.t('usage.open') }}</small>
      </a>
    </div>
    <p class="footnote">{{ balance.note }}</p>
  </section>
</template>
