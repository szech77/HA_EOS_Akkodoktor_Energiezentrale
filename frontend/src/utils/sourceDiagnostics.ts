/**
 * Numeric source diagnostics of the settings: the backend supplies values, ages and the balance
 * rule; the browser shows them as tables and as an aligned plain-text report.
 */
import type { Host } from '@/types/host'
import { isNumber } from '@/utils/format'

export interface DiagnosticSource {
  readonly key: string
  readonly source?: string | null
  readonly source_type?: string | null
  readonly value?: number | null
  readonly unit: string
  readonly age_s?: number | null
  readonly available: boolean
  readonly reason?: string | null
  readonly max_age_s?: number | null
}

export interface DiagnosticsView {
  readonly time?: string | null
  readonly sources?: readonly DiagnosticSource[]
  readonly derived?: Readonly<Record<string, number | null | undefined>>
  readonly balance?: { readonly residual_w?: number | null; readonly tolerance_w?: number | null; readonly balanced?: boolean } | null
  readonly complete?: boolean
  readonly estimates?: readonly { readonly key: string; readonly reason: string }[]
  readonly devices?: readonly { readonly name: string; readonly plugin?: string | null; readonly available?: boolean; readonly read_error?: string | null; readonly values?: Readonly<Record<string, number | null>> }[]
  readonly vehicles?: readonly { readonly name: string; readonly connected?: boolean; readonly car?: number | null; readonly car_soc?: number | null; readonly soc_source?: string | null; readonly car_range?: number | null }[]
}

export interface SourceRow {
  readonly measurement: string
  /** Kind prefix ("Sensor: ") and the source name; sensors are shown as code. */
  readonly kind: string
  readonly source: string
  readonly code: boolean
  readonly value: string
  readonly age: string
  readonly status: string
  readonly warn: boolean
}

export interface DiagnosticsModel {
  readonly time: string
  readonly sources: readonly SourceRow[]
  readonly derived: readonly { readonly label: string; readonly value: string; readonly strong: boolean }[]
  readonly state: { readonly text: string; readonly warn: boolean }
  readonly estimates: readonly { readonly measurement: string; readonly reason: string }[]
  readonly devices: readonly { readonly title: string; readonly status: string; readonly values: readonly { readonly measurement: string; readonly value: string }[] }[]
  readonly vehicles: readonly { readonly name: string; readonly power: string; readonly soc: string }[]
}

