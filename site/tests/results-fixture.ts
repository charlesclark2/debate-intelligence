import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { FIXTURE_SEASON_DIRECTORY, STUDENTS, contentWith, siteRootWith, withConsent } from './content-fixture'
import type { FixtureStudent } from './content-fixture'

/**
 * Fixture content for the results tests: tests/content-fixture.ts's synthetic season with
 * content/results.yaml's list replaced and the consent manifest's students chosen.
 *
 * Every name here is invented, as docs/policies/website-publishing.md (Students 11) requires of
 * a test: the real names live in site/content/ and nowhere else. Nothing here reads the shipped
 * schedule or results, so the tests do not change when the coach adds, moves or takes down a real
 * tournament, result or consent entry (v1-e37-t10).
 */

/** Replaces the `results:` list, which is the last thing in content/results.yaml. */
export function withResults(yaml: string): (source: string) => string {
  return (source) => {
    if (!/^results:/m.test(source)) {
      throw new Error('withResults: no `results:` list in content/results.yaml')
    }
    // Always ends with the marker line, so the edit changes the file even when the shipped list
    // is already empty, and an empty fixture is `[]` rather than the null a bare key reads as.
    const list = yaml.trim() === '' ? 'results: []\n' : `results:\n${yaml.replace(/^\n/, '')}\n`
    return source.replace(/^results:[\s\S]*$/m, `${list}# Fixture content from tests/results-fixture.ts.\n`)
  }
}

/** The edits for one fixture: the results, and the consent manifest's students replaced. */
function fixtureEdits(
  yaml: string,
  students: readonly FixtureStudent[],
): Record<string, (source: string) => string> {
  return { 'results.yaml': withResults(yaml), 'media-consent.yaml': withConsent(students) }
}

/** A content directory with these results and the fixture students' consent. */
export function resultsContent(
  yaml: string,
  students: readonly FixtureStudent[] = Object.values(STUDENTS),
  more: Record<string, (source: string) => string> = {},
): string {
  return contentWith({ ...fixtureEdits(yaml, students), ...more })
}

/** The same, as a site root, for a test that renders a page reading process.cwd()/content. */
export function resultsSiteRoot(
  yaml: string,
  students: readonly FixtureStudent[] = Object.values(STUDENTS),
): string {
  return siteRootWith(fixtureEdits(yaml, students))
}

/**
 * The `results:` list of tests/fixtures/season/results.yaml: five placings at four tournaments,
 * two still on the synthetic schedule and two off it, with every form of who placed. The expected
 * page is written out by hand from that file in tests/results.test.tsx.
 */
export const SEASON_FIXTURE = readFileSync(join(FIXTURE_SEASON_DIRECTORY, 'results.yaml'), 'utf8').split(
  /^results:\n/m,
)[1]!

/**
 * One result at the Birchwood Invitational, a tournament off the synthetic schedule, with the
 * fields given in `fields` replacing or adding to it.
 */
export function oneResult(fields: Record<string, string>): string {
  const base: Record<string, string> = {
    tournament: 'Birchwood Invitational',
    date: '2026-10-17',
    event: 'lincoln-douglas',
    division: 'varsity',
    placing: 'first place',
    ...fields,
  }
  return Object.entries(base)
    .filter(([, value]) => value !== '')
    .map(([key, value], index) => `${index === 0 ? '  - ' : '    '}${key}: ${value}`)
    .join('\n')
}
