<script setup lang="ts">
import { computed } from 'vue'
import { useCar } from '../state'
import type { ChargePlan, VehicleLive } from '../types'
import SocRing from './SocRing.vue'

/** The answer first: SoC against the goal, what EOS plans until the departure, current state. */
const props = defineProps<{ plan: ChargePlan; live: VehicleLive }>()
const emit = defineEmits<{ toPlan: [] }>()
const { host, labels } = useCar()

const title = computed(() => labels.goalTitle(props.plan))
const summary = computed(() => labels.summary(props.plan))
const tags = computed(() => labels.goalTags(props.live))
</script>

<template>
  <section id="car-goal" class="plan-panel car-goal">
    <div class="soc-goal-head">
      <SocRing :soc="plan.soc" :target="plan.target_soc" />
      <div class="goal-copy">
        <h2>{{ title }}</h2>
        <p class="dim">
          {{ summary }}
          <template v-if="plan.segments?.length">
            {{ ' ' }}<a href="#car-plan" class="to-plan" @click.prevent="emit('toPlan')">{{ host.t('car.to_plan') }}</a>
          </template>
        </p>
        <div class="goal-tags">
          <span v-for="tag in tags" :key="tag" class="tag">{{ tag }}</span>
        </div>
      </div>
    </div>
  </section>
</template>