export function createDiagnostics(host: Pick<Host, 't' | 'decimal' | 'locale'>, zone: () => string | undefined) {
  const { t, decimal } = host
  const digits = (unit: string) => (unit === 'W' ? 0 : unit === 'ct/kWh' ? 2 : 1)
  /** Table value: a typographic minus before the absolute value. */
  const number = (value: number | null | undefined, unit: string) => (isNumber(value) ? `${value < 0 ? '−' : ''}${decimal(Math.abs(value), digits(unit))} ${unit}` : '—')
  /** Plain text value, as the locale formats it. */
  const plainNumber = (value: number | null | undefined, unit: string) => (isNumber(value) ? `${decimal(value, digits(unit))} ${unit}` : '—')
  const age = (row: DiagnosticSource) => (isNumber(row.age_s) ? `${decimal(row.age_s, 0)} s` : '—')
  const status = (row: DiagnosticSource) => (row.available ? t('diagnostics.ok') : t(`diagnostics.reason.${row.reason ?? 'state_unavailable'}`, { age: row.max_age_s ?? '—' }))
  const kind = (row: DiagnosticSource) => (row.source_type ? `${t(`diagnostics.source_${row.source_type}`)}: ` : '')
  const deviceTitle = (device: NonNullable<DiagnosticsView['devices']>[number]) => device.name + (device.plugin ? ` · ${device.plugin}` : '')
  const deviceStatus = (device: NonNullable<DiagnosticsView['devices']>[number]) =>
    t(device.available ? 'diagnostics.device_ok' : 'diagnostics.device_incomplete') + (device.read_error ? ` · ${t('diagnostics.read_error', { error: device.read_error })}` : '')
  const connection = (item: NonNullable<DiagnosticsView['vehicles']>[number]) => `${item.name} · ${t(item.connected === false ? 'diagnostics.disconnected' : 'diagnostics.connected')}`
  const estimate = (item: { soc_source?: string | null }) => (item.soc_source === 'estimate' ? ` (${t('source.estimate')})` : '')
  const unitOf = (key: string) => (key === 'battery_soc' ? '%' : 'W')

  // Derived values in display order; shared by the table and the text export.
  function derived(view: DiagnosticsView) {
    const values = view.derived ?? {}
    const balance = view.balance
    const rows: [string, number | null | undefined, boolean][] = [
      ['diagnostics.house_total', values['house_total'], false], ['diagnostics.minus_car', values['car'], false],
      ['diagnostics.minus_heat', values['heat'], false], ['diagnostics.house', values['house'], true],
      ['diagnostics.house_total_measured', values['house_total_measured'], false],
      ['diagnostics.residual', balance?.residual_w, true], ['diagnostics.tolerance', balance?.tolerance_w, false],
    ]
    const state = view.complete === false ? 'incomplete' : !balance ? 'measured_missing' : balance.balanced ? 'balanced' : 'unbalanced'
    const estimates = (view.estimates ?? []).map(item => [item.key === 'house' ? 'diagnostics.house_label' : `measurement.${item.key}`, `diagnostics.estimate.${item.reason}`] as const)
    return { rows, state, estimates }
  }
  const stamp = (time: string | null | undefined, options: Intl.DateTimeFormatOptions) =>
    time ? new Intl.DateTimeFormat(host.locale(), { timeZone: zone(), ...options }).format(new Date(time)) : '—'

  function model(view: DiagnosticsView | null | undefined): DiagnosticsModel | null {
    if (!view) return null
    const { rows, state, estimates } = derived(view)
    return {
      time: t('diagnostics.time', { time: stamp(view.time, { timeStyle: 'medium' }) }),
      sources: (view.sources ?? []).map(row => ({
        measurement: t(`measurement.${row.key}`),
        kind: row.source ? kind(row) : '',
        source: row.source ?? '—',
        code: Boolean(row.source) && row.source_type === 'sensor',
        value: number(row.value, row.unit),
        age: age(row),
        status: status(row),
        warn: !row.available,
      })),
      derived: rows.map(([key, value, strong]) => ({ label: t(key), value: number(value, 'W'), strong })),
      state: { text: t(`diagnostics.${state}`), warn: state !== 'balanced' },
      estimates: estimates.map(([key, reason]) => ({ measurement: t(key), reason: t(reason) })),
      devices: (view.devices ?? []).map(device => ({
        title: deviceTitle(device),
        status: deviceStatus(device),
        values: Object.entries(device.values ?? {}).map(([key, value]) => ({ measurement: t(`measurement.${key}`), value: number(value, unitOf(key)) })),
      })),
      vehicles: (view.vehicles ?? []).map(item => ({
        name: connection(item),
        power: number(item.car, 'W'),
        soc: number(item.car_soc, '%') + estimate(item) + (isNumber(item.car_range) ? ` · ${number(item.car_range, 'km')}` : ''),
      })),
    }
  }

  /** Plain-text copy of the same backend diagnostics for analysis outside the panel. */
  function text(view: DiagnosticsView | null | undefined): string {
    const plain = (value: unknown) => String(value ?? '').replace(/[\r\n\t]+/g, ' ').trim()
    const columns = (rows: readonly (readonly string[])[], right: readonly number[] = [1]) => {
      const widths = (rows[0] ?? []).map((_, index) => Math.max(...rows.map(row => plain(row[index]).length)))
      return rows.map(row => row.map((cell, index) => (right.includes(index) ? plain(cell).padStart(widths[index] ?? 0) : plain(cell).padEnd(widths[index] ?? 0))).join('  ').trimEnd())
    }
    const lines = [`EOS Energiezentrale · ${t('diagnostics.title')}`, `${t('diagnostics.time', { time: stamp(view?.time, { dateStyle: 'short', timeStyle: 'medium' }) })} (${view?.time ?? '—'})`, '']
    if (!view) return `${[...lines, t('diagnostics.empty')].join('\n')}\n`
    const source = (row: DiagnosticSource) => (row.source ? kind(row) + row.source : '—')
    lines.push(...columns([
      [t('diagnostics.measurement'), t('diagnostics.source'), t('diagnostics.value'), t('diagnostics.age'), t('diagnostics.status')],
      ...(view.sources ?? []).map(row => [t(`measurement.${row.key}`), source(row), plainNumber(row.value, row.unit), age(row), status(row)]),
    ], [2, 3]))
    const { rows, state, estimates } = derived(view)
    lines.push('', t('diagnostics.derived'), ...columns(rows.map(([key, value]) => [t(key), plainNumber(value, 'W')])), t(`diagnostics.${state}`))
    if (estimates.length) lines.push('', t('diagnostics.estimates'), ...columns(estimates.map(([key, reason]) => [t(key), t(reason)]), []))
    for (const device of view.devices ?? []) {
      lines.push('', `${t('diagnostics.devices')}: ${plain(deviceTitle(device))} · ${deviceStatus(device)}`,
        ...columns(Object.entries(device.values ?? {}).map(([key, value]) => [t(`measurement.${key}`), plainNumber(value, unitOf(key))])))
    }
    if ((view.vehicles ?? []).length) {
      lines.push('', t('diagnostics.vehicles'), ...columns((view.vehicles ?? []).map(item => [plain(connection(item)), plainNumber(item.car, 'W'), plainNumber(item.car_soc, '%') + estimate(item)]), [1, 2]))
    }
    return `${lines.join('\n')}\n`
  }

  /** File name of the text export, by the time of the diagnostics. */
  const fileName = (view: DiagnosticsView | null | undefined, now: string) => `eos-messwerte-${(view?.time ?? now).slice(0, 19).replace(/[:T]/g, '-')}.txt`

  return { model, text, fileName }
}

export type Diagnostics = ReturnType<typeof createDiagnostics>
