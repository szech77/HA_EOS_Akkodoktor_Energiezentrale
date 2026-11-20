import { describe, expect, it } from 'vitest'
import { points, sampleAt, type Series } from '@/utils/chartSeries'
import { powerFraction } from '@/utils/energyFlow'

const NOW = Date.parse('2026-11-09T12:00:00Z')
const iso = (offset: number) => new Date(NOW + offset).toISOString()
const series = (actual: Series['actual'], future: Series['future']): Series => ({ key: 'power', label: '', divisor: 1, color: 'grid', actual, future })

describe('chart series', () => {
  it('treat missing and malformed readings as gaps while signed flows and zero stay valid', () => {
    const rows = [{ time: iso(0), power: -470 }, { time: iso(-1000), power: 0 }, { time: iso(-2000), power: null }, { time: 'bad', power: 200 }, { time: iso(1000), power: Infinity }]
    expect(points(rows, 'power', NOW - 5000, NOW + 5000).map(point => point.value)).toEqual([0, -470])
  })

  it('use nearby measurements without extrapolating across long outages', () => {
    const data = series([{ stamp: NOW - 60_000, end: NaN, value: -470 }], [])
    expect(sampleAt(data, NOW, NOW)?.point.value).toBe(-470)
    expect(sampleAt(data, NOW - 60_000 - 360_001, NOW)).toBeNull()
    expect(sampleAt(data, NOW + 1, NOW)).toBeNull()
  })

  it('follow forecast slot boundaries, including a slot already in progress', () => {
    const data = series([], [{ stamp: NOW - 60_000, end: NOW + 60_000, value: 4000 }, { stamp: NOW + 60_000, end: NOW + 120_000, value: 2000 }])
    expect(sampleAt(data, NOW + 1, NOW)?.point.value).toBe(4000)
    expect(sampleAt(data, NOW + 60_000, NOW)?.point.value).toBe(2000)
    expect(sampleAt(data, NOW + 120_000, NOW)).toBeNull()
    expect(sampleAt(data, NOW, NOW)).toBeNull()
  })
})

describe('power rings', () => {
  it('fill linearly with the signed magnitude and need a usable reference', () => {
    expect(powerFraction(2500, 10000)).toBe(0.25)
    expect(powerFraction(-1190, 4760)).toBe(0.25)
    expect(powerFraction(0, 10000)).toBe(0)
    expect(powerFraction(12000, 10000)).toBe(1)
    for (const [value, maximum] of [[null, 1000], [NaN, 1000], [100, null], [100, 0]]) expect(powerFraction(value, maximum)).toBeNull()
  })
})
