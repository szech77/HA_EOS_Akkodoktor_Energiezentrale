/** SVG shapes of the weather symbols (32×32), rendered as data instead of HTML strings. */
export type Shape = { readonly circle: readonly [cx: number, cy: number, r: number] } | { readonly path: string }

const SUN: readonly Shape[] = [{ circle: [16, 13, 5] }, { path: 'M16 3v2m0 16v2M6 13H4m24 0h-2M8 5l2 2m12 12 2 2M24 5l-2 2M10 19l-2 2' }]
const CLOUD: Shape = { path: 'M8 23h16a6 6 0 0 0 0-12 8 8 0 0 0-15-1 6.5 6.5 0 0 0-1 13Z' }
const MOON: Shape = { path: 'M24 23A12 12 0 0 1 11 3a12 12 0 1 0 13 20Z' }
const RAIN: Shape = { path: 'm9 26-1 3m8-3-1 3m8-3-1 3' }
const LIGHTNING: Shape = { path: 'm17 17-4 7h5l-3 6' }
const SNOW: Shape = { path: 'M8 27h3m-1.5-1.5v3M22 27h3m-1.5-1.5v3' }
const FOG: Shape = { path: 'M4 26h24M7 30h18' }
const WIND: readonly Shape[] = [{ path: 'M3 11h20a4 4 0 1 0-4-4M3 17h24M3 23h15a4 4 0 1 1-4 4' }]
const UNKNOWN: readonly Shape[] = [{ circle: [16, 16, 12] }, { path: 'M16 8v10m0 5v1' }]

/** Shapes for a Home Assistant weather condition; unknown or missing conditions get a neutral symbol. */
export function weatherShapes(condition: string | null | undefined): readonly Shape[] {
  if (!condition || condition === 'unknown' || condition === 'exceptional') return UNKNOWN
  if (condition === 'windy' || condition === 'windy-variant') return WIND
  const base: Shape[] = condition === 'sunny' ? [...SUN] : condition === 'clear-night' ? [MOON]
    : condition === 'partlycloudy' ? [{ circle: [9, 8, 5] }, CLOUD] : [CLOUD]
  if (['rainy', 'pouring', 'lightning-rainy', 'snowy-rainy'].includes(condition)) base.push(RAIN)
  if (['lightning', 'lightning-rainy'].includes(condition)) base.push(LIGHTNING)
  if (['snowy', 'snowy-rainy', 'hail'].includes(condition)) base.push(SNOW)
  if (condition === 'fog') base.push(FOG)
  return base
}
