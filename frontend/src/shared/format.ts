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
  }
}

export type Format = ReturnType<typeof createFormat>
