import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { BackendRequest, PanelSnapshot } from '@/types/host'
import { flush, testContext, type TestContext } from '@/test/host'
import { createCarController, MOUNT_ID } from '@/bridge/carController'
import type { VehicleData } from '@/types/car'
import { chargePlan, fleet, NOW, vehicle } from '@/test/fixtures/car'

let root: HTMLElement

/** A new mount point: each controller mounts its own app. */
function freshRoot() {
  root?.remove()
  root = document.createElement('div')
  root.id = MOUNT_ID
  document.body.append(root)
}
beforeEach(freshRoot)
afterEach(() => root.remove())

function open(route: string, snapshot: object = fleet(), options: { request?: BackendRequest; code?: 'de' | 'en' } = {}) {
  const request = options.request ?? (vi.fn(async () => ({})) as unknown as BackendRequest)
  const refresh = vi.fn(async () => undefined)
  const context: TestContext = testContext({ code: options.code ?? 'de', snapshot: snapshot as PanelSnapshot, request, now: NOW, refresh })
  const view = createCarController(context)
  view.show(route)
  const $ = <T extends Element = HTMLElement>(selector: string) => root.querySelector<T>(selector)
  const text = (selector: string) => $(selector)?.textContent?.replace(/\s+/g, ' ').trim() ?? ''
  /** Simulate the next panel refresh with new backend data. */
  const refreshWith = async (next: object) => {
    context.snapshot = next as PanelSnapshot
    view.show(route)
    await flush()
  }
  return { context, view, request, refresh, $, text, refreshWith }
}

const input = (element: HTMLInputElement | null, value: string, events: string[] = ['input', 'change']) => {
  if (!element) throw new Error('missing input')
  element.value = value
  for (const name of events) element.dispatchEvent(new Event(name, { bubbles: true }))
}
const sent = (request: BackendRequest, call = 0) => (request as unknown as { mock: { calls: unknown[][] } }).mock.calls[call]

describe('all vehicles', () => {
  it('offers all vehicles and each vehicle, with encoded links', async () => {
    const { $, text } = open('car')
    await flush()
    const links = [...root.querySelectorAll<HTMLAnchorElement>('.car-nav a')]
    expect(links.map(link => [link.getAttribute('href'), link.textContent, link.getAttribute('aria-current')]))
      .toEqual([['#car', 'Alle Fahrzeuge', 'page'], ['#car/id4', 'VW ID.4', null], ['#car/a%2Fb', 'Leapmotor', null]])
    expect($('.usage-link')?.getAttribute('href')).toBe('#usage/car')
    expect(text('.car-nav')).not.toContain('<')
  })

  it('compares the vehicles without one vehicle\'s goal, switches, plan or goals', async () => {
    const { $ } = open('car')
    await flush()
    const cards = [...root.querySelectorAll<HTMLAnchorElement>('.vehicle-card')]
    expect(cards.map(card => card.getAttribute('href'))).toEqual(['#car/id4', '#car/a%2Fb'])
    expect(cards[0]?.textContent).toContain('3,7 kW')
    expect(cards[0]?.textContent).toContain('40 % · Lädt')
    expect(cards[0]?.textContent).toContain('Ladeziel 80 % · Kein Termin')
    // A disconnected vehicle says so instead of a power value.
    expect(cards[1]?.classList.contains('vehicle-inactive')).toBe(true)
    expect(cards[1]?.querySelector('strong')?.textContent).toBe('Kein Fahrzeug angeschlossen')
    for (const selector of ['#car-view', '#vehicle-daily', '#car-plan', '#vehicle-goals']) expect($(selector)).toBeNull()
  })
})

