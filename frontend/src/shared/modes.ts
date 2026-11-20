import type { Host } from '@/host/types'

/** EOS operating modes: text key and the colour token of the panel (same table as app.js). */
export const MODES: Readonly<Record<string, readonly [string, string]>> = {
  IDLE: ['mode.idle', 'grid'],
  NON_EXPORT: ['mode.pv', 'battery'],
  SELF_CONSUMPTION: ['mode.own', 'house'],
  FORCED_CHARGE: ['mode.grid', 'car'],
  GRID_SUPPORT_IMPORT: ['mode.grid', 'car'],
  FORCED_DISCHARGE: ['mode.discharge', 'heat'],
  GRID_SUPPORT_EXPORT: ['mode.discharge', 'heat'],
  PEAK_SHAVING: ['mode.peak', 'solar'],
  CHARGING: ['mode.charging', 'car'],
  DISCONNECTED: ['mode.disconnected', 'edge'],
}

/** Labels for backend states; an unknown value is shown as sent instead of a missing text. */
export function createStateLabels(host: Host) {
  return {
    mode(mode: string | null | undefined): string {
      const entry = mode ? MODES[mode] : undefined
      return entry ? host.t(entry[0]) : (mode ?? '—')
    },
    state(prefix: string, value: string | null | undefined): string {
      return value ? (host.lookup(`${prefix}.${value}`) ?? value) : ''
    },
  }
}

export type StateLabels = ReturnType<typeof createStateLabels>
