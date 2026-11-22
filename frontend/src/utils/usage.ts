/**
 * Wording of the consumption and cost report. Reports include explicit estimates, never
 * control- or display-held power; every figure comes from the backend.
 */
import type { Host } from '@/types/host'
import type { Amount, Balance, Fact, Period, PvFlowKey, PvGapKey, Report, ReportView, Source, SourceAmount } from '@/types/usage'
import type { Card } from '@/utils/devicePage'
import { createFormat, isNumber } from '@/utils/format'

export const SOURCE_COLORS: Readonly<Record<Source, string>> = { pv: '#f2c94c', battery: '#55c7cb', grid: '#5794f2', unknown: '#8995a5' }
export const SOURCES = Object.keys(SOURCE_COLORS) as Source[]

/** PV destinations above zero, and below zero the consumption PV did not cover (battery by charging origin). */
export const PV_FLOWS: readonly (readonly [PvFlowKey, string])[] = [
  ['house', 'var(--house)'], ['car', 'var(--car)'], ['heat', 'var(--heat)'], ['storage', 'var(--battery)'], ['export', 'var(--solar)'],
]
export const PV_GAPS: readonly (readonly [PvGapKey, string])[] = [
  ['battery_pv', 'color-mix(in srgb,var(--battery) 60%,transparent)'],
  ['battery_grid', 'color-mix(in srgb,var(--battery) 35%,var(--grid) 35%)'],
  ['battery_unknown', 'color-mix(in srgb,var(--battery) 30%,transparent)'],
  ['grid', 'color-mix(in srgb,var(--grid) 70%,transparent)'],
  ['unknown', 'var(--dim)'],
]

export const isCarKey = (key: string) => key === 'car' || key.startsWith('car/')

export interface Vehicle {
  readonly id?: string
  readonly name?: string
}

/** Report pages in the order of the sub navigation; a single vehicle stays on the car report. */
export function usageKeys(features: Readonly<Record<string, boolean>> | undefined, vehicles: readonly Vehicle[]): string[] {
  const enabled = (key: string) => features?.[key] !== false
  const cars = enabled('car') ? ['car', ...(vehicles.length > 1 ? vehicles.map(item => `car/${item.id ?? ''}`) : [])] : []
  return ['pv', 'house', ...cars, ...(enabled('heat') ? ['heat'] : []), 'grid', 'total']
}

export interface SourceBarModel {
  readonly empty: boolean
  readonly label: string
  readonly parts: readonly { readonly share: number; readonly color: string; readonly title: string }[]
}

export interface PriceRow {
  readonly label: string
  readonly rate: string
  readonly value: string
  readonly sum?: boolean
}

export interface PriceTable {
  readonly heading: string | null
  readonly rows: readonly PriceRow[]
  readonly note: string | null
}

export interface MixItem {
  readonly label: string
  readonly color: string
  readonly value: string
  readonly detail: string
}

export interface Mix {
  readonly title: string
  readonly total: string
  readonly bar: SourceBarModel | null
  readonly items: readonly MixItem[]
}

export interface FactRow {
  readonly title: string
  readonly text: string
  readonly tag: string
  readonly href?: string
}

export interface BalanceTile {
  readonly href: string
  readonly name: string
  readonly value: string
  readonly context: string
  readonly bar: SourceBarModel | null
  readonly feed: boolean
}

