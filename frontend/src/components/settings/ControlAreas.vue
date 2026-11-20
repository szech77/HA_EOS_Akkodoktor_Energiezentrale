<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { useSettingsStore } from '@/stores/settings'
import type { ControlArea, ControlKey } from '@/types/status'

/**
 * Storage and vehicle charging control are enabled separately; the backend reports which areas
 * have a matching device. Each change needs a confirmation.
 */
const props = defineProps<{ control: Readonly<Partial<Record<ControlKey, ControlArea>>> | undefined }>()
const { host, ready, control } = useSettingsStore()
const { t } = host
const { confirming, busy, result } = control
const root = ref<HTMLElement | null>(null)

const areas = computed(() => (['battery', 'vehicle'] as const).map(key => {
  const view = props.control?.[key]
  const available = Boolean(view?.available)
  const held = Boolean(view?.enabled || view?.release_pending)
  return {
    key,
    available,
    held,
    state: !available ? t(`control.area_unavailable.${key}`) : t(view?.release_pending ? 'control.area_releasing' : view?.enabled ? 'control.area_on' : 'control.area_off'),
    confirming: confirming.value === key && available,
  }
}))

async function ask(key: ControlKey) {
  control.ask(key)
  await nextTick()
  root.value?.querySelector<HTMLButtonElement>(`[data-control-area="${key}"] [data-area-action="confirm"]`)?.focus()
}
</script>

<template>
  <div id="control-areas" ref="root" class="control-areas">
    <div v-for="area in areas" :key="area.key" class="control-area" :data-control-area="area.key">
      <div><strong>{{ t(`control.area.${area.key}`) }}</strong><small class="control-area-state">{{ area.state }}</small></div>
      <button
        type="button"
        :class="area.held ? 'btn' : 'btn primary'"
        data-area-action="toggle"
        :hidden="!area.available"
        :disabled="!ready || busy || Boolean(confirming)"
        @click="ask(area.key)"
      >{{ t(area.held ? 'control.release' : 'control.take') }}</button>
      <div v-if="area.confirming" class="control-area-confirm">
        <p>{{ t(area.held ? `control.area_release_confirm.${area.key}` : `control.area_confirm.${area.key}`) }}</p>
        <div class="status-actions">
          <button type="button" :class="area.held ? 'btn danger' : 'btn primary'" data-area-action="confirm" :disabled="busy" @click="control.confirm(area.key)">
            {{ t(area.held ? 'control.release_confirm' : 'control.take_confirm') }}
          </button>
          <button type="button" class="btn ghost" data-area-action="cancel" :disabled="busy" @click="control.cancel()">{{ t('control.cancel') }}</button>
        </div>
      </div>
    </div>
  </div>
  <p id="control-result" class="footnote" role="status">{{ result }}</p>
</template>
