<script setup lang="ts">
import { computed } from 'vue'
import NoticeCard from '@/components/status/NoticeCard.vue'
import { useStatusStore } from '@/stores/status'

/** All open notices, most severe first, and the notices resolved in the last 24 hours. */
const { host, notices, snapshot, texts } = useStatusStore()
const { t } = host
const count = computed(() => (notices.value.length ? t('notice_card.open_count', { count: notices.value.length }) : t('notice_card.none_open')))
const resolved = computed(() => (snapshot.value.resolved_notices ?? []).map((item, index) => ({ key: `${item.id ?? item.code}:${item.at}:${index}`, ...texts.resolved(item) })))
</script>

<template>
  <a class="back" href="#overview">{{ t('nav.back') }}</a>
  <div class="page-top">
    <div><p class="eyebrow">{{ t('section.notices') }}</p><h1>{{ t('nav.notices') }}</h1></div>
    <span class="tag">{{ count }}</span>
  </div>
  <div class="notices">
    <NoticeCard v-for="(notice, index) in notices" :key="notice.id ?? `${notice.message}:${index}`" :notice="notice" />
    <div v-if="!notices.length" class="plan-panel">
      <b>{{ t('notice_card.all_clear') }}</b><p class="footnote">{{ t('notice_card.all_clear_text') }}</p>
    </div>
  </div>
  <section v-if="resolved.length" class="plan-panel">
    <h2>{{ t('notice_card.resolved_title') }}</h2>
    <div class="list">
      <div v-for="item in resolved" :key="item.key" class="row">
        <span><b>{{ item.text }}</b><br><small>{{ item.detail }}</small></span><span class="tag">{{ item.tag }}</span>
      </div>
    </div>
  </section>
  <p class="footnote">{{ t('control.restart_info') }}</p>
</template>
