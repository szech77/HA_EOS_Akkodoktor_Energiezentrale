import { inject, type InjectionKey, type ShallowRef } from 'vue'
import type { Host, PanelSnapshot } from './types'

export const HOST: InjectionKey<Host> = Symbol('eos-host')
export const SNAPSHOT: InjectionKey<ShallowRef<PanelSnapshot>> = Symbol('eos-snapshot')

function required<T>(key: InjectionKey<T>, name: string): T {
  const value = inject(key)
  if (value === undefined) throw new Error(`${name} is not provided`)
  return value
}

/** Host services (backend request, texts, formatting) of the surrounding panel. */
export const useHost = (): Host => required(HOST, 'Host')

/** The current panel snapshot; replaced (not mutated) on every panel refresh. */
export const useSnapshot = (): ShallowRef<PanelSnapshot> => required(SNAPSHOT, 'Snapshot')
