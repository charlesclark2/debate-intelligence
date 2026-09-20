/**
 * Build-time feature flags for the static export. Like SITE_ENV and SITE_URL they are read when
 * `next build` runs and never reach the browser, so a flag that is off leaves no trace in the
 * exported HTML: there is nothing for a visitor to toggle and nothing for a crawler to find.
 *
 *   SITE_DEBATER_LOGIN       'on' renders the Debater login link in the main navigation.
 *                            Anything else, including unset, leaves it out. Default: off.
 *   SITE_DEBATER_LOGIN_URL   where that link points. Defaults to /app/, because the V2
 *                            authenticated app mounts under this same domain (epic E36).
 *
 * The flag stays off until the V2 app exists (Cognito, web/). The task spec forbids an active
 * Debater login link before then, which is why the default is off rather than on.
 */

export const DEFAULT_DEBATER_LOGIN_URL = '/app/'

/**
 * Just the variables this module reads. `process.env` satisfies it, and a test can pass a plain
 * object literal without having to fake NODE_ENV and the rest of a real environment.
 */
export interface FeatureFlagEnvironment {
  SITE_DEBATER_LOGIN?: string | undefined
  SITE_DEBATER_LOGIN_URL?: string | undefined
  // Keeps process.env assignable: without it TypeScript treats an all-optional interface as a
  // weak type and rejects an environment that happens to set neither variable.
  [variable: string]: string | undefined
}

export function isDebaterLoginEnabled(env: FeatureFlagEnvironment = process.env): boolean {
  return env.SITE_DEBATER_LOGIN === 'on'
}

export function debaterLoginUrl(env: FeatureFlagEnvironment = process.env): string {
  const configured = env.SITE_DEBATER_LOGIN_URL?.trim()
  return configured && configured.length > 0 ? configured : DEFAULT_DEBATER_LOGIN_URL
}

/** The extra navigation item, or null when the flag is off, which is the default. */
export function debaterLoginNavigationItem(
  label: string,
  env: FeatureFlagEnvironment = process.env,
): { href: string; label: string } | null {
  return isDebaterLoginEnabled(env) ? { href: debaterLoginUrl(env), label } : null
}
