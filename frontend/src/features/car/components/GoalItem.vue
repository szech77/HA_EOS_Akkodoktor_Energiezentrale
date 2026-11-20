<script setup lang="ts">
import { computed } from 'vue'
import { WEEKDAYS } from '../labels'
import { useCar } from '../state'
import { useGoalDraftStore, type GoalDraft } from '../useGoalDraft'
import SocField from './SocField.vue'

/** One goal of the editor store: a summary line with an editor that opens on demand. */
const props = defineProps<{ id: string; factor: number | null }>()
const { host, labels } = useCar()
const store = useGoalDraftStore()
const goal = computed(() => store.rows.value.find(row => row.id === props.id) as GoalDraft)
const saved = computed(() => store.savedGoal(props.id))
const changed = computed(() => store.changed(goal.value))

const soc = computed(() => (goal.value.target_soc === '' ? '—' : host.decimal(goal.value.target_soc, 0)))
const range = computed(() => (goal.value.target_soc === '' ? '' : labels.range(goal.value.target_soc, props.factor)))
const schedule = computed(() => labels.goalSchedule({ ...goal.value, next_departure: changed.value ? undefined : saved.value?.next_departure }))
const next = computed(() => labels.goalNext({ next_departure: saved.value?.next_departure }, changed.value))
const weekdays = WEEKDAYS.map((day, index) => ({ index, label: host.t(`weekday.${day}`) }))

function toggleDay(index: number, on: boolean) {
  const days = new Set(goal.value.weekdays)
  if (on) days.add(index)
  else days.delete(index)
  goal.value.weekdays = [...days].sort((a, b) => a - b)
}
function remove() {
  if (globalThis.confirm(host.t('plans.delete_confirm'))) store.remove(props.id)
}
</script>

<template>
  <fieldset v-if="goal" class="charge-goal" :class="{ selected: saved?.selected && !changed }">
    <legend class="sr-only">{{ host.t('plans.goal') }}</legend>
    <div class="goal-summary">
      <span class="goal-when"><b>{{ soc }} %</b><small v-if="range">{{ range }}</small></span>
      <span class="goal-text"><b>{{ schedule }}</b><small>{{ next }}</small></span>
      <span class="goal-tags">
        <span v-if="saved?.selected && !changed" class="tag accent">{{ host.t('car.goal_next') }}</span>
        <span v-if="!goal.active" class="tag">{{ host.t('car.goal_inactive') }}</span>
        <span v-if="goal.schedule === 'weekly' && goal.holidays" class="tag">{{ host.t('car.goal_holidays') }}</span>
        <button type="button" class="btn goal-edit" :aria-expanded="goal.open" @click="goal.open = !goal.open">
          {{ host.t(goal.open ? 'car.goal_close' : 'car.goal_edit') }}
        </button>
      </span>
    </div>
    <div v-show="goal.open" class="goal-editor">
      <div class="goal-header">
        <label class="check"><input v-model="goal.active" name="active" type="checkbox">{{ host.t('plans.active') }}</label>
        <button type="button" class="delete-goal" @click="remove">{{ host.t('plans.delete') }}</button>
      </div>
      <div class="fields">
        <label>{{ host.t('settings.schedule') }}
          <select v-model="goal.schedule" name="schedule">
            <option value="once">{{ host.t('settings.once') }}</option>
            <option value="weekly">{{ host.t('settings.weekly') }}</option>
          </select>
        </label>
        <SocField v-model="goal.target_soc" name="target_soc" :label="host.t('settings.target_soc')" :factor="factor" />
        <label v-if="goal.schedule === 'once'">{{ host.t('settings.departure') }}
          <input v-model="goal.departure_local" name="departure_local" type="datetime-local" required>
        </label>
        <label v-else>{{ host.t('settings.departure_time') }}
          <input v-model="goal.departure_time" name="departure_time" type="time" required>
        </label>
      </div>
      <div v-if="goal.schedule === 'weekly'" class="checks">
        <label v-for="day in weekdays" :key="day.index">
          <input name="day" type="checkbox" :value="day.index" :checked="goal.weekdays.includes(day.index)" @change="toggleDay(day.index, ($event.target as HTMLInputElement).checked)">{{ day.label }}
        </label>
        <label><input v-model="goal.holidays" name="holidays" type="checkbox">{{ host.t('plans.holidays') }}</label>
      </div>
    </div>
  </fieldset>
</template>
