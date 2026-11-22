<script setup lang="ts">
import { computed } from 'vue'
import NoticeCard from '@/components/status/NoticeCard.vue'
import StatusBand from '@/components/status/StatusBand.vue'
import { useStatusStore } from '@/stores/status'
import { toneOf } from '@/utils/status'

/**
 * Shown above every page: the status band, the two most important notices and, on small screens,
 * the pill. The notices page lists all notices itself.
 */
const { host, notices, ready, route, texts } = useStatusStore()
const onNotices = computed(() => route.value === 'notices')
const pill = computed(() => {
  const notice = notices.value[0]
  if (!notice) return null
  const more = notices.value.length > 1 ? ` · ${host.t('notice_card.more', { count: notices.value.length - 1 })}` : ''
  return { tone: toneOf(notice.severity), severity: host.t(`notice_card.${notice.severity ?? 'warning'}`), text: texts.noticeText(notice) + more }
})
</script>

<template>
  <div id="status-view">
    <StatusBand v-if="ready" />
    <template v-if="!onNotices">
      <div v-if="notices.length" id="top-notices" class="notices">
        <NoticeCard v-for="(notice, index) in notices.slice(0, 2)" :key="notice.id ?? `${notice.message}:${index}`" :notice="notice" compact />
      </div>
      <a v-if="pill" id="notice-pill" class="notice-pill" :class="`tone-${pill.tone}`" href="#notices">
        <span class="sev">{{ pill.severity }}</span><span class="txt">{{ pill.text }}</span><span aria-hidden="true">→</span>
      </a>
    </template>
  </div>
</template>
