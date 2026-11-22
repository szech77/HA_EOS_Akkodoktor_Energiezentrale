/**
 * Devices of a battery group (Fronius site, Victron GX, mixed plugins) in the settings: role,
 * availability, the measurements each device declares and its firmware diagnostics.
 */
import type { Host } from '@/types/host'
import { isNumber, type Format } from '@/utils/format'

export interface GroupDevice {
  readonly name: string
  readonly battery?: boolean
  readonly available?: boolean
  readonly plugin?: { readonly name: string } | null
  readonly soc?: number | null
  readonly solar?: number | null
  readonly ac?: number | null
  readonly measurements?: Readonly<Record<string, number | null>>
  readonly read_diagnostics?: {
    readonly firmware?: {
      readonly version?: string | null
      readonly source: string
      readonly register_status: string
      readonly raw_words?: readonly number[] | null
    } | null
  } | null
}

export interface BatteryGroup {
  readonly inverter_count?: number
  readonly battery_count?: number
  readonly capacity_wh?: number | null
  readonly approximate?: boolean
  readonly devices?: readonly GroupDevice[]
}

/** One entry of the definition list; a hint without term has no `term`. */
export interface GroupEntry {
  readonly term?: string
  readonly text: string
  readonly device?: {
    readonly values: readonly { readonly label: string; readonly value: string }[]
    /** "Venus OS: <version> (source) · register: status [raw words]" in three parts. */
    readonly firmware: { readonly label: string; readonly version: string; readonly detail: string } | null
  }
}

const LABELS: Readonly<Record<string, string>> = { solar: 'measurement.solar', inverter_ac: 'measurement.inverter_ac', house_total: 'measurement.house_total', grid: 'measurement.grid' }

export function groupEntries(host: Pick<Host, 't' | 'decimal'>, format: Pick<Format, 'power' | 'percentText'>, group: BatteryGroup | null | undefined): GroupEntry[] {
  if (!group) return []
  const { t, decimal } = host
  const capacity = isNumber(group.capacity_wh) ? ` · ${t('plugin.site_capacity', { capacity: `${decimal(group.capacity_wh / 1000, 2)} ${t('unit.kwh')}` })}` : ''
  const entries: GroupEntry[] = [{ term: t('plugin.fronius_site'), text: t('plugin.site_summary', { inverters: group.inverter_count ?? 0, batteries: group.battery_count ?? 0 }) + capacity }]
  for (const device of group.devices ?? []) {
    const measurements = device.measurements ?? { solar: device.solar ?? null, inverter_ac: device.ac ?? null }
    const values = Object.entries(measurements).map(([key, value]) => ({
      label: LABELS[key] ? t(LABELS[key]) : key,
      value: `${isNumber(value) && value < 0 ? '− ' : ''}${format.power(value)}`,
    }))
    if (device.battery) values.push({ label: t('measurement.battery_soc'), value: format.percentText(device.soc) })
    const firmware = device.read_diagnostics?.firmware
    const raw = Array.isArray(firmware?.raw_words) ? ` [${firmware.raw_words.map(word => `0x${word.toString(16).toUpperCase().padStart(4, '0')}`).join(' ')}]` : ''
    entries.push({
      term: device.name === 'primary' ? t('plugin.primary_inverter') : device.name,
      text: `${device.plugin ? `${device.plugin.name} · ` : ''}${t(device.battery ? 'plugin.site_storage' : 'plugin.site_pv')} · ${t(device.available ? 'plugin.site_available' : 'plugin.site_unavailable')}`,
      device: {
        values,
        firmware: firmware
          ? {
              label: t('plugin.firmware'),
              version: firmware.version ?? t('plugin.firmware_unknown'),
              detail: `(${t(`plugin.firmware_source_${firmware.source}`)}) · ${t('plugin.firmware_register')}: ${t(`plugin.firmware_register_${firmware.register_status}`)}${raw}`,
            }
          : null,
      },
    })
  }
  if (group.approximate) entries.push({ term: t('plugin.pool_approximation'), text: t('plugin.pool_limitations') })
  if (group.battery_count === 0) entries.push({ text: t('plugin.no_storage') })
  return entries
}
