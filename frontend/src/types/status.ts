/** Control state and notices as the backend sends them (status.py); the browser only presents them. */

export type Severity = 'error' | 'warning' | 'info'

export interface Notice {
  readonly id?: string
  readonly code?: string
  readonly scope?: string
  readonly severity?: Severity
  /** Text key of the message, e.g. "notice.eos". */
  readonly message: string
  /** Measurement keys the message names ({values}). */
  readonly measurements?: readonly string[]
  readonly vehicle_name?: string
  readonly since?: string
  /** A browser-side problem (connection, view loading); never reported to the backend. */
  readonly browser?: boolean
}

export interface ResolvedNotice {
  readonly id?: string
  readonly code: string
  readonly scope?: string
  readonly severity?: Severity
  readonly since?: string
  readonly at: string
}

export interface ControlArea {
  readonly available: boolean
  readonly enabled: boolean
  readonly release_pending: boolean
}

export type ControlKey = 'vehicle' | 'battery'

export interface StatusSnapshot {
  readonly control_status?: string
  readonly armed?: boolean
  readonly release_pending?: boolean
  readonly eos_run?: { readonly state?: string; readonly elapsed_s?: number } | null
  readonly next_mode?: { readonly battery?: { readonly time?: string; readonly mode?: string } | null }
  readonly control?: Readonly<Partial<Record<ControlKey, ControlArea>>>
  readonly notices?: readonly Notice[]
  readonly resolved_notices?: readonly ResolvedNotice[]
  readonly settings?: Readonly<Record<string, unknown>>
  readonly features?: Readonly<Record<string, boolean>>
  readonly zone?: string
}
