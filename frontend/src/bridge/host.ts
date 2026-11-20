/**
 * Bridge to the legacy panel (app.js): until Vue owns routing, app.js creates the views through the
 * controllers in this folder and passes its services as a LegacyContext.
 */
import type { Host, LegacyContext } from '@/types/host'

/** Host services of a legacy context; optional services fall back to safe defaults. */
export function hostOf(context: LegacyContext): Host {
  return {
    request: context.request,
    t: context.t,
    decimal: context.decimal,
    locale: context.getLocale,
    now: context.now ?? Date.now,
    lookup: context.lookup ?? (() => undefined),
    refresh: context.refresh ?? (async () => undefined),
  }
}