describe('a vehicle page', () => {
  it('marks the shown vehicle in the choice and decodes its id', async () => {
    const { $, text } = open('car/a%2Fb')
    await flush()
    expect($('.car-nav a[aria-current="page"]')?.getAttribute('href')).toBe('#car/a%2Fb')
    expect($('.usage-link')?.getAttribute('href')).toBe('#usage/car/a%2Fb')
    expect(text('#car-goal h2')).toBe('Bis 23:00 auf 80 %')
  })

  it('answers the goal first with the backend plan summary', async () => {
    const { $, text } = open('car/id4')
    await flush()
    expect(text('#car-goal h2')).toBe('Bis 23:00 auf 80 %')
    expect(text('#car-goal p')).toContain('Noch 20 kWh. EOS plant 3,7 kWh aus PV bis 16:00 und 16,7 kWh Netzladen ab 19:00 (24 ct/kWh).')
    expect($('.soc-ring')?.getAttribute('aria-label')).toBe('Ladestand 40 %, Ziel 80 %')
    expect(text('#car-goal .goal-tags')).toContain('3,7 kW · 1-phasig')
    expect($('.to-plan')).not.toBeNull()
    expect(text('#car-goal')).not.toContain('Reichweite')
  })

  it('shows the reported or the estimated range', async () => {
    const shown = async (live: VehicleData['live']) => {
      const { text } = open('car/id4', fleet({ live: { car: 0, soc_source: 'vehicle', ...live } }))
      await flush()
      return text('#car-goal .goal-tags')
    }
    expect(await shown({ car_range: 212, car_range_source: 'vehicle' })).toContain('Reichweite 212 km')
    freshRoot()
    expect(await shown({ car_range: 180.4, car_range_source: 'estimate' })).toContain('Reichweite ≈ 180 km')
  })

  it('shows track, list and the cheaper plan against charging now', async () => {
    const { $, text } = open('car/id4')
    await flush()
    expect(text('#car-plan h2')).toBe('EOS-Ladeplan bis 23:00')
    expect(text('#car-plan .panel-heading .tag')).toBe('Plan von 14:58')
    const segments = [...root.querySelectorAll<HTMLButtonElement>('.charge-track .mode-segment')]
    expect(segments.map(segment => segment.style.getPropertyValue('--mode'))).toEqual(['var(--solar)', 'var(--edge)', 'var(--grid)', 'var(--car)'])
    expect(text('#car-plan .list')).toContain('Netzladen 3-phasig mit 6,7 kW')
    const ready = [...root.querySelectorAll('#car-plan .list .row')].at(-1)
    expect(ready?.querySelector('b')?.textContent).toBe('80 % erreicht')
    expect(ready?.querySelector('small')?.textContent).toBe('1 h 30 min Puffer bis 23:00')
    const boxes = [...root.querySelectorAll('.cp-compare > div')].map(box => [box.classList.contains('win'), box.querySelector('small')?.textContent, box.querySelector('strong')?.textContent?.replace(/\s/g, ' ')])
    expect(boxes).toEqual([[true, 'EOS-Plan', '4,29 €'], [false, 'Sofort laden', '≈ 5,55 €']])
    expect(text('#car-plan .footnote')).toContain('Einspeisevergütung von 8 ct/kWh')
    expect($('#car-plan')?.classList.contains('overridden')).toBe(false)
  })

  it('explains a tapped segment of the plan', async () => {
    const { text } = open('car/id4')
    await flush()
    expect(text('#car-plan .mode-detail')).toBe('Abschnitt antippen für Details.')
    const segments = [...root.querySelectorAll<HTMLButtonElement>('.charge-track .mode-segment')]
    segments[2]?.click()
    await flush()
    expect(segments[2]?.getAttribute('aria-pressed')).toBe('true')
    expect(segments[0]?.getAttribute('aria-pressed')).toBe('false')
    expect(text('#car-plan .mode-detail')).toMatch(/^19:00–21:30 · Netzladen · 6,7 kW 3-phasig/)
  })

  it('marks charging now as active when fast charging overrides the plan', async () => {
    const { $, text } = open('car/id4', fleet({ charge_plan: chargePlan({ settings: { fast: true } }) }))
    await flush()
    expect(text('#car-plan .panel-heading .tag')).toBe('überstimmt')
    expect(text('#car-plan .notice-card')).toContain('Schnellladen ist an')
    expect(text('#car-plan .notice-card')).toContain('80 % um ≈ 16:49')
    expect(text('.cp-compare .win small')).toBe('Sofort laden (aktiv)')
    expect($('#car-plan')?.classList.contains('overridden')).toBe(true)
  })

  it('links a suspended plan to the diagnostics and only displays a read-only plan', async () => {
    const suspended = open('car/id4', fleet({ charge_plan: chargePlan({ errors: { wallbox: 'TimeoutError' } }) }))
    await flush()
    expect(suspended.$('#car-plan .notice-card')?.getAttribute('role')).toBe('alert')
    expect(suspended.$('#car-plan .notice-card')?.classList.contains('tone-crit')).toBe(true)
    expect(suspended.$('#car-plan .notice-card a')?.getAttribute('href')).toBe('#notices')
    freshRoot()
    const readOnly = open('car/id4', fleet({ charge_plan: chargePlan({ armed: false }) }))
    await flush()
    expect(readOnly.text('#car-plan .panel-heading .tag')).toBe('nur Anzeige')
    expect(readOnly.text('#car-plan .notice-card')).toContain('Lesemodus')
    expect(readOnly.$('#car-plan')?.classList.contains('overridden')).toBe(true)
  })

  it('says so when EOS has no charging plan instead of inventing segments', async () => {
    const { $, text } = open('car/id4', fleet({ charge_plan: chargePlan({ vehicle_forecast_source: 'constant' }) }))
    await flush()
    expect(text('#car-goal p')).toContain('kein EOS-Ladeplan')
    expect($('.charge-track')).toBeNull()
    expect(text('#car-plan .footnote')).toContain('Die Kurve schreibt nur den Ladestand fort')
  })

  it('scrolls to the plan when the user asked for it', async () => {
    const scroll = vi.fn()
    Element.prototype.scrollIntoView = scroll
    const { view, $ } = open('car/id4')
    await flush()
    $('.to-plan')?.click()
    await flush()
    expect(scroll).toHaveBeenCalledTimes(1)
    view.show('car/id4', { scrollToPlan: true })
    await flush()
    expect(scroll).toHaveBeenCalledTimes(2)
  })
})

