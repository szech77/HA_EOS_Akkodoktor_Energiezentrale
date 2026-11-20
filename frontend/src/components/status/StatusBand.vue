<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { useStatusStore } from '@/stores/status'
import type { ControlAction } from '@/utils/status'

/** Control state with cause and consequence; taking over or releasing control is confirmed inline. */
const store = useStatusStore()
const { texts, snapshot, car, confirming, busy, result, controllable } = store
const band = computed(() => texts.band(snapshot.value, car.value, confirming.value))
const confirmButton = ref<HTMLButtonElement | null>(null)

const ICONS: Readonly<Record<string, readonly string[]>> = {
  ok: ['m5 12 4 4 10-10'],
  wait: ['M12 7v5l3 2'],
  pause: ['M9 6v12M15 6v12'],
  off: ['M8 12h8'],
}
const circle = computed(() => band.value.icon === 'wait' || band.value.icon === 'off')

async function ask(action: ControlAction) {
  store.ask(action)
  await nextTick()
  confirmButton.value?.focus()
}
</script>

<template>
  <section id="status-band" class="status-band" :class="`tone-${band.tone}`" aria-live="polite">
    <span class="status-dot" aria-hidden="true">
      <svg viewBox="0 0 24 24"><circle v-if="circle" cx="12" cy="12" r="9" /><path v-for="d in ICONS[band.icon]" :key="d" :d="d" /></svg>
    </span>
    <div class="status-text">
      <h2>{{ band.title }}</h2>
      <p>{{ band.text }}</p>
      <p v-if="result" class="status-result" role="status">{{ result }}</p>
    </div>
    <div class="status-actions">
      <button type="button" class="btn" :class="{ primary: band.action === 'take' }" :data-control="band.action" :disabled="!controllable || busy || confirming !== null" @click="ask(band.action)">
        <span class="label-long">{{ band.long }}</span><span class="label-short">{{ band.short }}</span>
      </button>
    </div>
    <div v-if="band.confirm" class="status-confirm">
      <b>{{ band.confirm.title }}</b>
      <ul><li v-for="item in band.confirm.items" :key="item">{{ item }}</li></ul>
      <div class="status-actions">
        <button ref="confirmButton" type="button" class="btn" data-control="confirm" :class="band.confirm.danger ? 'danger' : 'primary'" :disabled="busy" @click="store.confirm()">{{ band.confirm.label }}</button>
        <button type="button" class="btn ghost" data-control="cancel" :disabled="busy" @click="store.cancel()">{{ store.host.t('control.cancel') }}</button>
      </div>
    </div>
  </section>
</template>
