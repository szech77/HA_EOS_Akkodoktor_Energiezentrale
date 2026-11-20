<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import KpiCards from '@/components/device/KpiCards.vue'
import SourceBar from '@/components/usage/SourceBar.vue'
import UsageChart from '@/components/usage/UsageChart.vue'
import { narrowScreen, useViewport } from '@/composables/useViewport'
import { useUsageStore } from '@/stores/usage'
import type { Period } from '@/types/usage'
import { isCarKey, PV_FLOWS, PV_GAPS, SOURCE_COLORS, SOURCES, entryOf } from '@/utils/usage'
import { profileOf, slotsOf, type BinGroup } from '@/utils/usageCharts'

/**
 * Consumption and cost report of one page (PV, house, car, vehicle, heat pump, grid or total):
 * key figures, chart by period, prices, energy mix and the facts the backend selected.
 */
const props = defineProps<{ reportKey: string; /** Time of the panel snapshot; a newer one may reload the report. */ tick: number }>()
const store = useUsageStore()
const { host, text, charts, period, unit, report, loading, error } = store
const { t } = host
const viewport = useViewport()
const open = !narrowScreen()
const nav = ref<HTMLElement | null>(null)
const bin = ref<string | null>(null)

onMounted(() => void store.load())
watch(() => props.tick, () => void store.load())
watch([() => props.reportKey, period, unit, report], () => (bin.value = null))

const key = computed(() => props.reportKey)
const keys = computed(() => store.keys())
const view = computed(() => report.value?.views?.[key.value])
const balance = computed(() => report.value?.balance ?? null)
const amount = computed(() => entryOf(report.value, key.value)?.total)
const range = computed(() => {
  const data = report.value
  if (!data) return ''
  const options: Record<Period, Intl.DateTimeFormatOptions> = { day: { dateStyle: 'long' }, month: { year: 'numeric', month: 'long' }, year: { year: 'numeric' } }
  return new Intl.DateTimeFormat(host.locale(), { timeZone: 'UTC', ...options[period.value] }).format(new Date(`${data.date}T12:00:00Z`))
})
const current = computed(() => !report.value || report.value.end > store.today())
const device = computed(() => (key.value.startsWith('car/') || ['house', 'heat', 'grid', 'car'].includes(key.value) ? key.value : null))
const eyebrow = computed(() => {
  const kind = key.value === 'grid' ? 'usage.eyebrow_grid' : key.value === 'pv' ? 'usage.eyebrow_pv' : key.value === 'total' ? 'usage.eyebrow_total' : 'usage.eyebrow_consumer'
  return t(kind) + (range.value ? ` · ${range.value}` : '')
})
const figures = computed(() => text.figures(key.value, report.value, period.value))

