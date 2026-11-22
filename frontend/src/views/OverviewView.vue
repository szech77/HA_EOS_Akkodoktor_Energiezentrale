<script setup lang="ts">
import { computed } from 'vue'
import EnergyFlow from '@/components/overview/EnergyFlow.vue'
import PlanPanel from '@/components/overview/PlanPanel.vue'
import KpiCards from '@/components/device/KpiCards.vue'
import { useOverviewStore } from '@/stores/overview'
import { isNumber } from '@/utils/format'
import type { Card } from '@/utils/devicePage'

/** Start page: four key figures, the live energy flow and the EOS plan. */
const { host, snapshot, format } = useOverviewStore()
const { t } = host

const cards = computed<Card[]>(() => {
  const data = snapshot.value
  const live = data.live
  const shown = (key: string): number | null | undefined => {
    const retained = data.flow_display?.[key]?.value
    if (retained !== undefined && retained !== null) return retained
    const value = live[key]
    return isNumber(value) ? value : data.display?.[key]?.value
  }
  const approximate = (key: string) => Boolean(data.flow_display?.[key] || (data.display?.[key] && !isNumber(live[key])))
  const power = (key: string) => (approximate(key) ? '≈ ' : '') + format.power(shown(key))
  const remaining = data.pv_daily_forecast?.[0]?.kwh
  const backup = data.power_supply?.grid_active === false
  const grid = shown('grid')
  const battery = shown('battery')
  return [
    {
      title: t('metric.pv_today'),
      value: isNumber(data.pv_today_kwh) ? `${host.decimal(data.pv_today_kwh)} ${t('unit.kwh')}` : '—',
      context: isNumber(remaining) ? t('metric.remaining', { energy: `${host.decimal(remaining)} ${t('unit.kwh')}` }) : t('metric.available_intervals'),
    },
    { title: t('metric.price_now'), value: format.price(shown('price')), context: t('metric.import') },
    {
      title: t('metric.grid_connection'),
      value: backup ? t('power_supply.backup') : power('grid'),
      context: backup ? t('power_supply.grid_disconnected') : data.power_supply?.state === 'unknown' ? t('power_supply.unknown')
        : isNumber(grid) ? t(grid < 0 ? 'metric.export' : grid > 0 ? 'metric.import' : 'metric.no_grid_flow') : '—',
    },
    {
      title: t('node.battery'),
      value: format.percentText(shown('battery_soc')),
      context: isNumber(battery) && Math.abs(battery) >= 10 ? `${t(battery < 0 ? 'metric.discharging' : 'mode.charging')} · ${power('battery')}` : t('metric.battery_idle'),
    },
  ]
})
</script>

<template>
  <div class="page-top"><div><p class="eyebrow">{{ t('section.overview') }}</p><h1>{{ t('nav.overview') }}</h1></div></div>
  <KpiCards id="overview-kpis" :cards="cards" />
  <div class="overview-grid">
    <EnergyFlow />
    <PlanPanel />
  </div>
</template>