export function createUsageText(host: Host, zone: () => string | undefined, vehicles: () => readonly Vehicle[]) {
  const { t, decimal } = host
  const format = createFormat(host, zone)
  const price = format.price
  const percent = format.percentText

  const money = (value: number) => {
    const tiny = value !== 0 && Math.abs(value) < 0.0001
    const currency = new Intl.NumberFormat(host.locale(), {
      style: 'currency', currency: 'EUR', minimumFractionDigits: 2, maximumFractionDigits: value !== 0 && Math.abs(value) < 0.01 ? 4 : 2,
    })
    return tiny ? (value > 0 ? '< ' : '> ') + currency.format(Math.sign(value) * 0.0001) : currency.format(value)
  }
  const energy = (value: number) => `${decimal(value, 2)} kWh`
  const energyOr = (value: number | null | undefined) => (isNumber(value) ? energy(value) : '—')
  const moneyOr = (value: number | null | undefined, approximate = false) => (isNumber(value) ? (approximate ? '≈ ' : '') + money(value) : '—')
  const plusMoney = (value: number | null | undefined, approximate = false) => (isNumber(value) ? (approximate ? '≈ +' : '+') + money(value) : '—')
  const estimated = (amount: SourceAmount | null | undefined) => amount?.estimated === true
  /** Unknown costs are never shown as free; a partly priced amount says so. */
  const costValue = (amount: SourceAmount | null | undefined) =>
    amount?.cost_available && isNumber(amount.cost_eur)
      ? `${estimated(amount) ? '≈ ' : ''}${money(amount.cost_eur)}${amount.cost_partial ? ` (${t('billing.known_portion')})` : ''}`
      : '—'
  const averageCost = (amount: SourceAmount | null | undefined) => {
    const rate = amount?.average_price_ct
    return isNumber(rate) ? `${estimated(amount) ? '≈ ' : ''}${price(rate)}` : '—'
  }
  const estimatedAverageNote = (amount: SourceAmount | null | undefined) => (estimated(amount) && isNumber(amount?.average_price_ct) ? t('billing.estimated_average_note') : '')
  const averageCostLabel = (amount: SourceAmount | null | undefined) => {
    const value = averageCost(amount)
    return t('billing.average_unit_price', { price: value === '—' ? `— ${t('unit.price')}` : value })
  }
  const costWithPrice = (amount: SourceAmount | null | undefined) => `${costValue(amount)} · ${averageCostLabel(amount)}`
  const feedInMoney = (balance: Balance | null | undefined) =>
    balance && !(balance.export_kwh > 0.0001 && !isNumber(balance.feed_in_price_ct)) ? plusMoney(balance.export_eur, balance.cost_partial) : '—'

  const name = (key: string): string => {
    if (key === 'total') return t('billing.total_consumption')
    if (key === 'grid') return t('usage.grid_title')
    if (key === 'pv') return t('usage.pv_title')
    if (key.startsWith('car/')) return vehicles().find(item => item.id === key.slice(4))?.name ?? t('device.car')
    return t(`device.${key}`)
  }
  const navName = (key: string) => (key === 'total' ? t('billing.total') : key === 'grid' ? t('usage.grid_nav') : name(key))

  function sourceBar(amount: Amount | null | undefined): SourceBarModel {
    if (!amount || amount.kwh <= 0) return { empty: true, label: '', parts: [] }
    const parts = Object.entries(amount.sources).map(([source, item]) => {
      const share = item?.share_percent ?? 0
      return { share, color: SOURCE_COLORS[source as Source], title: `${t(`billing.${source}`)}: ${decimal(share)} %` }
    })
    return { empty: false, label: Object.entries(amount.sources).map(([source, item]) => `${t(`billing.${source}`)} ${decimal(item?.share_percent ?? 0)} %`).join(', '), parts }
  }

  function binLabel(time: string, unit: Fact['unit']) {
    const locale = host.locale()
    if (unit === 'hour') return new Intl.DateTimeFormat(locale, { timeZone: zone(), weekday: 'short', hour: '2-digit', minute: '2-digit' }).format(new Date(time))
    if (unit === 'day') return new Intl.DateTimeFormat(locale, { timeZone: 'UTC', weekday: 'short', day: 'numeric', month: 'short' }).format(new Date(`${time}T12:00:00Z`))
    return new Intl.DateTimeFormat(locale, { timeZone: 'UTC', month: 'long', year: 'numeric' }).format(new Date(`${time}-15T12:00:00Z`))
  }

  /** Facts are selected by the backend; the browser only words them. */
  function fact(item: Fact): FactRow {
    const time = item.time ? binLabel(item.time, item.unit) : ''
    const kwh = item.kwh ?? 0
    switch (item.id) {
      case 'best': return { title: t(`usage.fact_best_${item.unit}`), text: t('usage.fact_best_text', { time, share: percent(item.percent) }), tag: percent(item.percent) }
      case 'max_pv': return { title: t('usage.fact_max_pv'), text: t('usage.fact_max_pv_text', { time, energy: energy(kwh) }), tag: energy(kwh) }
      case 'pv_per_day': return { title: t('usage.fact_per_day'), text: t('usage.fact_pv_per_day_text', { energy: energy(kwh) }), tag: 'Ø' }
      case 'max_grid': return { title: t('usage.fact_max_grid'), text: t('usage.fact_max_grid_text', { time, energy: energy(kwh) }), tag: energy(kwh) }
      case 'charge_days': return { title: t('usage.fact_charge_days'), text: t('usage.fact_charge_days_text', { count: item.count ?? 0, days: item.days ?? 0 }), tag: t('usage.days', { count: item.count ?? 0 }) }
      case 'per_day': return { title: t('usage.fact_per_day'), text: `${energy(kwh)} · ${item.cost_available && isNumber(item.eur) ? money(item.eur) : '—'}`, tag: 'Ø' }
      case 'savings': {
        const eur = item.eur ?? 0
        return { title: t(eur >= 0 ? 'usage.fact_savings' : 'usage.fact_extra_cost'), text: t('usage.fact_savings_text', { self: price(item.self_price_ct), grid: price(item.grid_price_ct) }), tag: (eur >= 0 ? '+' : '') + money(eur) }
      }
      case 'consumer': {
        const share = isNumber(item.self_percent) ? `${t('usage.self_share', { share: percent(item.self_percent) })} · ` : ''
        return { title: name(item.key ?? ''), text: `${energy(kwh)} · ${share}${item.cost_available && isNumber(item.cost_eur) ? money(item.cost_eur) : '—'}`, tag: t('usage.open'), href: `#usage/${item.key ?? ''}` }
      }
      case 'export': return { title: t('usage.feed_in'), text: `${energy(kwh)} · ${isNumber(item.eur) ? `+${money(item.eur)}` : '—'}`, tag: t('usage.open'), href: '#usage/grid' }
      case 'max_export': return { title: t('usage.fact_max_export'), text: `${time} · ${energy(kwh)}`, tag: isNumber(item.eur) ? `+${money(item.eur)}` : '—' }
      case 'max_import': return { title: t('usage.fact_max_import'), text: `${time} · ${energy(kwh)}`, tag: moneyOr(item.eur) }
      case 'grid_per_day': return { title: t('usage.fact_per_day'), text: t('usage.fact_grid_per_day_text', { feed: energy(item.export_kwh ?? 0), import: energy(item.import_kwh ?? 0) }), tag: 'Ø' }
      default: return { title: t(`usage.fact_${item.id}`), text: t(`usage.fact_${item.id}_text`), tag: '—' }
    }
  }

  /** Lead sentence and the four key figures of a report page. */
  function figures(key: string, report: Report | null, period: Period): { lead: string; kpis: Card[] } {
    const view = report?.views?.[key]
    const balance = report?.balance ?? null
    const amount = entryOf(report, key)?.total
    const days = isNumber(view?.per_day_kwh)
    const perDay = (value: number | null | undefined) => (days && isNumber(value) ? t('usage.per_day', { energy: energy(value) }) : t('billing.observed'))
    const card = (title: string, value: string, context: string): Card => ({ title, value, context })
    const feedContext = `${feedInMoney(balance)} · ${price(balance?.feed_in_price_ct)}`
    if (key === 'pv') {
      // The forecast covers only the rest of the period; EOS plans about two days ahead.
      const forecast = report?.pv_forecast
      const more = forecast && !forecast.complete && forecast.kwh > 0 ? t('usage.pv_forecast_partial') : ''
      const perDayPv = balance && balance.base_days > 1 && period !== 'day' ? balance.pv_kwh / balance.base_days : null
      return {
        lead: balance ? t('usage.lead_pv', { energy: energy(balance.pv_kwh), share: percent(balance.self_consumption_percent) }) : '',
        kpis: [
          card(t('usage.pv_produced'), energyOr(balance?.pv_kwh), perDay(perDayPv)),
          card(t('usage.self_consumption'), percent(balance?.self_consumption_percent), t('usage.self_consumption_note')),
          card(t('usage.feed_in'), energyOr(balance?.export_kwh), feedContext),
          card(t('usage.pv_forecast'), forecast ? energy(forecast.kwh) : '—', [t('usage.pv_forecast_note'), more].filter(Boolean).join(' ')),
        ],
      }
    }
    if (key === 'grid') {
      return {
        lead: balance ? t('usage.lead_grid', { feed: energy(balance.export_kwh), import: energy(balance.grid_import_kwh), share: percent(balance.self_consumption_percent) }) : '',
        kpis: [
          card(t('usage.feed_in'), energyOr(balance?.export_kwh), feedContext),
          card(t('usage.import'), energyOr(balance?.grid_import_kwh), `${moneyOr(balance?.grid_import_cost_eur, balance?.cost_partial)} · ${t('billing.average_unit_price', { price: price(balance?.grid_import_price_ct) })}`),
          card(t('usage.self_consumption'), percent(balance?.self_consumption_percent), t('usage.self_consumption_note')),
          card(t('usage.autarky'), percent(balance?.autarky_percent), t('usage.autarky_note')),
        ],
      }
    }
    const approx = amount?.energy_estimated ? '≈ ' : ''
    const consumed = amount ? approx + energy(amount.kwh) : '—'
    if (key === 'total') {
      return {
        lead: amount && balance ? t('usage.lead_total', { energy: approx + energy(amount.kwh), share: percent(balance.autarky_percent), net: moneyOr(balance.net_eur, balance.cost_partial) }) : '',
        kpis: [
          card(t('billing.consumption'), consumed, perDay(view?.per_day_kwh)),
          card(t('usage.autarky'), percent(balance?.autarky_percent), t('usage.autarky_parts', { energy: energyOr(balance?.own_kwh) })),
          card(t('usage.costs_total'), moneyOr(balance?.total_cost_eur, balance?.cost_partial), t('usage.incl_base')),
          card(t('usage.net'), moneyOr(balance?.net_eur, balance?.cost_partial), t('usage.net_note', { value: feedInMoney(balance) })),
        ],
      }
    }
    const car = isCarKey(key)
    return {
      lead: amount && amount.kwh > 0
        ? t('usage.lead_consumer', { energy: approx + energy(amount.kwh), share: percent(view?.self_percent), cost: costValue(amount) })
        : t(car ? 'usage.lead_no_charging' : 'usage.lead_none'),
      kpis: [
        card(t(car ? 'usage.charged' : 'billing.consumption'), consumed, perDay(view?.per_day_kwh)),
        card(t('usage.self_supply'), percent(view?.self_percent), t('usage.self_parts', { pv: energyOr(view?.pv_kwh), battery: energyOr(view?.battery_own_kwh) })),
        card(t(amount?.cost_partial ? 'billing.known_costs' : 'billing.costs'), costValue(amount), averageCostLabel(amount)),
        card(t('usage.savings'), moneyOr(view?.savings_eur), t('usage.savings_note')),
      ],
    }
  }

  function prices(key: string, report: Report | null): PriceTable {
    const view = report?.views?.[key]
    const balance = report?.balance ?? null
    const row = (label: string, rate: string, value: string, sum = false): PriceRow => ({ label, rate, value, sum })
    const empty: PriceTable = { heading: null, rows: [], note: null }
    if (!balance && (key === 'pv' || key === 'grid')) return empty
    const base = (b: Balance): PriceRow[] => b.base_segments?.length
      ? b.base_segments.map(segment => row(
        `${t('usage.base_price', { days: segment.days })} · ${segment.start} – ${segment.end}`,
        t(segment.period === 'day' ? 'usage.price_per_day' : 'usage.per_month', {
          value: new Intl.NumberFormat(host.locale(), { style: 'currency', currency: 'EUR', minimumFractionDigits: 2, maximumFractionDigits: 6 }).format(segment.amount_eur),
        }), money(segment.cost_eur)))
      : [row(t('usage.base_price', { days: b.base_days }),
        b.base_segments ? '—' : t('usage.per_month', { value: money(b.base_price_eur_month ?? 0) }), money(b.base_eur ?? 0))]
    const feed = (b: Balance) => row(t('usage.feed_in_credit', { energy: energy(b.export_kwh) }), price(b.feed_in_price_ct),
      isNumber(b.feed_in_price_ct) || b.export_kwh <= 0.0001 ? `−${money(b.export_eur ?? 0)}` : '—')
    if (key === 'pv' && balance) return { heading: null, rows: [feed(balance)], note: null }
    if (key === 'grid' && balance) {
      const approx = balance.cost_partial
      return {
        heading: t('usage.grid_price', { price: price(balance.grid_import_price_ct) }),
        rows: [
          row(t('usage.grid_import', { energy: energy(balance.grid_import_kwh) }), price(balance.grid_import_price_ct), moneyOr(balance.grid_import_cost_eur, approx)),
          ...base(balance), feed(balance), row(t('usage.grid_balance'), '', moneyOr(balance.grid_balance_eur, approx), true),
        ],
        note: (balance.storage_grid_kwh ?? 0) > 0.0001 ? t('usage.price_note_grid', { energy: energy(balance.storage_grid_kwh ?? 0) }) : null,
      }
    }
    if (!view) return empty
    const rows: PriceRow[] = [row(t('usage.grid_import', { energy: energy(view.grid_kwh ?? 0) }), price(view.grid_price_ct), moneyOr(view.grid_cost_eur, view.cost_partial))]
    if (key === 'total' && balance) rows.push(...base(balance))
    // Own power is split by origin; grid-charged storage is listed apart instead of as own power.
    const origin = view.self_origin
    if (origin) {
      for (const part of ['pv_direct', 'battery_pv', 'battery_grid', 'battery_unknown'] as const) {
        const item = origin[part]
        if (!item || (part !== 'pv_direct' && !(item.kwh > 0.0001))) continue
        rows.push(row(t(`usage.self_${part}`, { energy: energy(item.kwh) }), price(item.price_ct), moneyOr(item.cost_eur, view.cost_partial)))
      }
    } else rows.push(row(t('usage.self_power', { energy: energy(view.self_kwh ?? 0) }), price(view.self_price_ct), moneyOr(view.self_cost_eur, view.cost_partial)))
    if ((view.unknown_kwh ?? 0) > 0.0001) rows.push(row(t('usage.unknown_origin', { energy: energy(view.unknown_kwh ?? 0) }), '', '—'))
    if (key === 'total' && balance) rows.push(feed(balance), row(t('usage.net'), '', moneyOr(balance.net_eur, balance.cost_partial), true))
    else rows.push(row(t('billing.costs'), '', view.cost_available ? moneyOr(view.cost_eur, view.cost_partial) : '—', true))
    return { heading: averageCostLabel(entryOf(report, key)?.total), rows, note: t('usage.price_note') + (key === 'total' ? '' : ` ${t('usage.base_note')}`) }
  }

  function mix(key: string, report: Report | null): Mix {
    const balance = report?.balance ?? null
    const amount = entryOf(report, key)?.total
    const share = (value: number | null | undefined) => (isNumber(value) ? decimal(value) : '—')
    const item = (label: string, color: string, kwh: number, percentage: number | null | undefined, detail = ''): MixItem =>
      ({ label, color, value: `${energy(kwh)} · ${share(percentage)} %`, detail })
    const bar = (parts: readonly (readonly [number | null | undefined, string])[]): SourceBarModel =>
      ({ empty: false, label: '', parts: parts.map(([value, color]) => ({ share: value ?? 0, color, title: '' })) })
    if (key === 'pv') {
      const flow = balance?.pv_flow
      if (!flow || !balance) return { title: t('usage.mix_pv_title'), total: '—', bar: null, items: [] }
      const total = Object.values(flow).reduce((sum, value) => sum + value, 0)
      const part = (value: number) => (total > 0 ? (value / total) * 100 : null)
      return {
        title: t('usage.mix_pv_title'),
        total: energy(balance.pv_kwh),
        bar: bar(PV_FLOWS.map(([flowKey, color]) => [part(flow[flowKey]), color] as const)),
        items: PV_FLOWS.map(([flowKey, color]) => item(t(`usage.pv_to_${flowKey}`), color, flow[flowKey], part(flow[flowKey]))),
      }
    }
    if (key === 'grid') {
      const use = balance?.pv_use
      if (!use || !balance) return { title: t('usage.mix_pv_title'), total: '—', bar: null, items: [] }
      const parts = [['direct', '#5ab0e8'], ['storage', SOURCE_COLORS.battery], ['export', SOURCE_COLORS.pv]] as const
      return {
        title: t('usage.mix_pv_title'),
        total: energy(balance.pv_kwh),
        bar: bar(parts.map(([part, color]) => [use[part].share_percent, color] as const)),
        items: parts.map(([part, color]) => item(t(`usage.pv_${part}`), color, use[part].kwh, use[part].share_percent)),
      }
    }
    if (!amount) return { title: t('usage.mix_title'), total: '—', bar: null, items: [] }
    return {
      title: t('usage.mix_title'),
      total: energy(amount.kwh),
      bar: sourceBar(amount),
      items: Object.entries(amount.sources)
        .filter(([source, value]) => source !== 'unknown' || (value?.kwh ?? 0) > 0.0001)
        .map(([source, value]) => item(t(`usage.from_${source}`), SOURCE_COLORS[source as Source], value?.kwh ?? 0, value?.share_percent, costWithPrice(value))),
    }
  }

  /** Data quality and method of the report, below the details. */
  function quality(key: string, report: Report | null): string {
    const amount = entryOf(report, key)?.total
    return [
      report?.historical_error ? t('billing.history_error') : '',
      report?.reconstructed ? t('billing.reconstructed') : '',
      t('billing.method'),
      t('billing.partial'),
      estimatedAverageNote(amount),
      report?.started ? `${t('billing.recording_since')} ${format.dateTime(report.started)}.` : '',
    ].filter(Boolean).join(' ')
  }

  /** Today's tiles on the overview: each consumer, the feed-in and the total, each linking to its report. */
  function dayBalance(report: Report | null | undefined): { total: string; tiles: BalanceTile[]; note: string } | null {
    if (!report) return null
    const consumers = report.overview?.consumers ?? {}
    const total = report.overview?.total ?? null
    const balance = report.balance ?? null
    const views = report.views ?? {}
    const share = (key: string) => (isNumber(views[key]?.self_percent) ? `${t('usage.self_share', { share: percent(views[key]?.self_percent) })} · ` : '')
    const amountText = (value: Amount | null | undefined) => (value?.energy_estimated ? '≈ ' : '') + (value ? energy(value.kwh) : '—')
    const tiles: BalanceTile[] = Object.keys(consumers).map(key => {
      const value = consumers[key]
      return { href: `#usage/${key}`, name: name(key), value: amountText(value), context: share(key) + costWithPrice(value), bar: sourceBar(value), feed: false }
    })
    if (balance) {
      tiles.push({
        href: '#usage/grid', name: t('usage.feed_in'), value: energy(balance.export_kwh),
        context: `${feedInMoney(balance)} · ${t('usage.import_short', { energy: energy(balance.grid_import_kwh) })}`, bar: null, feed: true,
      })
    }
    tiles.push({
      href: '#usage/total', name: t('billing.total_consumption'), value: amountText(total),
      context: costWithPrice(total) + (balance ? ` · ${t('usage.net_short', { value: moneyOr(balance.net_eur, balance.cost_partial) })}` : ''), bar: null, feed: false,
    })
    const sum = `${total ? energy(total.kwh) : '—'} · ${costValue(total)}` + (balance ? ` · ${t('usage.feed_short', { value: feedInMoney(balance) })}` : '')
    return { total: sum, tiles, note: [t('billing.partial'), total?.cost_partial ? t('billing.unknown_cost') : '', estimatedAverageNote(total)].filter(Boolean).join(' ') }
  }

  return {
    format, money, energy, energyOr, moneyOr, costValue, costWithPrice, averageCostLabel, feedInMoney, price, percent,
    name, navName, sourceBar, binLabel, fact, figures, prices, mix, quality, dayBalance,
  }
}

export type UsageText = ReturnType<typeof createUsageText>

/** The consumer entry of a report page; PV and grid have none. */
export function entryOf(report: Report | null | undefined, key: string) {
  if (!report) return undefined
  if (key === 'total') return report.total
  if (key === 'grid' || key === 'pv') return undefined
  return report.consumers[key]
}

export type { ReportView }
