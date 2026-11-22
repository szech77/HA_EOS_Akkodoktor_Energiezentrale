/** Texts of the car pages from backend values; no calculations beyond presentation. */
import type { Host } from '@/types/host'
import { isNumber, type Format } from '@/utils/format'
import type { StateLabels } from '@/utils/modes'
import type { ChargeCost, ChargeGoal, ChargePlan, ChargeSegment, ChargeState, SegmentKind, VehicleData, VehicleLive } from '@/types/car'

/** Colour token per segment kind (CSS variables of the panel). */
export const SEGMENT_COLORS: Readonly<Record<SegmentKind, string>> = { pv: 'solar', grid: 'grid', pause: 'edge', ready: 'car' }

/** Plan states that replace the normal plan tag with a notice: tone and severity label. */
const ALERTS: Partial<Record<ChargeState, readonly [string, string]>> = {
  suspended: ['crit', 'error'],
  overridden: ['warn', 'override'],
  read_only: ['info', 'info'],
  disconnected: ['off', 'info'],
}

export const WEEKDAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'] as const

export interface CostBox {
  readonly label: string
  readonly value: string
  readonly detail: string
  readonly win: boolean
}

export interface ChargeAlert {
  readonly tone: string
  readonly severity: string
  readonly title: string
  readonly detail: string
  readonly diagnose: boolean
}

