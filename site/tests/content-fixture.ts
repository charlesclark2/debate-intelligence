import { cpSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

/**
 * Content directories for the site tests: a copy of site/content/ with the season's schedule and
 * results swapped for a synthetic season of their own (v1-e37-t10).
 *
 * The coach edits content/tournaments.yaml and content/results.yaml every week. A test that read
 * them for an entry, a count or an order failed at every edit: on 2026-10-30 one tournament off
 * the schedule failed 35 tests. So a behaviour test reads tests/fixtures/season/ instead, whose
 * entries its expected values are written from by hand, and the consent manifest's students are
 * replaced by the invented ones below. Everything else (the pages, the events, the words around
 * the schedule) is the shipped copy. What the shipped schedule and results must always satisfy
 * is checked in tests/shipped-content.test.ts, for any entries they hold.
 *
 * Every name here is invented, as docs/policies/website-publishing.md (Students 11) requires of
 * a test: the real names live in site/content/ and nowhere else.
 */

export const FIXTURE_SEASON_DIRECTORY = join(process.cwd(), 'tests/fixtures/season')

/** The season tests/fixtures/season/ is for. The consent manifest's copy is set to it too. */
export const FIXTURE_SEASON = '2026-27'

/**
 * The capitalised phrases in the synthetic season, reviewed for the fixture as a coach reviews a
 * real one: tournaments and schools, none a person. Added to the copy's permittedNamePhrases, so
 * the guard covers them as it covers the shipped schedule.
 */
export const FIXTURE_NAME_PHRASES = [
  'Lantern Hill Invitational',
  'Harbor Point High School',
  'Granite Falls Round Robin',
  'Lakeshore Invitational',
  'Copper Creek Qualifier',
  'Northwoods Classic',
  'Pine Hollow Open',
  'Silver Lake Qualifier',
  'Prairie Cup',
  'Birchwood Invitational',
]

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
    `    season: '${student.season ?? FIXTURE_SEASON}'`,
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
    return source.replace(list, `${entries}# Fixture students from tests/content-fixture.ts.\n`)
  }
}

/** Replaces exactly one occurrence of `target`, failing if there is not exactly one. */
export function replaceOnce(target: string, replacement: string): (source: string) => string {
  return (source) => {
    const count = source.split(target).length - 1
    if (count !== 1) {
      throw new Error(`replaceOnce: expected one "${target}", found ${count}`)
    }
    return source.replace(target, replacement)
  }
}

/**
 * The consent manifest for the synthetic season: its season set to the fixture's, its students
 * replaced by STUDENTS, and the fixture's phrases reviewed. The shipped phrases stay, because the
 * shipped pages in the copy are checked against them.
 */
function fixtureConsent(source: string): string {
  const season = replaceSeason(source)
  const phrases = season.replace(
    /^permittedNamePhrases:\n/m,
    `permittedNamePhrases:\n${FIXTURE_NAME_PHRASES.map((phrase) => `  - ${phrase}\n`).join('')}`,
  )
  if (phrases === season) {
    throw new Error('contentWith: no `permittedNamePhrases:` list in content/media-consent.yaml')
  }
  return withConsent(Object.values(STUDENTS))(phrases)
}

function replaceSeason(source: string): string {
  const pattern = /^season: '\d{4}-\d{2}'$/m
  if (!pattern.test(source)) {
    throw new Error('contentWith: no `season:` line in content/media-consent.yaml')
  }
  return source.replace(pattern, `season: '${FIXTURE_SEASON}'`)
}

function applyEdits(directory: string, edits: Record<string, (source: string) => string>): void {
  for (const [file, edit] of Object.entries(edits)) {
    const path = join(directory, file)
    const before = readFileSync(path, 'utf8')
    const after = edit(before)
    if (after === before) {
      throw new Error(`contentWith: the edit to ${file} changed nothing`)
    }
    writeFileSync(path, after)
  }
}

function shippedCopy(): string {
  const directory = mkdtempSync(join(tmpdir(), 'site-content-'))
  cpSync(join(process.cwd(), 'content'), directory, { recursive: true })
  return directory
}

/**
 * A content directory with the synthetic season, then `edits` applied. `edits` maps a file under
 * content/ to a function from its text to the new text; each edit must change something, so a
 * replacement whose target has moved fails loudly instead of testing the unedited file.
 */
export function contentWith(edits: Record<string, (source: string) => string> = {}): string {
  const directory = shippedCopy()
  for (const file of ['tournaments.yaml', 'results.yaml']) {
    cpSync(join(FIXTURE_SEASON_DIRECTORY, file), join(directory, file))
  }
  const consentPath = join(directory, 'media-consent.yaml')
  writeFileSync(consentPath, fixtureConsent(readFileSync(consentPath, 'utf8')))
  applyEdits(directory, edits)
  return directory
}

/**
 * A copy of the content the site ships, entries and all, with `edits` applied: for planting a
 * break in the real files and showing a check on them refuses it (tests/shipped-content.test.ts).
 * A behaviour test never uses this; its expected values would change with every coach's edit.
 */
export function shippedContentWith(edits: Record<string, (source: string) => string> = {}): string {
  const directory = shippedCopy()
  applyEdits(directory, edits)
  return directory
}

/**
 * The same as contentWith, as a site root, for a test that renders a page or the layout reading
 * `process.cwd()/content`: point `process.cwd()` at the returned root.
 */
export function siteRootWith(edits: Record<string, (source: string) => string> = {}): string {
  const root = mkdtempSync(join(tmpdir(), 'site-root-'))
  cpSync(contentWith(edits), join(root, 'content'), { recursive: true })
  return root
}
