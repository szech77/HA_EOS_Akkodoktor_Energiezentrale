<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { isNumber } from '@/utils/format'
import { SEGMENT_COLORS } from '@/utils/carLabels'
import { useCarStore } from '@/stores/car'
import type { ChargePlan, ChargeSegment } from '@/types/car'

/** EOS charging plan until the departure: SoC curve, tappable track, list and cost comparison. */
const props = defineProps<{ plan: ChargePlan }>()
const { host, labels, format, now } = useCarStore()
const HOUR = 3_600_000

// The track starts now and covers at least one hour.
const start = computed(() => now.value)
const end = computed(() => Math.max(start.value + HOUR, Date.parse(props.plan.end)))
const span = computed(() => end.value - start.value)
const segments = computed<readonly ChargeSegment[]>(() => props.plan.segments ?? [])
const selected = ref<number | null>(null)
watch(() => props.plan, () => { selected.value = null })

const alert = computed(() => labels.alert(props.plan))
const tag = computed(() => labels.planTag(props.plan))
const muted = computed(() => props.plan.state === 'overridden' || props.plan.state === 'read_only')

const track = computed(() => segments.value.flatMap((segment, index) => {
  const from = Math.max(start.value, Date.parse(segment.start))
  const to = Math.min(end.value, Date.parse(segment.end))
  const share = (to - from) / span.value
  if (!(share > 0)) return []
  return [{
    index,
    info: labels.segment(segment),
    short: share >= 0.12 ? labels.short(segment.kind) : '',
    style: { '--start': ((from - start.value) / span.value).toFixed(4), '--duration': share.toFixed(4), '--mode': `var(--${SEGMENT_COLORS[segment.kind]})` },
  }]
}))

const ticks = computed(() => {
  const step = span.value > 12 * HOUR ? 4 * HOUR : span.value > 4 * HOUR ? 2 * HOUR : HOUR
  const result: { left: string; label: string }[] = []
  for (let stamp = Math.ceil((start.value + step / 2) / step) * step; stamp < end.value - step / 2; stamp += step) {
    result.push({ left: `${((stamp - start.value) * 100 / span.value).toFixed(2)}%`, label: format.clock(new Date(stamp).toISOString()) })
  }
  return result
})
const legend = computed(() => [...new Set(segments.value.map(segment => segment.kind))].map(kind => ({ kind, color: `var(--${SEGMENT_COLORS[kind]})`, label: labels.kind(kind) })))
// Short pauses and slivers stay in the track; the list names what matters.
const rows = computed(() => segments.value
  .filter(segment => Date.parse(segment.end) - Date.parse(segment.start) >= (segment.kind === 'pause' ? 1_800_000 : 600_000) || segment.kwh >= 0.5)
  .map(segment => ({ key: segment.start, ...labels.row(segment, props.plan) })))
const compare = computed(() => labels.compare(props.plan))
const detail = computed(() => {
  const segment = selected.value === null ? undefined : segments.value[selected.value]
  return segment ? labels.segment(segment) : host.t('car.track_hint')
})

const plot = computed(() => {
  const points = (props.plan.curve ?? []).map(point => ({
    x: Math.max(0, Math.min(100, (Date.parse(point.time) - start.value) * 100 / span.value)),
    y: 100 - Math.max(0, Math.min(100, point.soc)),
  }))
  const first = points[0]
  const last = points.at(-1)
  if (!first || !last) return null
  points.push({ x: 100, y: last.y })
  const line = points.map(point => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(' ')
  const target = isNumber(props.plan.target_soc) ? 100 - props.plan.target_soc : null
  return {
    line,
    target,
    startTop: `calc(${first.y.toFixed(1)}% - 20px)`,
    targetTop: target === null ? '' : `calc(${Math.max(0, target).toFixed(1)}% - 20px)`,
    startLabel: `${host.decimal(props.plan.soc ?? 0, 0)} %`,
    targetLabel: labels.targetAt(props.plan),
  }
})
</script>

<template>
  <section id="car-plan" class="plan-panel" :class="{ overridden: muted }">
    <div class="panel-heading">
      <h2>{{ labels.planTitle(plan) }}</h2>
      <span v-if="tag" class="tag">{{ tag }}</span>
    </div>
    <div v-if="alert" class="notice-card" :class="`tone-${alert.tone}`" :role="alert.tone === 'crit' ? 'alert' : 'status'">
      <span class="sev">{{ alert.severity }}</span>
      <div><b>{{ alert.title }}</b><small>{{ alert.detail }}</small></div>
      <a v-if="alert.diagnose" href="#notices">{{ host.t('car.alert_diagnose') }}</a>
      <span v-else />
    </div>
    <div v-if="plot" class="socplot" aria-hidden="true">
      <svg viewBox="0 0 100 100" preserveAspectRatio="none">
        <polygon class="soc-area" :points="`${plot.line} 100,100 0,100`" />
        <line v-if="plot.target !== null" class="soc-target" x1="0" :y1="plot.target" x2="100" :y2="plot.target" />
        <polyline class="soc-line" :points="plot.line" />
      </svg>
      <span class="soclbl" :style="{ left: '0', top: plot.startTop }">{{ plot.startLabel }}</span>
      <span v-if="plot.target !== null" class="soclbl" :style="{ right: '0', top: plot.targetTop }">{{ plot.targetLabel }}</span>
    </div>
    <template v-if="segments.length">
      <div class="plan-track-wrap">
        <div class="plan-track charge-track" role="group" :aria-label="host.t('car.track_aria')">
          <button
            v-for="item in track"
            :key="item.index"
            type="button"
            class="mode-segment"
            :style="item.style"
            :aria-label="item.info"
            :aria-pressed="selected === item.index"
            @click="selected = item.index"
          >
            <span v-if="item.short">{{ item.short }}</span>
          </button>
        </div>
      </div>
      <div class="plan-axis" aria-hidden="true">
        <span style="left: 0">{{ host.t('chart.now') }}</span>
        <span v-for="tick in ticks" :key="tick.left" :style="{ left: tick.left }">{{ tick.label }}</span>
        <span style="left: 100%">{{ format.whenDated(end) }}</span>
      </div>
      <div class="mode-legend">
        <span v-for="item in legend" :key="item.kind"><i :style="{ '--mode': item.color }" />{{ item.label }}</span>
      </div>
      <p class="mode-detail" aria-live="polite">{{ detail }}</p>
      <div class="list">
        <div v-for="row in rows" :key="row.key" class="row">
          <span><b>{{ row.title }}</b><template v-if="row.detail"><br><small>{{ row.detail }}</small></template></span>
          <span class="tag">{{ row.stamp }}</span>
        </div>
      </div>
      <template v-if="compare">
        <div class="cp-compare">
          <div v-for="box in compare.boxes" :key="box.label" :class="{ win: box.win }">
            <small>{{ box.label }}</small><strong>{{ box.value }}</strong><small>{{ box.detail }}</small>
          </div>
        </div>
        <p class="footnote">{{ compare.note }}</p>
      </template>
    </template>
    <p v-else class="footnote">{{ host.t(plan.state === 'disconnected' ? 'car.summary_disconnected' : 'car.no_plan') }}</p>
  </section>
</template>
