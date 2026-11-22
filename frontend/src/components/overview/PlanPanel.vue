<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useOverviewStore } from '@/stores/overview'
import { consumerEnabled } from '@/utils/devicePage'

/** EOS battery plan of the last 3 and next 12 hours, and the collapsible list of what happens next. */
const { host, snapshot, now, plan } = useOverviewStore()
const { t } = host

const track = computed(() => plan.track(snapshot.value, now.value))
const events = computed(() => plan.events(snapshot.value))
const selected = ref<string | null>(null)
const detail = computed(() => track.value?.segments.find(item => item.id === selected.value)?.info ?? t('plan.track_hint'))
const car = computed(() => consumerEnabled(snapshot.value, 'car'))

// Opened or closed is a per-viewer convenience; blocked storage keeps the list open.
const STORAGE = 'eos-energiezentrale.next-events-open'
function stored(): boolean {
  try {
    return globalThis.localStorage?.getItem(STORAGE) !== '0'
  } catch {
    return true
  }
}
const open = ref(stored())
watch(open, value => {
  try {
    globalThis.localStorage?.setItem(STORAGE, value ? '1' : '0')
  } catch {
    // Storage unavailable: the choice lasts until the page is reloaded.
  }
})
const toggled = (event: Event) => { open.value = (event.target as HTMLDetailsElement).open }
</script>

<template>
  <section id="plan-panel" class="plan-panel">
    <div class="panel-heading"><h2>{{ t('plan.next_title') }}</h2><span class="tag">{{ t('device.battery') }}</span></div>
    <template v-if="track">
      <div class="plan-track-wrap">
        <div class="plan-track" role="group" :aria-label="t('timeline.aria')">
          <button
            v-for="segment in track.segments"
            :key="segment.id"
            type="button"
            class="mode-segment"
            :class="{ future: segment.future }"
            :style="segment.style"
            :aria-label="segment.info"
            :aria-pressed="selected === segment.id"
            @click="selected = segment.id"
          >
            <span v-if="segment.label">{{ segment.label }}</span>
          </button>
        </div>
        <span class="plan-now" :style="{ left: track.now }" aria-hidden="true" />
      </div>
      <div class="plan-axis" aria-hidden="true"><span v-for="tick in track.axis" :key="tick.left" :style="{ left: tick.left }">{{ tick.label }}</span></div>
      <div class="mode-legend"><span v-for="[label, color] in track.legend" :key="label"><i :style="{ '--mode': `var(--${color})` }" />{{ label }}</span></div>
    </template>
    <p v-else class="footnote">{{ t('plan.no_valid') }}</p>
    <p class="mode-detail" aria-live="polite">{{ detail }}</p>
    <details class="next-details" :open="open" @toggle="toggled">
      <summary class="list-title"><span>{{ t('plan.what_next') }}</span><span v-if="events.length" class="tag">{{ events.length }}</span></summary>
      <div class="list">
        <div v-for="event in events" :key="event.key" class="row">
          <span><b>{{ event.text }}</b><template v-if="event.detail"><br><small>{{ event.detail }}</small></template></span>
          <span class="tag">{{ event.time }}</span>
        </div>
        <p v-if="!events.length" class="footnote">{{ t('status.no_next_mode') }}</p>
      </div>
    </details>
    <a v-if="car" class="plan-link" href="#car">{{ t('plan.car_link') }}</a>
  </section>
</template>