// Day view: power profile (kW), hourly energy (kWh) or hourly costs (€); month and year: kWh or €.
// PV production has no euro view; its value appears as feed-in credit and in the consumers' costs.
const shownUnit = computed(() => ((unit.value === 'kw' && period.value !== 'day') || (unit.value === 'eur' && key.value === 'pv') ? 'kwh' : unit.value))
const profile = computed(() => (shownUnit.value === 'kw' ? profileOf(report.value, period.value, key.value) : null))
const units = computed(() => [
  { value: 'kw', label: 'kW', hidden: period.value !== 'day' },
  { value: 'kwh', label: 'kWh', hidden: false },
  { value: 'eur', label: '€', hidden: key.value === 'pv' },
])
const unitTag = computed(() => {
  if (profile.value) return t('usage.unit_power')
  const bins = { day: 'hour', month: 'day', year: 'month' }[period.value]
  return t(`${shownUnit.value === 'eur' ? 'usage.unit_eur_' : 'usage.unit_'}${bins}`)
})
const chart = computed(() => {
  const data = report.value
  const slots = slotsOf(data, period.value, host.locale(), store.zone())
  const cost = shownUnit.value === 'eur'
  if (profile.value && data) return charts.power(key.value, profile.value, data, slots, viewport.value)
  if (key.value === 'pv') return charts.pv(balance.value?.bins ?? [], data?.pv_forecast, slots, viewport.value)
  if (key.value === 'grid') return charts.grid(balance.value?.bins ?? [], slots, cost, viewport.value)
  return charts.consumption(entryOf(data, key.value), slots, cost, viewport.value)
})
type LegendItem = { label: string; color: string | null; group?: boolean }
const legend = computed<LegendItem[]>(() => {
  const present = <K extends string>(values: Readonly<Partial<Record<K, number>>> | undefined, names: readonly (readonly [K, string])[]) =>
    names.filter(([name]) => (values?.[name] ?? 0) > 0.005)
  if (key.value === 'pv') {
    const gaps = present(balance.value?.pv_gap, PV_GAPS)
    return [
      { label: t('usage.pv_legend_flows'), color: null, group: true },
      ...present(balance.value?.pv_flow, PV_FLOWS).map(([name, color]) => ({ label: t(`usage.pv_to_${name}`), color })),
      ...(gaps.length ? [{ label: t('usage.pv_legend_gaps'), color: null, group: true }] : []),
      ...gaps.map(([name, color]) => ({ label: t(`usage.pv_gap_${name}`), color })),
      { label: t('usage.pv_forecast'), color: null },
    ]
  }
  if (key.value === 'grid') return [{ label: `↑ ${t('usage.import')}`, color: SOURCE_COLORS.grid }, { label: `↓ ${t('usage.feed_in')}`, color: SOURCE_COLORS.pv }]
  return SOURCES.filter(source => source !== 'unknown' || (amount.value?.sources.unknown?.kwh ?? 0) > 0.0001).map(source => ({ label: t(`billing.${source}`), color: SOURCE_COLORS[source] }))
})
// Older days have no minute values left; their kW view shows hourly energy instead.
const binHint = computed(() => bin.value ?? t(period.value === 'day' ? 'usage.bin_hint' : 'usage.bin_drill') + (shownUnit.value === 'kw' && !profile.value && report.value ? ` ${t('usage.profile_hourly')}` : ''))
const priceTag = computed(() => text.price(key.value === 'grid' ? balance.value?.grid_import_price_ct : view.value?.grid_price_ct))
const prices = computed(() => text.prices(key.value, report.value))
const mix = computed(() => text.mix(key.value, report.value))
const facts = computed(() => (view.value?.facts ?? []).map(fact => text.fact(fact)))
const vehicles = computed(() => (key.value === 'car' && store.vehicles().length > 1 ? store.vehicles() : []))

function choose(group: BinGroup) {
  if (period.value !== 'day') store.drill(group.date)
  else bin.value = group.tooltip
}

// On narrow screens the chips scroll sideways; keep the current report visible.
watch(key, () => void nextTick(centerChip), { immediate: true })
function centerChip() {
  const element = nav.value
  const active = element?.querySelector<HTMLElement>('[aria-current]')
  if (element && active?.offsetWidth && element.scrollWidth > element.clientWidth) {
    element.scrollLeft = active.offsetLeft - element.offsetLeft - (element.clientWidth - active.offsetWidth) / 2
  }
}
</script>

