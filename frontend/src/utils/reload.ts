/**
 * Reload the panel with a new build parameter, so the browser fetches every UI file again instead
 * of mixing cached files of different releases.
 */
export function reloadPanel(location: Pick<Location, 'href' | 'replace'> = window.location, now = Date.now()): void {
  const target = new URL(location.href)
  target.searchParams.set('v', String(now))
  location.replace(target.href)
}

/** The build version the HA panel put into the page address; versioned asset URLs use it. */
export function buildVersion(href: string): string | null {
  return new URL(href).searchParams.get('v')
}
