/** The real Python backend contract (tests/backend.cjs) instead of hand-written plan data. */
import { createRequire } from 'node:module'

const require = createRequire(import.meta.url)
const call = require('../../../tests/backend.cjs') as (operation: string, data: unknown, options?: Record<string, unknown>) => unknown

export function backend<T>(operation: string, data: unknown, options: Record<string, unknown> = {}): T {
  return call(operation, data, options) as T
}
