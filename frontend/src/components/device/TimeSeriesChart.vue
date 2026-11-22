<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useDeviceStore } from '@/stores/device'
import { chartModel, DAY, sampleAt, type ChartSpec } from '@/utils/chartSeries'

/**
 * 24 h of measurements and 24 h of forecast around "now". Values under the pointer, on touch and
 * with the arrow keys; Escape or leaving the chart hides them.
 */
const props = defineProps<{ spec: ChartSpec }>()
const { host, format, now } = useDeviceStore()
const { t } = host

const model = computed(() => chartModel(props.spec, now.value))
const axisX = ['−24', '−12', null, '+12', '+24'].map(value => (value ? `${value} ${t('chart.hour')}` : t('chart.now')))
const axisY = computed(() => (model.value ? [model.value.max, (model.value.max + model.value.min) / 2, model.value.min].map(value => host.decimal(value)) : []))

/** Position of the probe across the chart, 0 (−24 h) to 1 (+24 h); null when hidden. */
const ratio = ref<number | null>(null)
const plot = ref<HTMLElement | null>(null)
const tooltip = ref<HTMLElement | null>(null)
const tooltipLeft = ref('0px')

const probe = computed(() => {
  const current = model.value
  if (!current || ratio.value === null) return null
  const stamp = now.value + (ratio.value - 0.5) * 2 * DAY
  return {
    time: format.dateTime(stamp),
    hint: t(stamp > now.value ? 'chart.forecast_values' : 'chart.measured_values'),
    rows: current.series.map(item => {
      const sample = sampleAt(item, stamp, now.value)
      return {
        key: item.key,
        label: item.label,
        color: `var(--${item.color})`,
        value: sample ? `${host.decimal(sample.point.value / item.divisor, 2)} ${props.spec.unit}` : '—',
        at: sample ? format.dateTime(sample.point.stamp) : '',
      }
    }),
  }
})

// Keep the tooltip inside the plot next to the crosshair.
watch(probe, async () => {
  await nextTick()
  if (!plot.value || !tooltip.value || ratio.value === null) return
  const width = plot.value.clientWidth
  tooltipLeft.value = `${Math.max(4, Math.min(width - tooltip.value.offsetWidth - 4, ratio.value * width + 12))}px`
})

const show = (value: number) => { ratio.value = Math.max(0, Math.min(1, value)) }
const hide = () => { ratio.value = null }
function pointer(event: PointerEvent) {
  const box = (event.currentTarget as Element).getBoundingClientRect()
  if (box.width > 0) show((event.clientX - box.left) / box.width)
}
function key(event: KeyboardEvent) {
  if (event.key === 'Escape') return hide()
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
  event.preventDefault()
  // One step is 5 minutes of the 48 h window.
  const current = ratio.value ?? 0.5
  show(event.key === 'Home' ? 0 : event.key === 'End' ? 1 : current + (event.key === 'ArrowRight' ? 1 : -1) / 576)
}
</script>

<template>
  <section>
    <h2>{{ spec.title }} · {{ spec.unit }}</h2>
    <template v-if="model">
      <div class="series-legend">
        <span v-for="item in model.series" :key="item.key"><i :style="{ '--series': `var(--${item.color})` }" />{{ item.label }}</span>
      </div>
      <div class="chart" :data-chart="spec.id">
        <div class="axis-y" aria-hidden="true"><span v-for="(value, index) in axisY" :key="index">{{ value }}</span></div>
        <div ref="plot" class="interactive-plot">
          <svg
            viewBox="0 0 100 100"
            preserveAspectRatio="none"
            tabindex="0"
            role="img"
            :aria-label="t('chart.interactive_aria', { title: spec.title })"
            @pointermove="pointer"
            @pointerdown="pointer"
            @pointerleave="hide"
            @pointercancel="hide"
            @focus="show(0.5)"
            @blur="hide"
            @keydown="key"
          >
            <path class="guide" d="M0 1 H100 M0 50 H100 M0 99 H100" />
            <line class="now" x1="50" x2="50" y1="0" y2="100" />
            <path v-for="(path, index) in model.paths" :key="index" class="curve" :class="{ forecast: path.forecast }" :style="{ '--series': `var(--${path.color})` }" :d="path.d" />
          </svg>
          <div v-show="probe" class="chart-crosshair" :style="{ left: `${(ratio ?? 0) * 100}%` }" />
          <div v-show="probe" ref="tooltip" class="chart-tooltip" role="status" :style="{ left: tooltipLeft }">
            <template v-if="probe">
              <b>{{ probe.time }}</b><small>{{ probe.hint }}</small>
              <div v-for="row in probe.rows" :key="row.key" class="tooltip-series">
                <i :style="{ '--series': row.color }" /><span>{{ row.label }}<small v-if="row.at">{{ row.at }}</small></span><strong>{{ row.value }}</strong>
              </div>
            </template>
          </div>
        </div>
        <div class="axis-x"><span v-for="label in axisX" :key="label">{{ label }}</span></div>
      </div>
    </template>
    <p v-else class="footnote">{{ t('chart.no_data') }}</p>
  </section>
  <p v-if="spec.note" class="footnote">{{ spec.note }}</p>
</template>
