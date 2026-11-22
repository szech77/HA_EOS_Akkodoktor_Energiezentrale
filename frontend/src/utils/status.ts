/** Status band and notice texts. The backend decides state, severity and ids; this only presents them. */
import type { Host } from '@/types/host'
import type { ControlArea, ControlKey, Notice, ResolvedNotice, Severity, StatusSnapshot } from '@/types/status'
import type { Format } from '@/utils/format'
import type { StateLabels } from '@/utils/modes'

export type Tone = 'ok' | 'info' | 'warn' | 'off' | 'crit'
export type Icon = 'ok' | 'wait' | 'pause' | 'off'
export type ControlAction = 'take' | 'release'

/**
 * Tone and icon per backend control_status; unknown states look like read-only. A short EOS
 * outage or computation with the last valid plan is normal operation and looks like active control.
 */
const BAND: Readonly<Record<string, readonly [Tone, Icon]>> = {
  active: ['ok', 'ok'], waiting: ['info', 'wait'], cached_eos: ['ok', 'ok'], syncing_vehicle: ['info', 'wait'],
  planning_vehicle: ['info', 'wait'], backup: ['info', 'pause'], power_supply_waiting: ['warn', 'pause'], read_only: ['off', 'off'],
}
const ORDER: Readonly<Record<Severity, number>> = { error: 0, warning: 1, info: 2 }

export const toneOf = (severity: Severity | undefined): Tone => (severity === 'error' ? 'crit' : severity === 'info' ? 'info' : 'warn')

/** Errors first, then warnings, then information; equal severities keep the backend order. */
export const sortNotices = (list: readonly Notice[]): Notice[] =>
  [...list].sort((a, b) => (ORDER[a.severity ?? 'warning'] ?? 1) - (ORDER[b.severity ?? 'warning'] ?? 1))

/** Page a notice belongs to; null when no single page helps. */
export function noticeLink(notice: Pick<Notice, 'code' | 'scope'>): string | null {
  const code = notice.code ?? ''
  if (notice.scope?.startsWith('vehicle/') || ['goal', 'vehicle_limits', 'wallbox', 'wallbox_stop', 'wallbox_read'].includes(code)) return '#car'
  if (code === 'battery_read' || code === 'battery_limits') return '#battery'
  if (code === 'eos' || code === 'eos_cached') return '#settings'
  return null
}

export function bandState(snapshot: StatusSnapshot) {
  const state = snapshot.control_status && BAND[snapshot.control_status] ? snapshot.control_status : 'read_only'
  const releasing = !snapshot.armed && snapshot.release_pending === true
  const [tone, icon] = BAND[state] ?? BAND.read_only!
  return {
    state,
    releasing,
    tone: releasing ? 'warn' : tone,
    icon: releasing ? 'wait' : icon,
    action: (snapshot.armed || releasing ? 'release' : 'take') as ControlAction,
  }
}

/** Control areas from the backend; older snapshots without them fall back to the configured consumers. */
export function controlAreas(snapshot: StatusSnapshot, car: boolean) {
  const areas = snapshot.control
  const all: ControlKey[] = [...(car ? ['vehicle' as const] : []), 'battery']
  if (!areas) return { available: all, held: all, enabled: null }
  const list = (filter: (area: ControlArea) => boolean) =>
    (['vehicle', 'battery'] as const).filter(key => {
      const area = areas[key]
      return area !== undefined && filter(area)
    })
  return {
    available: list(area => area.available),
    held: list(area => area.enabled || area.release_pending),
    enabled: list(area => area.enabled),
  }
}

export function createStatusTexts(host: Host, format: Format, states: StateLabels) {
  const { t } = host
  const noticeText = (notice: Pick<Notice, 'message' | 'measurements' | 'vehicle_name'>) => {
    const values = (notice.measurements ?? []).map(key => t(`measurement.${key}`)).join(', ')
    return (notice.vehicle_name ? `${notice.vehicle_name}: ` : '') + t(notice.message, { values })
  }
  return {
    noticeText,
    /** Headline, text and confirmation of the status band. */
    band(snapshot: StatusSnapshot, car: boolean, confirming: ControlAction | null) {
      const info = bandState(snapshot)
      const cached = info.state === 'cached_eos'
      const shown = cached ? 'active' : info.state
      const areas = controlAreas(snapshot, car)
      const only = areas.enabled?.length === 1 ? areas.enabled[0] : null
      let text = t(info.releasing ? 'status_band.release_pending' : `status_band.${shown}${shown === 'active' && only ? `_${only}` : ''}`)
      const next = snapshot.next_mode?.battery
      if (shown === 'active' && !info.releasing && only !== 'vehicle' && next?.time) {
        text += ` ${t('status_band.next_change', { time: format.whenDated(next.time), mode: states.mode(next.mode) })}`
      }
      // EOS computing or briefly unreachable: an informational note, not a headline.
      if (cached) text += ` ${t('status_band.cached_eos')}`
      const run = snapshot.eos_run
      if (run?.state === 'calculating' || run?.state === 'updating') text += ` ${t(`eos.run_${run.state}`, { seconds: run.elapsed_s ?? 0 })}.`
      const take = areas.available.length > 1 ? 'control.take_devices' : `control.take_${areas.available[0] ?? 'battery'}`
      return {
        ...info,
        title: t(`control.${shown}`),
        text,
        long: t(`control.${info.action}`),
        short: t(`status_band.${info.action}_short`),
        confirm: confirming && {
          title: t(`control.${confirming}_title`),
          items: (confirming === 'release'
            ? [...areas.held.map(key => (key === 'vehicle' ? 'control.release_wallbox' : 'control.release_battery')), 'control.release_persist']
            : [take, 'control.take_start', 'control.take_persist']).map(key => t(key)),
          label: t(`control.${confirming}_confirm`),
          danger: confirming === 'release',
        },
      }
    },
    /** Severity, text, metadata and link of a notice card. */
    card(notice: Notice, compact: boolean) {
      const tone = toneOf(notice.severity)
      const meta = [
        notice.id ? t('notice_card.id', { id: notice.id }) : '',
        notice.since ? t('notice_card.since', { time: format.whenDated(notice.since) }) : '',
        notice.browser ? t('notice_card.browser') : '',
      ].filter(Boolean).join(' · ')
      const link = compact ? '#notices' : noticeLink(notice)
      return {
        tone,
        severity: t(`notice_card.${notice.severity ?? 'warning'}`),
        text: noticeText(notice),
        meta: compact ? '' : meta,
        link,
        linkText: link ? t(compact ? 'notice_card.all' : 'notice_card.open') : '',
      }
    },
    /** A notice resolved in the last 24 h: what it was, when it ended and how long it lasted. */
    resolved(item: ResolvedNotice) {
      const key = item.code.startsWith('sources_') ? 'notice_card.sources_resolved' : `notice.${item.code}`
      const minutes = item.since && item.at ? Math.max(1, Math.round((Date.parse(item.at) - Date.parse(item.since)) / 60000)) : null
      return {
        text: host.lookup(key) !== undefined ? t(key, { values: '' }) : t('notice.unknown'),
        detail: [t('notice_card.resolved_at', { time: format.whenDated(item.at) }), minutes ? t('notice_card.duration', { minutes }) : ''].filter(Boolean).join(' · '),
        tag: item.id ?? item.code,
      }
    },
  }
}

export type StatusTexts = ReturnType<typeof createStatusTexts>
