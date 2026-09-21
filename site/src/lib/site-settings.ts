/**
 * Build-time settings for the static export.
 *
 * Both values are read from the environment when `next build` runs, never in the browser:
 *
 *   SITE_ENV   'dev' or 'prod'. Anything else (including unset) is treated as 'dev', so a
 *              misconfigured build fails closed: it emits a disallow-everything robots.txt and a
 *              noindex meta tag rather than exposing a preview to search engines.
 *   SITE_URL   the origin the built files will be served from, used for canonical URLs, Open
 *              Graph URLs and sitemap entries. Defaults to the local dev server.
 */

export type SiteEnvironment = 'dev' | 'prod'

export const DEFAULT_SITE_URL = 'http://localhost:3000'

export function readSiteEnvironment(env: NodeJS.ProcessEnv = process.env): SiteEnvironment {
  return env.SITE_ENV === 'prod' ? 'prod' : 'dev'
}

export function isIndexable(env: NodeJS.ProcessEnv = process.env): boolean {
  return readSiteEnvironment(env) === 'prod'
}

/** The site origin with any trailing slash removed, so callers can append absolute paths. */
export function readSiteUrl(env: NodeJS.ProcessEnv = process.env): string {
  const configured = env.SITE_URL?.trim()
  const url = configured && configured.length > 0 ? configured : DEFAULT_SITE_URL
  return url.replace(/\/+$/, '')
}

/** Turns a site-relative route such as `/join/` into an absolute URL for canonical and og tags. */
export function absoluteUrl(route: string, env: NodeJS.ProcessEnv = process.env): string {
  const path = route.startsWith('/') ? route : `/${route}`
  return `${readSiteUrl(env)}${path}`
}