export function createLabels(host: Host, format: Format, states: StateLabels) {
  const { t, decimal } = host
  const soc = (value: number | null | undefined) => (isNumber(value) ? decimal(value, 0) : '—')

  const phases = (value: number | null | undefined) => (value === 1 || value === 3 ? t(`car.phases_${value}`) : '')
  const chargePower = (segment: ChargeSegment) =>
    [`${decimal(segment.power_w / 1000, 1)} ${t('unit.kw')}`, phases(segment.phases)].filter(Boolean).join(' ')
  const duration = (seconds: number) => {
    const minutes = Math.round(seconds / 60)
    const hours = Math.floor(minutes / 60)
    return hours ? t('car.duration', { h: hours, m: minutes % 60 }) : t('car.duration_min', { m: minutes })
  }

  /** Range for a SoC with the km-per-% factor the backend learned; empty without a factor. */
  const range = (value: number | null | undefined, factor: number | null) =>
    isNumber(factor) && isNumber(value) && value >= 0 && value <= 100 ? t('car.range', { range: decimal(value * factor, 0) }) : ''

  const currentRange = (live: VehicleLive) => {
    if (!isNumber(live.car_range)) return ''
    return t(live.car_range_source === 'estimate' ? 'car.range' : 'car.range_measured', { range: decimal(live.car_range, 0) })
  }

  const weekdays = (days: readonly number[]) => {
    const sorted = [...new Set(days)].sort((a, b) => a - b)
    if (sorted.length === 7) return t('car.goal_daily')
    const label = (index: number) => t(`weekday.${WEEKDAYS[index] ?? 'mon'}`)
    const runs: [number, number][] = []
    for (const value of sorted) {
      const run = runs.at(-1)
      if (run && value === run[1] + 1) run[1] = value
      else runs.push([value, value])
    }
    return runs
      .map(([first, last]) => (last - first >= 2 ? `${label(first)}–${label(last)}` : first === last ? label(first) : `${label(first)}, ${label(last)}`))
      .join(', ')
  }

  const cost = (plan: ChargePlan, label: string, value: ChargeCost | null | undefined, approximate: boolean, win: boolean): CostBox => ({
    label,
    value: value ? (approximate ? '≈ ' : '') + format.euro(value.eur) : '—',
    detail: value
      ? [
          isNumber(value.price_ct) ? t('car.compare_avg', { price: format.price(value.price_ct) }) : '',
          value.reached_at ? t(approximate ? 'car.compare_at_estimated' : 'car.compare_at', { soc: soc(plan.target_soc), time: format.whenDated(value.reached_at) }) : '',
        ].filter(Boolean).join(' · ')
      : t('car.compare_none'),
    win,
  })

  return {
    range,
    /** SoC with its expected range: "70 % · ≈ 294 km". */
    socWithRange(value: number | null | undefined, factor: number | null): string {
      if (!isNumber(value)) return ''
      const text = range(value, factor)
      return `${decimal(value, 0)} %` + (text ? ` · ${text}` : '')
    },
    /** The reported range, or the estimate from the SoC (≈). */
    currentRange,
    vehicleActive: (vehicle: VehicleData) => vehicle.live.car_connected !== false,
    vehicleStatus: (vehicle: VehicleData) => t(vehicle.live.car_available === false ? 'vehicle.unavailable' : 'vehicle.disconnected'),

    goalTitle(plan: ChargePlan): string {
      return plan.departure
        ? t('car.goal_until', { when: format.whenDated(plan.departure), soc: soc(plan.target_soc) })
        : t('car.goal_open', { soc: soc(plan.target_soc) })
    },
    summary(plan: ChargePlan): string {
      if (plan.state === 'disconnected') return t('car.summary_disconnected')
      if (plan.state === 'reached') return t('car.summary_reached')
      if (!plan.segments?.length) return t('car.summary_no_plan')
      const parts: string[] = []
      if (plan.pv_kwh >= 0.05) parts.push(t('car.summary_pv', { kwh: format.kwh(plan.pv_kwh), time: format.whenDated(plan.pv_until) }))
      if (plan.grid_kwh >= 0.05)
        parts.push(t('car.summary_grid', { kwh: format.kwh(plan.grid_kwh), time: format.whenDated(plan.grid_from), price: format.price(plan.grid_price_ct) }))
      const text = [
        isNumber(plan.remaining_kwh) ? t('car.remaining', { kwh: format.kwh(plan.remaining_kwh) }) : '',
        parts.length ? t('car.summary_plan', { parts: parts.join(t('car.summary_and')) }) : t('car.summary_none'),
      ]
      const late = plan.departure && (!plan.reached_at || Date.parse(plan.reached_at) > Date.parse(plan.departure))
      if (late) text.push(t('car.summary_late'))
      return text.filter(Boolean).join(' ')
    },
    goalTags(live: VehicleLive): string[] {
      const charging = isNumber(live.car) && live.car >= 100
      const range = currentRange(live)
      return [
        charging ? [format.power(live.car), phases(live.phases)].filter(Boolean).join(' · ') : '',
        states.mode(live.car_mode),
        live.soc_source ? t('car.soc_source', { source: states.state('source', live.soc_source) }) : '',
        range ? t('car.range_now', { range }) : '',
      ].filter(Boolean)
    },
    ring(value: number | null | undefined, target: number | null | undefined) {
      return {
        label: t('car.ring', { soc: format.percentText(value), target: format.percentText(target) }),
        value: isNumber(value) ? `${decimal(value, 0)} %` : '—',
        target: isNumber(target) ? t('car.ring_target', { soc: decimal(target, 0) }) : '',
      }
    },

    planTitle: (plan: ChargePlan) => (plan.departure ? t('car.plan_title', { when: format.whenDated(plan.departure) }) : t('car.plan_title_open')),
    planTag(plan: ChargePlan): string {
      if (ALERTS[plan.state]) return t(`car.state_${plan.state}`)
      return plan.generated_at ? t('car.plan_from', { time: format.whenDated(plan.generated_at) }) : ''
    },
    alert(plan: ChargePlan): ChargeAlert | null {
      const alert = ALERTS[plan.state]
      if (!alert) return null
      const immediate = plan.immediate_cost?.reached_at
      return {
        tone: alert[0],
        severity: t(`car.sev_${alert[1]}`),
        title: t(`car.alert_${plan.state}_title`),
        detail: plan.state === 'overridden' && immediate
          ? t('car.alert_overridden_at', { soc: soc(plan.target_soc), time: format.whenDated(immediate) })
          : t(`car.alert_${plan.state}`),
        diagnose: plan.state === 'suspended',
      }
    },
    targetAt(plan: ChargePlan): string {
      if (plan.reached_at) return t('car.plot_target_at', { soc: soc(plan.target_soc), time: format.whenDated(plan.reached_at) })
      return isNumber(plan.target_soc) ? t('car.ring_target', { soc: decimal(plan.target_soc, 0) }) : ''
    },
    kind: (kind: SegmentKind) => t(`car.kind_${kind}`),
    short: (kind: SegmentKind) => t(`car.short_${kind}`),
    /** Detail of a tapped plan segment. */
    segment(segment: ChargeSegment): string {
      const parts = [`${format.clock(segment.start)}–${format.clock(segment.end)}`, t(`car.kind_${segment.kind}`)]
      if (segment.kwh >= 0.05) {
        parts.push(chargePower(segment))
        parts.push(t('car.seg_energy', { kwh: format.kwh(segment.kwh), from: soc(segment.soc_start), to: soc(segment.soc_end) }))
        parts.push(segment.kind === 'pv' && isNumber(segment.value_ct) ? t('car.seg_valued', { price: format.price(segment.value_ct) }) : format.price(segment.price_ct))
      } else if (segment.kind === 'pause' && isNumber(segment.price_ct)) parts.push(t('car.row_pause_price', { price: format.price(segment.price_ct) }))
      return parts.filter(Boolean).join(' · ')
    },
    /** Row of the plan list: what happens, with energy and cost, and when. */
    row(segment: ChargeSegment, plan: ChargePlan): { title: string; detail: string; stamp: string } {
      const charge = () => t('car.row_charge', { kwh: format.kwh(segment.kwh), soc: soc(segment.soc_end) })
      const euro = isNumber(segment.cost_eur) ? format.euro(segment.cost_eur) : ''
      let title: string, detail: string[], stamp = format.whenDated(segment.start)
      if (segment.kind === 'pv') {
        title = t('car.row_pv')
        stamp = t('car.row_until', { time: format.whenDated(segment.end) })
        detail = [charge(), euro]
      } else if (segment.kind === 'grid') {
        title = t(segment.phases ? 'car.row_grid_phases' : 'car.row_grid', { power: `${decimal(segment.power_w / 1000, 1)} ${t('unit.kw')}`, phases: phases(segment.phases) })
        detail = [charge(), format.price(segment.price_ct), euro]
      } else if (segment.kind === 'ready') {
        title = t('car.row_ready', { soc: soc(plan.target_soc) })
        detail = [plan.buffer_s && plan.departure ? t('car.row_buffer', { duration: duration(plan.buffer_s), when: format.whenDated(plan.departure) }) : '']
      } else {
        title = t('car.row_pause')
        detail = [isNumber(segment.price_ct) ? t('car.row_pause_price', { price: format.price(segment.price_ct) }) : '']
      }
      return { title, detail: detail.filter(Boolean).join(' · '), stamp }
    },
    /** Plan cost against charging immediately; null when the backend has neither. */
    compare(plan: ChargePlan): { boxes: [CostBox, CostBox]; note: string } | null {
      const planned = plan.plan_cost, now = plan.immediate_cost, fast = plan.state === 'overridden'
      if (!planned && !now) return null
      const cheaper = planned && now ? planned.eur <= now.eur : Boolean(planned)
      return {
        boxes: [
          cost(plan, t('car.compare_plan'), planned, false, !fast && cheaper),
          cost(plan, t(fast ? 'car.compare_now_active' : 'car.compare_now'), now, true, fast),
        ],
        note: isNumber(plan.pv_price_ct) ? t('car.compare_note', { price: format.price(plan.pv_price_ct) }) : t('car.compare_note_free'),
      }
    },

    weekdays,
    goalSchedule(goal: Pick<ChargeGoal, 'schedule' | 'weekdays' | 'departure_time' | 'next_departure' | 'departure_local'>): string {
      const text = goal.schedule === 'weekly'
        ? `${weekdays(goal.weekdays ?? [])} ${goal.departure_time ?? ''}`.trim()
        : goal.next_departure ? format.whenDated(goal.next_departure) : (goal.departure_local ?? '').replace('T', ' ')
      return text || t('plans.no_next')
    },
    goalNext(goal: Pick<ChargeGoal, 'next_departure'>, changed: boolean): string {
      if (changed || goal.next_departure === undefined) return t('car.goal_unsaved')
      return goal.next_departure ? t('plans.next', { date: format.whenDated(goal.next_departure) }) : t('plans.no_next')
    },
  }
}

export type CarLabels = ReturnType<typeof createLabels>
