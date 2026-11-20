import { computed, inject, ref, watch, type ComputedRef, type InjectionKey } from 'vue'
import type { Host } from '@/host/types'
import type { ChargeGoal, GoalSchedule, VehicleData } from './types'

/** Editable copy of a goal; `open` only controls the editor and is never sent. */
export interface GoalDraft {
  id: string
  active: boolean
  schedule: GoalSchedule
  target_soc: number | ''
  departure_local: string
  departure_time: string
  weekdays: number[]
  holidays: boolean
  open: boolean
}

/** The backend accepts at most this many goals per vehicle. */
export const MAX_GOALS = 32

const draftOf = (goal: ChargeGoal, open = false): GoalDraft => ({
  id: goal.id,
  active: goal.active,
  schedule: goal.schedule,
  target_soc: goal.target_soc,
  departure_local: goal.departure_local ?? '',
  departure_time: goal.departure_time ?? '07:30',
  weekdays: [...(goal.weekdays ?? [])],
  holidays: Boolean(goal.holidays),
  open,
})

/** Values the backend validates and saves (without UI state). */
export const goalValues = (draft: GoalDraft) => ({
  id: draft.id,
  active: draft.active,
  schedule: draft.schedule,
  target_soc: Number(draft.target_soc),
  departure_local: draft.departure_local,
  departure_time: draft.departure_time,
  holidays: draft.holidays,
  weekdays: [...draft.weekdays].sort((a, b) => a - b),
})

const key = (rows: readonly GoalDraft[]) => JSON.stringify(rows.map(goalValues))

/**
 * Charging goals edited together and saved with one button.
 *
 * Without unsaved changes the list follows the backend (e.g. after a save or a change in the
 * settings); with changes a refresh keeps the user's edits. Another vehicle starts fresh.
 */
export function useGoalDraft(host: Host, vehicle: ComputedRef<VehicleData | null>) {
  const rows = ref<GoalDraft[]>([])
  const status = ref('')
  let counter = 0
  const saved = computed(() => (vehicle.value?.charge_plan_view ?? []).map(goal => draftOf(goal)))
  const dirty = computed(() => key(rows.value) !== key(saved.value))
  const identity = computed(() => vehicle.value?.id ?? '')

  function reset() {
    const open = new Set(rows.value.filter(row => row.open).map(row => row.id))
    rows.value = saved.value.map(row => ({ ...row, open: open.has(row.id) }))
  }
  // The page mounts a new editor per vehicle; start with that vehicle's saved goals.
  rows.value = saved.value
  // Unsaved edits win over a refresh; an unedited list takes the new backend state.
  watch(saved, (_, previous) => {
    if (previous && key(rows.value) === key(previous)) reset()
  })

  return {
    rows,
    status,
    dirty,
    full: computed(() => rows.value.length >= MAX_GOALS),
    /** Saved backend state of a goal, for the summary (next departure, selection). */
    savedGoal: (id: string) => vehicle.value?.charge_plan_view?.find(goal => goal.id === id),
    changed(row: GoalDraft): boolean {
      const original = saved.value.find(item => item.id === row.id)
      return !original || key([row]) !== key([original])
    },
    add() {
      if (rows.value.length >= MAX_GOALS) return
      rows.value.push({
        id: `plan_${host.now()}_${++counter}`,
        active: true,
        schedule: 'weekly',
        target_soc: 80,
        departure_local: '',
        departure_time: '07:30',
        weekdays: [0, 1, 2, 3, 4],
        holidays: false,
        open: true,
      })
    },
    remove(id: string) {
      rows.value = rows.value.filter(row => row.id !== id)
    },
    async save() {
      const values: Record<string, unknown> = { charge_plans: rows.value.map(goalValues) }
      if (identity.value) values.vehicle_id = identity.value
      try {
        await host.request('settings', values)
        // After saving the backend state is authoritative again (normalised values, next departures).
        rows.value = rows.value.map(row => ({ ...row, open: false }))
        await host.refresh()
        reset()
        status.value = host.t('settings.saved')
      } catch (error) {
        status.value = error instanceof Error ? error.message : String(error)
      }
    },
  }
}

export type GoalDraftStore = ReturnType<typeof useGoalDraft>

/** The goal list of the editor; goal items edit their entry in this store. */
export const GOAL_DRAFT: InjectionKey<GoalDraftStore> = Symbol('eos-goal-draft')

export function useGoalDraftStore(): GoalDraftStore {
  const store = inject(GOAL_DRAFT)
  if (!store) throw new Error('Goal draft is not provided')
  return store
}