describe('charging switches and limits', () => {
  it('save immediately with only the changed value of the shown vehicle', async () => {
    const { $, text, request, refresh } = open('car/id4')
    await flush()
    expect(text('#vehicle-daily .switch')).toContain('Lädt nur mit Überschuss bis 70 %')
    const fast = $<HTMLInputElement>('#vehicle-daily input[name=fast]')
    fast?.click()
    await flush()
    expect(sent(request)).toEqual(['settings', { fast: true, vehicle_id: 'id4' }])
    expect(text('#vehicle-daily output')).toBe('Einstellungen gespeichert')
    expect(refresh).toHaveBeenCalledTimes(1)
  })

  it('reverts a rejected switch and shows the reason', async () => {
    const request = vi.fn(async () => { throw new Error('abgelehnt') }) as unknown as BackendRequest
    const { $, text } = open('car/id4', fleet(), { request })
    await flush()
    const pv = $<HTMLInputElement>('#vehicle-daily input[name=pv]')
    pv?.click()
    await flush()
    expect(pv?.checked).toBe(true)
    expect(text('#vehicle-daily output')).toBe('abgelehnt')
  })

  it('save a valid limit, map the fast target and refuse values outside 1 to 100', async () => {
    const { $, text, request } = open('car/id4')
    await flush()
    input($<HTMLInputElement>('input[name=fast_target_soc]'), '88')
    await flush()
    expect(sent(request)).toEqual(['settings', { target_soc: 88, vehicle_id: 'id4' }])
    input($<HTMLInputElement>('input[name=fast_target_soc]'), '0')
    await flush()
    expect(request).toHaveBeenCalledTimes(1)
    expect(text('#vehicle-daily output')).toMatch(/1 bis 100/)
  })

  it('show the range while the slider moves and save when it is released', async () => {
    const { $, request } = open('car/id4')
    await flush()
    const field = $('#vehicle-daily .soc-field')
    const slider = field?.querySelector<HTMLInputElement>('.soc-slider') ?? null
    input(slider, '81', ['input'])
    await flush()
    expect(field?.querySelector<HTMLInputElement>('input[name=pv_target_soc]')?.value).toBe('81')
    expect(field?.querySelector('output')?.textContent).toBe('81 % · ≈ 324 km')
    expect(request).not.toHaveBeenCalled()
    input(slider, '40', ['input', 'change'])
    await flush()
    expect(sent(request)).toEqual(['settings', { pv_target_soc: 40, vehicle_id: 'id4' }])
  })

  it('follow the backend on refresh but keep a limit the user is typing', async () => {
    const { $, refreshWith } = open('car/id4')
    await flush()
    input($<HTMLInputElement>('input[name=pv_target_soc]'), '55', ['input'])
    await refreshWith(fleet({ settings: { pv: false, fast: false, phase_auto: true, pv_target_soc: 65, target_soc: 90 } }))
    expect($<HTMLInputElement>('input[name=pv_target_soc]')?.value).toBe('55')
    expect($<HTMLInputElement>('input[name=fast_target_soc]')?.value).toBe('90')
    expect($<HTMLInputElement>('input[name=pv]')?.checked).toBe(false)
  })

  it('disable automatic phase switching for a wallbox without it', async () => {
    const { $ } = open('car/id4', fleet({ plugins: { wallbox: { features: { phase_switching: false } } } }))
    await flush()
    const phases = $<HTMLInputElement>('input[name=phase_auto]')
    expect(phases?.disabled).toBe(true)
    expect(phases?.checked).toBe(false)
  })
})

