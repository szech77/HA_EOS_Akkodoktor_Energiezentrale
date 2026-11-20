import { inject, shallowRef, type InjectionKey, type ShallowRef } from 'vue'
import type { Host } from '@/types/host'
import type { OverviewSnapshot } from '@/types/overview'
import { createFlowNodes, type FlowNodes } from '@/utils/energyFlow'
import { createFormat, type Format } from '@/utils/format'
import { createStateLabels, type StateLabels } from '@/utils/modes'
import { createPlanOverview, type PlanOverview } from '@/utils/planOverview'

/** State of the overview page: the current snapshot and its presentation helpers. */
export interface OverviewStore {
  readonly host: Host
  readonly snapshot: ShallowRef<OverviewSnapshot>
  /** Time of the shown snapshot. */
  readonly now: ShallowRef<number>
  /** Versioned logo of the panel build for the hub of the flow. */
  readonly logo: string
  readonly format: Format
  readonly states: StateLabels
  readonly flow: FlowNodes
  readonly plan: PlanOverview
}

export const OVERVIEW_STORE: InjectionKey<OverviewStore> = Symbol('eos-overview')

export function createOverviewStore(host: Host, initial: OverviewSnapshot, logo: string): OverviewStore {
  const snapshot = shallowRef(initial)
  const format = createFormat(host, () => snapshot.value.zone)
  const states = createStateLabels(host)
  return {
    host,
    snapshot,
    now: shallowRef(host.now()),
    logo,
    format,
    states,
    flow: createFlowNodes(host, format),
    plan: createPlanOverview(host, format, states),
  }
}

export function useOverviewStore(): OverviewStore {
  const store = inject(OVERVIEW_STORE)
  if (!store) throw new Error('Overview store is not provided')
  return store
}
