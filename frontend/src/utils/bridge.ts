/**
 * Requests to the integration through the HA panel (panel.js): the iframe posts a message to its
 * parent, which calls the authenticated Home Assistant WebSocket API. No token enters the iframe.
 */

const TIMEOUT_MS = 30_000
const CODE = /^[a-z_]{1,64}$/
const NAME = /^[a-z_]{1,40}$/

/** A failed request: an allow-listed error code, the action and backend field hints, never raw text. */
export class RequestError extends Error {
  readonly code: string
  readonly action: string
  readonly reason: string | null
  readonly fields: readonly string[]
  /** Asset that failed to load (startup diagnostics only). */
  asset?: string

  constructor(message: string, code: string, action: string, details: { reason?: unknown; fields?: unknown } = {}) {
    super(message)
    this.name = 'RequestError'
    this.code = code
    this.action = action
    this.reason = typeof details.reason === 'string' && NAME.test(details.reason) ? details.reason : null
    this.fields = Array.isArray(details.fields) ? details.fields.filter((field): field is string => typeof field === 'string' && NAME.test(field)) : []
  }
}

/** Builds the user-facing message of a request error from the current texts. */
export type ErrorText = (code: string, action: string) => string

export interface BridgeWindow {
  readonly parent: { postMessage(message: unknown, origin: string): void }
  readonly location: { readonly origin: string }
  addEventListener(type: 'message', listener: (event: MessageEvent) => void): void
}

export function createBridge(view: BridgeWindow, message: ErrorText, clientId: string = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`) {
  let next = 0
  const pending = new Map<number, { resolve(value: unknown): void; reject(error: RequestError): void; timer: ReturnType<typeof setTimeout>; action: string }>()

  const error = (code: unknown, action: string, details: { reason?: unknown; fields?: unknown } = {}) => {
    const safe = typeof code === 'string' && CODE.test(code) ? code : 'request_failed'
    return new RequestError(message(safe, action), safe, action, details)
  }

  // Answers only from the parent panel of the same origin, addressed to this client.
  view.addEventListener('message', event => {
    const data = event.data as { channel?: unknown; client?: unknown; id?: unknown; error?: unknown; result?: unknown; reason?: unknown; fields?: unknown } | null
    if (event.source !== view.parent || event.origin !== view.location.origin || data?.channel !== 'eos-energy-response') return
    if (data.client !== undefined && data.client !== clientId) return
    const request = typeof data.id === 'number' ? pending.get(data.id) : undefined
    if (!request || typeof data.id !== 'number') return
    clearTimeout(request.timer)
    pending.delete(data.id)
    if (data.error) request.reject(error(data.error, request.action, data))
    else request.resolve(data.result)
  })

  return {
    error,
    request<T>(action: string, values: Readonly<Record<string, unknown>> = {}): Promise<T> {
      if ((view.parent as unknown) === (view as unknown)) return Promise.reject(error('ingress_only', action))
      const id = ++next
      return new Promise<T>((resolve, reject) => {
        const timer = setTimeout(() => {
          pending.delete(id)
          reject(error('timeout', action))
        }, action === 'eos_setup' ? 150_000 : TIMEOUT_MS)
        pending.set(id, { resolve: resolve as (value: unknown) => void, reject, timer, action })
        view.parent.postMessage({ channel: 'eos-energy-request', id, client: clientId, action, values }, view.location.origin)
      })
    },
  }
}

export type Bridge = ReturnType<typeof createBridge>
