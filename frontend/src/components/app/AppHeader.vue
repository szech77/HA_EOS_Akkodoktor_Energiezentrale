<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import NavBadge from '@/components/status/NavBadge.vue'
import type { ResolvedRoute } from '@/router'

/** Title bar with the main navigation; it stays at the top, so sticky parts keep clear of its height. */
defineProps<{ section: ResolvedRoute['section']; car: boolean; logo: string; t: (key: string) => string }>()
const header = ref<HTMLElement | null>(null)
let observer: ResizeObserver | null = null

const publish = () => document.documentElement.style.setProperty('--header-h', `${header.value?.offsetHeight ?? 0}px`)
onMounted(() => {
  publish()
  if (typeof ResizeObserver === 'function' && header.value) (observer = new ResizeObserver(publish)).observe(header.value)
})
onBeforeUnmount(() => observer?.disconnect())
</script>

<template>
  <header ref="header">
    <a class="brand" href="#overview">
      <svg class="energy-logo" viewBox="0 0 128 128" aria-hidden="true" focusable="false"><use :href="logo" /></svg>
      <span class="brand-wordmark"><strong>EOS</strong><span>{{ t('app.name') }}</span></span>
    </a>
    <nav :aria-label="t('nav.main')">
      <a href="#overview" data-route="overview" :aria-current="section === 'overview' ? 'page' : undefined">
        <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M3 11 12 4l9 7M5 10v10h14V10" /></svg><span>{{ t('nav.overview') }}</span>
      </a>
      <a v-if="car" href="#car" data-route="car" :aria-current="section === 'car' ? 'page' : undefined">
        <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M4 17H2v-5l3-2 2.5-5h7L18 10l3 1.5V17h-2M8 17h8" /><circle cx="6" cy="17" r="2" /><circle cx="18" cy="17" r="2" /></svg><span>{{ t('nav.car') }}</span>
      </a>
      <a href="#notices" data-route="notices" :aria-current="section === 'notices' ? 'page' : undefined">
        <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M6 16v-5a6 6 0 1 1 12 0v5l2 2H4l2-2M10 21h4" /></svg><span>{{ t('nav.notices') }}</span><NavBadge />
      </a>
      <a href="#settings" data-route="settings" :aria-current="section === 'settings' ? 'page' : undefined">
        <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="3" /><path d="M19 12a7 7 0 0 0-.1-1.2l2-1.6-2-3.4-2.4 1a7 7 0 0 0-2-1.2L14 3h-4l-.5 2.6a7 7 0 0 0-2 1.2l-2.4-1-2 3.4 2 1.6A7 7 0 0 0 5 12c0 .4 0 .8.1 1.2l-2 1.6 2 3.4 2.4-1a7 7 0 0 0 2 1.2L10 21h4l.5-2.6a7 7 0 0 0 2-1.2l2.4 1 2-3.4-2-1.6c.1-.4.1-.8.1-1.2Z" /></svg><span>{{ t('nav.settings') }}</span>
      </a>
    </nav>
  </header>
</template>
