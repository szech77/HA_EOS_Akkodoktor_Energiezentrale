<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import type { BinGroup, ChartModel, HoverPoint } from '@/utils/usageCharts'

/**
 * One report chart: axis, stacked areas or bars, and a tappable bin per slot. The power chart
 * shows the values under the pointer, for mouse and touch alike.
 */
const props = defineProps<{
  model: ChartModel
  readout: (row: HoverPoint['row'], key: string) => { title: string; lines: [string, string, string][] }
}>()
const emit = defineEmits<{ bin: [group: BinGroup] }>()

const svg = ref<SVGSVGElement | null>(null)
const tipNode = ref<HTMLElement | null>(null)
const pressed = ref<number | null>(null)
const cursor = ref<number | null>(null)
const tip = ref<{ title: string; lines: [string, string, string][]; left: number } | null>(null)
// Remembered so the readout survives the periodic redraw of the page.
let pointer: number | null = null

function hide(leave = false) {
  if (leave) pointer = null
  cursor.value = null
  tip.value = null
}

function show(clientX: number) {
  const hover = props.model.hover
  const element = svg.value
  if (!hover?.points.length || !element) return
  pointer = clientX
  const box = element.getBoundingClientRect()
  const position = box.width ? ((clientX - box.left) / box.width) * props.model.width : 0
  let nearest = hover.points[0] as HoverPoint
  for (const item of hover.points) if (Math.abs(item.x - position) < Math.abs(nearest.x - position)) nearest = item
  // Between data (a gap or after the last sample) nothing is shown.
  if (Math.abs(nearest.x - position) > hover.reach) return hide()
  cursor.value = nearest.x
  const container = element.parentElement?.getBoundingClientRect() ?? box
  const pixel = box.left - container.left + (nearest.x / props.model.width) * box.width
  const width = tipNode.value?.offsetWidth || 160
  const left = Math.max(0, Math.min(container.width - width, pixel + 12 > container.width - width ? pixel - width - 12 : pixel + 12))
  tip.value = { ...props.readout(nearest.row, hover.key), left }
}

watch(() => props.model, () => {
  pressed.value = null
  if (pointer === null || !props.model.hover) return hide()
  const last = pointer
  void nextTick(() => show(last))
})

function choose(group: BinGroup, index: number) {
  pressed.value = index
  emit('bin', group)
}
</script>

<template>
  <svg
    ref="svg"
    class="billing-chart"
    :class="{ 'power-chart': model.hover }"
    :viewBox="`0 0 ${model.width} ${model.height}`"
    role="group"
    :aria-label="model.label"
    @pointermove="model.hover && show($event.clientX)"
    @pointerdown="model.hover && show($event.clientX)"
    @pointerleave="hide(true)"
  >
    <template v-for="(tick, index) in model.axis" :key="`a${index}`">
      <line :x1="model.left" :x2="model.width - model.right" :y1="tick.y" :y2="tick.y" stroke="var(--edge)" :stroke-width="tick.strong ? 2 : undefined" />
      <text :x="model.left - 8" :y="tick.y + 4" text-anchor="end">{{ tick.label }}</text>
    </template>
    <polygon v-for="(area, index) in model.areas" :key="`p${index}`" class="area" :points="area.points" :style="{ fill: area.color }" />
    <polyline v-if="model.forecastLine" class="forecast-line" :points="model.forecastLine" stroke="#f2c94c" />
    <g
      v-for="(group, index) in model.groups"
      :key="`g${index}`"
      tabindex="0"
      role="button"
      :data-billing-bin="group.date"
      :aria-label="group.tooltip"
      :aria-pressed="pressed === null ? undefined : pressed === index"
      @click="choose(group, index)"
      @keydown.enter.space.prevent="choose(group, index)"
    >
      <title v-if="group.title">{{ group.tooltip }}</title>
      <rect
        v-for="(shape, part) in group.shapes"
        :key="part"
        :class="{ 'forecast-bar': shape.forecast }"
        :x="shape.x"
        :y="shape.y"
        :width="shape.width"
        :height="shape.height"
        :style="shape.forecast ? undefined : { fill: shape.color }"
        :stroke="shape.forecast ? shape.color : undefined"
      />
      <rect :x="group.hit.x" :y="group.hit.y" :width="group.hit.width" :height="group.hit.height" fill="transparent" />
    </g>
    <text v-for="(label, index) in model.labels" :key="`l${index}`" :x="label.x" :y="label.y" text-anchor="middle">{{ label.text }}</text>
    <line
      v-if="model.hover"
      class="power-cursor"
      :x1="cursor ?? 0"
      :x2="cursor ?? 0"
      :y1="model.top"
      :y2="model.height - model.bottom"
      :visibility="cursor === null ? 'hidden' : undefined"
    />
  </svg>
  <div v-if="model.hover" ref="tipNode" class="power-tip" role="status" :hidden="!tip" :style="tip ? { left: `${tip.left}px` } : undefined">
    <template v-if="tip">
      <b>{{ tip.title }}</b>
      <span v-for="(line, index) in tip.lines" :key="index"><i :style="{ background: line[2] }"></i>{{ line[0] }}<em>{{ line[1] }}</em></span>
    </template>
  </div>
</template>
