import type { Host } from '@/host/types'

const valid = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value)

export const isNumber = valid

/** Presentation helpers bound to the panel locale and the installation time zone. */
export function createFormat(host: Host, zone: () => string | undefined) {
  const { decimal, t } = host
  const options = (extra: Intl.DateTimeFormatOptions): Intl.DateTimeFormatOptions => {
    const timeZone = zone()
    return timeZone ? { timeZone, ...extra } : extra
  }
  const date = (stamp: number, extra: Intl.DateTimeFormatOptions) =>
    new Intl.DateTimeFormat(host.locale(), options(extra)).format(stamp)
  const dayKey = (stamp: number) => new Intl.DateTimeFormat('sv-SE', options({})).format(stamp)
  const clock = (stamp: string | null | undefined): string => {
    const value = Date.parse(stamp ?? '')
    return valid(value) ? date(value, { hour: '2-digit', minute: '2-digit' }) : '—'
  }
  return {
    date,
    dayKey,
    clock,
    /** Time of day today, weekday and time on other days. */
    when(stamp: string | null | undefined): string {
      const value = Date.parse(stamp ?? '')
      if (!valid(value)) return '—'
      return dayKey(value) === dayKey(host.now()) ? clock(stamp) : date(value, { weekday: 'short', hour: '2-digit', minute: '2-digit' })
    },
    kwh: (value: number | null | undefined) => (valid(value) ? `${decimal(value, 1)} kWh` : '—'),
    kw: (value: number | null | undefined) => (valid(value) ? `${decimal(value / 1000, 1)} kW` : '—'),
    price: (value: number | null | undefined) => (valid(value) ? `${decimal(value, 1)} ${t('unit.price')}` : '—'),
    // Rounding must not show a negative zero.
    temperature: (value: number | null | undefined) => (valid(value) ? `${decimal(Math.round(value) || 0, 0)}°` : '—'),
    percent: (value: number | null | undefined) => (valid(value) ? decimal(value, 0) : '—'),
    /** Percentage with unit, as the panel shows SoC values: "48 %". */
    percentText: (value: number | null | undefined) => (valid(value) ? `${decimal(value)} %` : '—'),
    /** Power in watts as kW with two decimals; the sign is shown by the context, not the number. */
    power: (value: number | null | undefined) => (valid(value) ? `${decimal(Math.abs(value) / 1000, 2)} ${t('unit.kw')}` : '—'),
    euro: (value: number) => new Intl.NumberFormat(host.locale(), { style: 'currency', currency: 'EUR' }).format(value),
    /** Same day: time; within six days: weekday and time; otherwise date and time. */
    whenDated(stamp: string | number | null | undefined): string {
      const value = typeof stamp === 'number' ? stamp : Date.parse(stamp ?? '')
      if (!valid(value)) return '—'
      if (dayKey(value) === dayKey(host.now())) return date(value, { hour: '2-digit', minute: '2-digit' })
      return Math.abs(value - host.now()) < 6 * 86_400_000
        ? date(value, { weekday: 'short', hour: '2-digit', minute: '2-digit' })
        : date(value, { dateStyle: 'short', timeStyle: 'short' })
    },
  }
}

export type Format = ReturnType<typeof createFormat>
