<script setup lang="ts">
import { computed } from 'vue'
import NoticeCard from '@/components/status/NoticeCard.vue'
import StatusBand from '@/components/status/StatusBand.vue'
import { useStatusStore } from '@/stores/status'
import { toneOf } from '@/utils/status'
import NoticesView from '@/views/NoticesView.vue'

/**
 * Shown on every page: the status band, the two most important notices (pill on small screens)
 * and the count in the navigation. The notices page is rendered into its section of app.js.
 */
const { host, notices, ready, route, texts } = useStatusStore()
const onNotices = computed(() => route.value === 'notices')
const first = computed(() => notices.value[0])
const pill = computed(() => {
  const notice = first.value
  if (!notice) return null
  const more = notices.value.length > 1 ? ` · ${host.t('notice_card.more', { count: notices.value.length - 1 })}` : ''
  return { tone: toneOf(notice.severity), severity: host.t(`notice_card.${notice.severity ?? 'warning'}`), text: texts.noticeText(notice) + more }
})
</script>

<template>
  <StatusBand v-if="ready" />
  <template v-if="!onNotices">
    <div v-if="notices.length" id="top-notices" class="notices">
      <NoticeCard v-for="(notice, index) in notices.slice(0, 2)" :key="notice.id ?? `${notice.message}:${index}`" :notice="notice" compact />
    </div>
    <a v-if="pill" id="notice-pill" class="notice-pill" :class="`tone-${pill.tone}`" href="#notices">
      <span class="sev">{{ pill.severity }}</span><span class="txt">{{ pill.text }}</span><span aria-hidden="true">→</span>
    </a>
  </template>
  <Teleport to="#nav-badge">
    <span v-if="first" class="badge" :class="`tone-${toneOf(first.severity)}`">{{ notices.length }}</span>
  </Teleport>
  <Teleport v-if="onNotices" to="#notices-view">
    <NoticesView />
  </Teleport>
</template>
