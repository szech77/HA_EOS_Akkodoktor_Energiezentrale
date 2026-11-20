import type { PanelSnapshot, PvEffect, Translate } from '@/host/types'
import { isNumber, type Format } from '@/shared/format'
import type { ForecastDay, ForecastEntry, ForecastHour } from './types'

/** Wording of the PV & weather view; values come from the backend, this only phrases them. */
export function createLabels(t: Translate, format: Format, decimal: (value: number, digits?: number) => string) {
  const condition = (value: string | null | undefined) => (value ? t('weather.' + value) : t('pv.no_weather'))

  function lead(snapshot: PanelSnapshot): string {
    const totals = snapshot.pv_forecast_totals ?? []
    return [
      isNumber(snapshot.live?.solar) ? t('pv.lead_now', { power: format.kw(snapshot.live.solar) }) : '',
      isNumber(snapshot.pv_today_kwh) ? t('pv.lead_today', { kwh: format.kwh(snapshot.pv_today_kwh) }) : '',
      isNumber(totals[0]?.kwh) ? t('pv.lead_rest', { kwh: format.kwh(totals[0].kwh) }) : '',
      isNumber(totals[1]?.kwh) ? t('pv.lead_tomorrow', { kwh: format.kwh(totals[1].kwh) }) : '',
    ].filter(Boolean).join(' · ')
  }

  function currentMeta(snapshot: PanelSnapshot, hour: ForecastHour | undefined): string[] {
    const pv = snapshot.pv_now ?? {}
    return [
      isNumber(hour?.cloud_coverage) ? t('pv.clouds', { percent: decimal(hour.cloud_coverage, 0) }) : '',
      isNumber(hour?.precipitation_probability) ? t('pv.rain_chance', { percent: decimal(hour.precipitation_probability, 0) }) : '',
      isNumber(pv.power_w)
        ? t('pv.now_power', { power: format.kw(pv.power_w) }) + (isNumber(pv.ratio) ? ' · ' + t('pv.now_ratio', { percent: decimal(pv.ratio * 100, 0) }) : '')
        : '',
    ].filter(Boolean)
  }

  function hourLabel(item: ForecastHour, index: number, entries: readonly ForecastEntry[]): string {
    if (item.now) return t('pv.now')
    const previous = entries.slice(0, index).reverse().find(entry => entry.kind === 'hour')
    const label = format.clock(item.start)
    return previous && format.dayKey(Date.parse(previous.start)) !== format.dayKey(Date.parse(item.start))
      ? format.date(Date.parse(item.start), { weekday: 'short' }) + ' ' + label
      : label
  }

  function hourText(item: ForecastHour): string {
    return [
      format.when(item.start),
      condition(item.condition) + (isNumber(item.temperature) ? ', ' + format.temperature(item.temperature) : ''),
      isNumber(item.cloud_coverage) ? t('pv.clouds', { percent: decimal(item.cloud_coverage, 0) }) : '',
      isNumber(item.precipitation) && item.precipitation > 0 ? t('pv.rain', { mm: decimal(item.precipitation, 1) }) : '',
      isNumber(item.precipitation_probability) ? t('pv.rain_chance', { percent: decimal(item.precipitation_probability, 0) }) : '',
      t('pv.hour_pv', { kwh: format.kwh(item.pv_kwh) }) + (item.now ? ' · ' + t('pv.rest_of_hour') : ''),
    ].filter(Boolean).join(' · ')
  }

  function nightText(item: { condition?: string | null; low?: number | null }): string {
    return [item.condition ? condition(item.condition) : '', isNumber(item.low) ? t('pv.night_low', { temperature: format.temperature(item.low) }) : '']
      .filter(Boolean).join(' · ')
  }

  function day(item: ForecastDay) {
    const stamp = Date.parse(item.date + 'T12:00:00Z')
    return {
      name: item.today ? t('pv.today') : format.date(stamp, { weekday: 'short', day: 'numeric', month: 'numeric' }),
      weather: [
        item.condition ? condition(item.condition) : '',
        isNumber(item.high) ? `${format.temperature(item.high)} / ${format.temperature(item.low)}` : '',
        isNumber(item.precipitation) && item.precipitation > 0 ? t('pv.rain', { mm: decimal(item.precipitation, 1) }) : '',
      ].filter(Boolean).join(' · ') || t('pv.no_weather'),
      energy: isNumber(item.pv_kwh) ? '≈ ' + format.kwh(item.pv_kwh) : '—',
      note: item.today && isNumber(item.measured_kwh) ? t('pv.day_measured', { kwh: format.kwh(item.measured_kwh) })
        : !item.complete ? t('pv.day_partial') : '',
    }
  }

  /** Title, detail, tag and (for actionable effects) the internal link of one plan effect. */
  function effect(item: PvEffect, snapshot: PanelSnapshot): { title: string; detail: string; tag: string; href?: string } | null {
    const vehicle = item.vehicle_name ?? snapshot.vehicle_name ?? t('node.car')
    // Vehicle ids come from the backend; they are still encoded as one route segment.
    const plan = item.vehicle_id ? '#car/' + encodeURIComponent(item.vehicle_id) : '#car'
    switch (item.id) {
      case 'tomorrow_low':
      case 'tomorrow_high':
        return { title: t('pv.effect_' + item.id), detail: t('pv.effect_tomorrow', { kwh: format.kwh(item.kwh), today: format.kwh(item.today_kwh) }), tag: t('pv.tag_outlook') }
      case 'battery_full':
        return { title: t('pv.effect_battery_full'), detail: t('pv.effect_battery_full_detail', { soc: format.percent(item.soc), time: format.when(item.start) }), tag: t('pv.tag_battery'), href: '#battery' }
      case 'battery_grid':
        return {
          title: t('pv.effect_battery_grid'),
          detail: t('pv.effect_battery_grid_detail', { start: format.when(item.start), end: format.clock(item.end), kwh: format.kwh(item.kwh), price: format.price(item.price_ct) })
            + (isNumber(item.soc) ? ' ' + t('pv.effect_battery_soc', { soc: decimal(item.soc, 0) }) : ''),
          tag: t('pv.tag_battery'), href: '#battery',
        }
      case 'export':
        return { title: t('pv.effect_export'), detail: t('pv.effect_export_detail', { kwh: format.kwh(item.kwh), time: format.when(item.start) }), tag: t('pv.tag_grid'), href: '#usage/grid' }
      case 'car_grid':
        return { title: t('pv.effect_car_grid', { vehicle }), detail: t('pv.effect_car_grid_detail', { kwh: format.kwh(item.kwh), time: format.when(item.start), price: format.price(item.price_ct) }), tag: t('pv.tag_plan'), href: plan }
      case 'car_pv':
        return { title: t('pv.effect_car_pv', { vehicle }), detail: t('pv.effect_car_pv_detail', { kwh: format.kwh(item.kwh), time: format.when(item.end) }), tag: t('pv.tag_plan'), href: plan }
      default:
        return null
    }
  }

  return { condition, lead, currentMeta, hourLabel, hourText, nightText, day, effect }
}

export type Labels = ReturnType<typeof createLabels>
