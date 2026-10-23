import { contentWith, siteRootWith } from './schedule-fixture'

/**
 * Fixture content for the results tests: a copy of site/content/ with content/results.yaml's
 * list replaced and invented students added to the consent manifest.
 *
 * Every name here is invented, as docs/policies/website-publishing.md (Students 11) requires of
 * a test: the real names live in site/content/ and nowhere else. The edits work whatever the
 * shipped files hold, so the tests do not change when a real result or consent entry is added.
 */

export interface FixtureStudent {
  publishedName: string
  graduationYear?: number
  consentReference: string
  publishedForm?: 'full-name-and-class-year' | 'first-name-only'
  season?: string
  dateChecked?: string
}

/** Four students with current-season consent, and two whose entries do not allow a full name. */
export const STUDENTS = {
  jordan: { publishedName: 'Jordan Rivera', graduationYear: 2028, consentReference: 'MC-2026-014' },
  sam: { publishedName: 'Sam Okafor', graduationYear: 2027, consentReference: 'MC-2026-021' },
  avery: { publishedName: 'Avery Chen', graduationYear: 2029, consentReference: 'MC-2026-033' },
  morgan: { publishedName: 'Morgan Blake', graduationYear: 2028, consentReference: 'MC-2026-040' },
  /** Consent from last season, never renewed: the start-of-season check found the gap. */
  lapsed: {
    publishedName: 'Riley Moss',
    graduationYear: 2027,
    consentReference: 'MC-2025-003',
    season: '2025-26',
    dateChecked: '2025-09-12',
  },
  /** A family that asked for the first name only. */
  reduced: {
    publishedName: 'Casey Park',
    consentReference: 'MC-2026-052',
    publishedForm: 'first-name-only',
  },
} as const satisfies Record<string, FixtureStudent>

function consentEntry(student: FixtureStudent): string {
  return [
    `  - publishedName: ${student.publishedName}`,
    `    publishedForm: ${student.publishedForm ?? 'full-name-and-class-year'}`,
    ...(student.graduationYear === undefined ? [] : [`    graduationYear: ${student.graduationYear}`]),
    `    consentReference: ${student.consentReference}`,
    `    season: '${student.season ?? '2026-27'}'`,
    `    dateChecked: ${student.dateChecked ?? '2026-09-18'}`,
    '',
  ].join('\n')
}

/**
 * Replaces the manifest's student list with these students, whatever it held, so a fixture never
 * depends on (or prints) a real entry.
 */
export function withConsent(students: readonly FixtureStudent[]): (source: string) => string {
  return (source) => {
    const list = /^students:(?: \[\])?\n(?:(?: {2}.*)?\n)*/m
    if (!list.test(source)) {
      throw new Error('withConsent: no `students:` list in content/media-consent.yaml')
    }
    const entries = students.length === 0 ? 'students: []\n' : `students:\n${students.map(consentEntry).join('')}`
    return source.replace(list, `${entries}# Fixture students from tests/results-fixture.ts.\n`)
  }
}

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
 * Five placings at four tournaments, two still on the schedule and two off it, with every form
 * of who placed: one named student, two awards to the same student, a named partnership, and two
 * team-level results. The expected page is written out by hand in tests/results.test.tsx.
 */
export const SEASON_FIXTURE = `
  - tournament: Fort Atkinson
    date: 2026-10-17
    event: lincoln-douglas
    division: varsity
    placing: first place
    students: [Jordan Rivera]

  - tournament: Fort Atkinson
    date: 2026-10-17
    event: lincoln-douglas
    division: varsity
    placing: top speaker
    students: [Jordan Rivera]

  - scheduleId: west-bend-2026
    event: public-forum
    division: novice
    placing: quarterfinalist
    students: [Sam Okafor, Avery Chen]

  - tournament: Neenah
    date: 2026-10-03
    event: policy
    division: varsity
    placing: semifinalist

  - scheduleId: badgerland-2026
    event: lincoln-douglas
    division: junior-varsity
    placing: second speaker
`

/** One result at Fort Atkinson, with the fields given in `fields` replacing or adding to it. */
export function oneResult(fields: Record<string, string>): string {
  const base: Record<string, string> = {
    tournament: 'Fort Atkinson',
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
