<script setup lang="ts">
import { computed, provide } from 'vue'
import { isNumber } from '@/shared/format'
import { useCar } from '../state'
import { GOAL_DRAFT, useGoalDraft } from '../useGoalDraft'
import GoalItem from './GoalItem.vue'

/** Charging goals of the shown vehicle, edited together and saved with one button. */
const { host, vehicle } = useCar()
const draft = useGoalDraft(host, vehicle)
provide(GOAL_DRAFT, draft)
const factor = computed(() => {
  const value = vehicle.value?.live.car_range_per_soc
  return isNumber(value) && value > 0 ? value : null
})
</script>

<template>
  <!-- Native validation: the submit event only fires with complete goals. -->
  <form id="vehicle-goals" class="plan-panel" @submit.prevent="draft.save()">
    <div class="panel-heading">
      <h2>{{ host.t('plans.goals') }}</h2>
      <button type="button" class="btn" :disabled="draft.full.value" @click="draft.add()">{{ host.t('plans.add') }}</button>
    </div>
    <p class="footnote">{{ host.t('plans.selection_note') }}</p>
    <div class="charge-plans">
      <GoalItem v-for="row in draft.rows.value" :id="row.id" :key="row.id" :factor="factor" />
    </div>
    <div class="form-footer">
      <button type="submit" class="save">{{ host.t('settings.save') }}</button>
      <output id="vehicle-saved" role="status">{{ draft.status.value }}</output>
    </div>
  </form>
</template>