<template>
  <section id="usage">
    <div class="d-head">
      <a class="back" :href="isCarKey(key) ? '#car' : '#overview'">{{ t('nav.back') }}</a>
      <nav ref="nav" class="subnav" :aria-label="t('usage.choose')">
        <a v-for="item in keys" :key="item" :href="`#usage/${item}`" :aria-current="item === key ? 'page' : undefined">{{ text.navName(item) }}</a>
      </nav>
    </div>
    <div class="period">
      <div class="segctl" role="group" :aria-label="t('billing.period')">
        <button v-for="item in (['day', 'month', 'year'] as const)" :key="item" type="button" :aria-pressed="period === item" @click="store.selectPeriod(item)">{{ t(`billing.${item}`) }}</button>
      </div>
      <div class="pnav">
        <button type="button" class="pbtn" :aria-label="t('billing.previous')" @click="store.move(-1)">‹</button>
        <b aria-live="polite">{{ range }}</b>
        <button type="button" class="pbtn" :aria-label="t('billing.next')" :disabled="current" @click="store.move(1)">›</button>
        <button type="button" class="btn ghost" :hidden="current" @click="store.move('now')">{{ t('billing.current') }}</button>
      </div>
    </div>
    <div class="usage-head">
      <div><p class="eyebrow">{{ eyebrow }}</p><h1>{{ key === 'total' ? t('usage.total_title') : text.name(key) }}</h1><p class="lead">{{ figures.lead }}</p></div>
      <a v-if="device" class="plan-link" :href="`#${device}`">{{ t('usage.device_link') }}</a>
    </div>
    <p role="status">{{ error ?? (loading ? t('billing.loading') : '') }}</p>
    <KpiCards :cards="figures.kpis" />
    <section class="chart-panel">
      <div class="panel-heading">
        <h2>{{ t('usage.history') }}</h2>
        <div class="chart-tools">
          <div class="segctl small" role="group" :aria-label="t('usage.chart_unit')">
            <button v-for="item in units" :key="item.value" type="button" :hidden="item.hidden" :aria-pressed="shownUnit === item.value" @click="store.selectUnit(item.value)">{{ item.label }}</button>
          </div>
          <span class="tag">{{ unitTag }}</span>
        </div>
      </div>
      <div class="series-legend">
        <template v-for="(item, index) in legend" :key="index">
          <span v-if="item.group" class="legend-group">{{ item.label }}</span>
          <span v-else><i :style="item.color ? { background: item.color } : { border: `1px dashed ${SOURCE_COLORS.pv}` }"></i>{{ item.label }}</span>
        </template>
      </div>
      <div id="usage-charts">
        <UsageChart v-if="chart" :model="chart" :readout="charts.readout" @bin="choose" />
        <p v-else class="empty-state">{{ t('billing.no_data') }}</p>
      </div>
      <p class="footnote" aria-live="polite">{{ binHint }}</p>
    </section>
    <div class="usage-two">
      <details class="plan-panel acc" :open="open">
        <summary><h2>{{ t('usage.prices') }}</h2><span class="tag">{{ priceTag }}</span></summary>
        <div>
          <p v-if="prices.heading" class="ph">{{ prices.heading }}</p>
          <div v-for="(row, index) in prices.rows" :key="index" class="prow" :class="{ sum: row.sum }">
            <span>{{ row.label }}</span><span class="num dim">{{ row.rate }}</span><span class="num">{{ row.value }}</span>
          </div>
          <p v-if="prices.note" class="footnote">{{ prices.note }}</p>
        </div>
      </details>
      <details class="plan-panel acc" :open="open">
        <summary><h2>{{ mix.title }}</h2><span class="tag">{{ mix.total }}</span></summary>
        <div id="usage-table">
          <SourceBar v-if="mix.bar" :bar="mix.bar" />
          <div v-if="mix.items.length" class="list">
            <div v-for="(item, index) in mix.items" :key="index" class="row">
              <span><i class="source-dot" :style="{ background: item.color }"></i>{{ item.label }}<template v-if="item.detail"><br><small>{{ item.detail }}</small></template></span>
              <span class="num">{{ item.value }}</span>
            </div>
          </div>
          <div v-if="vehicles.length" class="billing-links">
            <a v-for="vehicle in vehicles" :key="vehicle.id" :href="`#usage/car/${vehicle.id}`">{{ vehicle.name }} →</a>
          </div>
        </div>
      </details>
    </div>
    <details class="plan-panel acc" :open="open">
      <summary><h2>{{ t('usage.facts') }}</h2></summary>
      <div class="list">
        <template v-for="(fact, index) in facts" :key="index">
          <a v-if="fact.href" class="row rowlink" :href="fact.href"><span><b>{{ fact.title }}</b><br><small>{{ fact.text }}</small></span><span class="tag accent">{{ fact.tag }}</span></a>
          <div v-else class="row"><span><b>{{ fact.title }}</b><br><small>{{ fact.text }}</small></span><span class="tag">{{ fact.tag }}</span></div>
        </template>
        <p v-if="!facts.length" class="footnote">{{ t(loading ? 'billing.loading' : 'billing.no_data') }}</p>
      </div>
    </details>
    <details class="plan-panel">
      <summary>{{ t('billing.quality') }}</summary>
      <p>{{ text.quality(key, report) }}</p>
      <p>{{ t('billing.inventory_note') }}</p>
    </details>
  </section>
</template>
