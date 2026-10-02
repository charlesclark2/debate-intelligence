import { buildScheduleCalendar } from '@/lib/icalendar'
import { readSiteUrl } from '@/lib/site-settings'
import { loadScheduleView } from '@/lib/tournaments'

/**
 * /schedule.ics: the calendar file parents subscribe to, generated from content/tournaments.yaml.
 *
 * A static route handler rather than a step bolted onto the build script, for three reasons:
 *
 *   - it reads the schedule through the same loader as /schedule/, in the same process, so the
 *     page and the file cannot be built from two different readings of the data, and a schedule
 *     the loader rejects fails `next build` itself;
 *   - `force-static` makes Next write it into site/out/ at build time like sitemap.xml, so
 *     `pnpm build`, scripts/build-export.mjs, the export checks and scripts/site_deploy.sh all
 *     carry it without a change, and there is still no runtime backend (the publishing policy's
 *     Analytics and third parties, item 8);
 *   - the loader is TypeScript, and a separate Node script would need a TypeScript runner added as
 *     a dependency just to import it.
 *
 * The export is static, so the Content-Type below is for `next dev` only; on the live site S3
 * serves the file as text/calendar from its extension.
 */
export const dynamic = 'force-static'

export function GET(): Response {
  return new Response(buildScheduleCalendar(loadScheduleView(), readSiteUrl()), {
    headers: { 'Content-Type': 'text/calendar; charset=utf-8' },
  })
}
