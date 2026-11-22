import { onBeforeUnmount, shallowRef, type ShallowRef } from 'vue'

/** Width of the panel window; charts size themselves to it and redraw on resize. */
export function useViewport(target: Pick<Window, 'innerWidth' | 'addEventListener' | 'removeEventListener'> = window): ShallowRef<{ width: number }> {
  const viewport = shallowRef({ width: target.innerWidth })
  const follow = () => {
    viewport.value = { width: target.innerWidth }
  }
  target.addEventListener('resize', follow)
  onBeforeUnmount(() => target.removeEventListener('resize', follow))
  return viewport
}

/** Narrow screens start with collapsed detail sections. */
export const narrowScreen = (target: Pick<Window, 'matchMedia'> = window) => Boolean(target.matchMedia?.('(max-width:640px)').matches)