describe('charging goals', () => {
  const goals = () => [...root.querySelectorAll<HTMLFieldSetElement>('#vehicle-goals .charge-goal')]

  it('are compact rows whose editor opens on demand; new goals start open and unsaved', async () => {
    const { $ } = open('car/id4')
    await flush()
    const [first] = goals()
    expect(first?.querySelector('.goal-when')?.textContent).toBe('72 %≈ 288 km')
    expect(first?.querySelector('.goal-text')?.textContent).toContain('Mo, Mi 07:45')
    expect(first?.classList.contains('selected')).toBe(true)
    const editor = first?.querySelector<HTMLElement>('.goal-editor')
    expect(editor?.style.display).toBe('none')
    first?.querySelector<HTMLButtonElement>('.goal-edit')?.click()
    await flush()
    expect(editor?.style.display).toBe('')
    expect(first?.querySelector('.goal-edit')?.getAttribute('aria-expanded')).toBe('true')
    $<HTMLButtonElement>('#vehicle-goals .panel-heading button')?.click()
    await flush()
    const added = goals()[1]
    expect(added?.querySelector<HTMLElement>('.goal-editor')?.style.display).toBe('')
    expect(added?.textContent).toContain('Noch nicht gespeichert')
  })

  it('delete only after confirmation', async () => {
    open('car/id4')
    await flush()
    const confirm = vi.spyOn(globalThis, 'confirm').mockReturnValue(false)
    goals()[0]?.querySelector<HTMLButtonElement>('.delete-goal')?.click()
    await flush()
    expect(goals()).toHaveLength(1)
    confirm.mockReturnValue(true)
    goals()[0]?.querySelector<HTMLButtonElement>('.delete-goal')?.click()
    await flush()
    expect(goals()).toHaveLength(0)
  })

  it('switch the required departure with the schedule and save the local time unchanged', async () => {
    const { request, refresh } = open('car/id4')
    await flush()
    const [first] = goals()
    const schedule = first?.querySelector<HTMLSelectElement>('select[name=schedule]')
    expect(first?.querySelector<HTMLInputElement>('input[name=departure_time]')?.required).toBe(true)
    if (schedule) { schedule.value = 'once'; schedule.dispatchEvent(new Event('change')) }
    await flush()
    expect(first?.querySelector('input[name=departure_time]')).toBeNull()
    input(first?.querySelector<HTMLInputElement>('input[name=departure_local]') ?? null, '2027-04-01T07:30', ['input'])
    input(first?.querySelector<HTMLInputElement>('input[name=target_soc]') ?? null, '77', ['input'])
    await flush()
    root.querySelector<HTMLFormElement>('#vehicle-goals')?.requestSubmit()
    await flush()
    expect(sent(request)).toEqual(['settings', { vehicle_id: 'id4', charge_plans: [{
      id: 'id4_goal', active: true, schedule: 'once', target_soc: 77, departure_local: '2027-04-01T07:30', departure_time: '07:45', holidays: true, weekdays: [0, 2],
    }] }])
    expect(refresh).toHaveBeenCalledTimes(1)
  })

  it('keep unsaved edits during a refresh and follow the backend without edits', async () => {
    const { refreshWith } = open('car/id4')
    await flush()
    const later = (target: number) => fleet({ charge_plan_view: [{ id: 'id4_goal', active: true, schedule: 'weekly', target_soc: target, departure_time: '07:45', weekdays: [0, 2], holidays: true, next_departure: null }] })
    await refreshWith(later(75))
    expect(goals()[0]?.querySelector('.goal-when b')?.textContent).toBe('75 %')
    input(goals()[0]?.querySelector<HTMLInputElement>('input[name=target_soc]') ?? null, '66', ['input'])
    await refreshWith(later(90))
    expect(goals()[0]?.querySelector('.goal-when b')?.textContent).toBe('66 %')
    expect(goals()[0]?.textContent).toContain('Noch nicht gespeichert')
  })

  it('start fresh on another vehicle page', async () => {
    const { view } = open('car/id4')
    await flush()
    input(goals()[0]?.querySelector<HTMLInputElement>('input[name=target_soc]') ?? null, '66', ['input'])
    view.show('car/a%2Fb')
    await flush()
    expect(goals()[0]?.querySelector('.goal-when b')?.textContent).toBe('72 %')
  })
})

