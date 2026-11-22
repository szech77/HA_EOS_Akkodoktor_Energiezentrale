/** EOS battery plan of the overview (−3 h … +12 h) and the list of what happens next. */
import type { Host } from '@/types/host'
import type { ModeInterval } from '@/types/device'
import type { OverviewSnapshot, PlanEvent } from '@/types/overview'
import { vehicleName } from '@/utils/devicePage'
import { isNumber, type Format } from '@/utils/format'
import { MODES, type StateLabels } from '@/utils/modes'

const HOUR = 3_600_000
export const PLAN_WINDOW = { before: 3 * HOUR, after: 12 * HOUR }

export interface TrackSegment {
  readonly id: string
  readonly info: string
  readonly label: string
  readonly color: string
  readonly future: boolean
  readonly style: Readonly<Record<string, string>>
}

export function createPlanOverview(host: Host, format: Format, states: StateLabels) {
  const { t } = host
  const clock = (stamp: number) => format.clock(new Date(stamp).toISOString())

  function eventText(event: PlanEvent, snapshot: OverviewSnapshot): string {
    const vehicle = event.vehicle_name ?? (snapshot.vehicle_name || t('node.car', { vehicle: vehicleName(snapshot) }))
    const soc = isNumber(event.soc) ? host.decimal(event.soc, 0) : '—'
    if (event.kind === 'battery_full') return t('plan_event.battery_full', { soc })
    if (event.kind === 'car_target') return t('plan_event.car_target', { vehicle, soc })
    if (event.device === 'battery') {
      // The backend derives what the battery does from the forecast; the EOS mode name alone can mislead at night.
      if (event.effect) return t(`plan_event.effect_${event.effect}`)
      const key = `plan_event.battery_${event.mode ?? ''}`
      return host.lookup(key) !== undefined ? t(key) : t('plan_event.battery', { mode: states.mode(event.mode) })
    }
    return t('plan_event.car', { vehicle, mode: states.mode(event.mode) })
  }

  return {
    /** Segments placed by time, so many short EOS changes can never push the plan before "now". */
    track(snapshot: OverviewSnapshot, now: number) {
      const start = now - PLAN_WINDOW.before
      const end = now + PLAN_WINDOW.after
      const span = end - start
      const rows = (snapshot.mode_timeline?.battery ?? [])
        .map((row: ModeInterval) => ({ ...row, start: Math.max(start, row.start), end: Math.min(end, row.end) }))
        .filter(row => row.end > row.start)
      if (!rows.some(row => row.kind === 'plan' && row.mode)) return null
      const at = (stamp: number) => `${((stamp - start) * 100 / span).toFixed(2)}%`
      const segments: TrackSegment[] = rows.map(row => {
        const label = row.mode ? states.mode(row.mode) : t('timeline.no_data')
        const color = row.mode && MODES[row.mode] ? MODES[row.mode]![1] : 'edge'
        return {
          id: `${row.kind}:${row.start}`,
          info: t('timeline.interval', { kind: t(`timeline.${row.kind}`), start: format.whenDated(row.start), end: format.whenDated(row.end), mode: label }),
          // Only a segment of at least 1.5 h has room for its name.
          label: row.end - row.start >= 5_400_000 ? label : '',
          color,
          future: row.kind === 'plan',
          style: { '--start': String((row.start - start) / span), '--duration': String((row.end - row.start) / span), '--mode': `var(--${color})` },
        }
      })
      const legend = [...new Map(rows.map(row => [row.mode ? states.mode(row.mode) : t('timeline.no_data'), row.mode && MODES[row.mode] ? MODES[row.mode]![1] : 'edge'])).entries()]
      return {
        segments,
        legend,
        now: at(now),
        axis: [
          { left: '0', label: clock(start) },
          { left: at(now), label: t('chart.now') },
          { left: at(now + 6 * HOUR), label: clock(now + 6 * HOUR) },
          { left: '100%', label: clock(end) },
        ],
      }
    },
    /** Upcoming changes as everyday sentences with time, EOS mode and price. */
    events(snapshot: OverviewSnapshot) {
      return (snapshot.plan_events ?? []).map((event, index) => ({
        key: `${event.time}:${index}`,
        text: eventText(event, snapshot),
        detail: [event.effect ? t('plan_event.eos_mode', { mode: states.mode(event.mode) }) : '', isNumber(event.price_ct) ? t('plan_event.price', { price: format.price(event.price_ct) }) : ''].filter(Boolean).join(' · '),
        time: format.whenDated(event.time),
      }))
    },
  }
}

export type PlanOverview = ReturnType<typeof createPlanOverview>