describe('routes and installations', () => {
  it('shows the only vehicle of an installation without a vehicle list and sends no vehicle id', async () => {
    const single = { zone: 'Europe/Berlin', ...vehicle('ignored', 'E-Auto') }
    delete (single as { id?: string }).id
    const { $, request } = open('car', single)
    await flush()
    expect($('.car-nav')).toBeNull()
    expect($('#car-goal')).not.toBeNull()
    $<HTMLInputElement>('#vehicle-daily input[name=fast]')?.click()
    await flush()
    expect(sent(request)).toEqual(['settings', { fast: true }])
  })

  it('needs no vehicle choice with one vehicle', async () => {
    const { $ } = open('car/id4', { zone: 'Europe/Berlin', vehicles: [vehicle('id4', 'VW ID.4')] })
    await flush()
    expect($('.car-nav')).toBeNull()
  })

  it('ignores other routes and broken encodings, and shows nothing for an unknown vehicle', async () => {
    const { view, $ } = open('car/unknown')
    await flush()
    expect($('#car-view')).toBeNull()
    expect(view.show('battery')).toBe(false)
    expect(view.show('car/%E0%A4%A')).toBe(false)
  })

  it('renders English texts', async () => {
    const { text } = open('car/id4', fleet(), { code: 'en' })
    await flush()
    expect(text('.car-nav')).toContain('All vehicles')
    expect(text('#vehicle-goals h2')).toBe('Charging goals')
  })

  it('refuses to start without its mount point', () => {
    root.remove()
    const context = testContext({ snapshot: fleet() as unknown as PanelSnapshot, request: (async () => ({})) as BackendRequest, now: NOW })
    expect(() => createCarController(context)).toThrow(/mount point/)
  })
})
