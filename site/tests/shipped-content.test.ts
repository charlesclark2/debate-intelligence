import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

import { loadSiteSettings } from '@/lib/content'
import { consentGuardedContent, loadMediaConsent } from '@/lib/media-consent'
import { checkPublishingPolicy } from '@/lib/publishing-policy'
import { loadResults, loadResultsView, resultsGuardedContent } from '@/lib/results'
import { loadSchedule, loadScheduleView, readYaml, scheduleGuardedContent } from '@/lib/tournaments'

import { shippedContentWith } from './content-fixture'

/**
 * What the schedule and results the site ships must always satisfy, whatever entries the coach
 * has put in them (v1-e37-t10).
 *
 * The coach edits content/tournaments.yaml and content/results.yaml every week: a tournament off
 * the schedule once it has happened, its results moved to `tournament` and `date`, a result
 * added. So nothing here reads an entry, a count or an order. It checks only what must hold of
 * any content the site may publish: it parses against the schema, it passes the publishing-policy
 * and consent guards, no id is used twice, every date is inside the season, and the files are for
 * one season. Behaviour is tested on the synthetic season in tests/fixtures/season/.
 *
 * Each guarantee is one check, run twice: on content/ itself, and on a copy of it with a break
 * planted, which the same check must refuse. The plants are added beside whatever the shipped
 * files hold, so they work at any point in the season, and every name in them is invented.
 * A failure names the entry by its position, never a student by name (Students 10).
 */

const SHIPPED = join(process.cwd(), 'content')

interface RawEntry {
  id?: unknown
  start?: unknown
  end?: unknown
  date?: unknown
  students?: unknown
}

/** A file as typed, before any loader has judged it, so a check does not lean on the loader's. */
function raw(directory: string, file: 'tournaments.yaml' | 'results.yaml' | 'media-consent.yaml') {
  const data = readYaml(directory, file, `content/${file}`) as { season?: unknown; tournaments?: unknown; results?: unknown }
  const list = file === 'tournaments.yaml' ? data.tournaments : data.results
  return { season: String(data.season), entries: (Array.isArray(list) ? list : []) as RawEntry[] }
}

/** One check per guarantee. Each throws, giving the reason, when a content directory breaks it. */
const checks: Record<string, (directory: string) => void> = {
  /** Both files load through the build's own loaders: schema, events, house style, and the pages. */
  schema: (directory) => {
    loadSchedule(directory)
    loadScheduleView(directory)
    loadResults(directory)
    loadResultsView(directory)
  },

  /** The schedule, the results and the consent manifest are for the same season. */
  oneSeason: (directory) => {
    const seasons = (['tournaments.yaml', 'results.yaml', 'media-consent.yaml'] as const).map(
      (file) => `${file} ${raw(directory, file).season}`,
    )
    if (new Set(seasons.map((season) => season.split(' ')[1])).size !== 1) {
      throw new Error(`the content files are for different seasons: ${seasons.join(', ')}`)
    }
  },

  /** No tournament id is used twice: a calendar app knows a tournament by it. */
  uniqueIds: (directory) => {
    const counts = new Map<string, number>()
    for (const entry of raw(directory, 'tournaments.yaml').entries) {
      counts.set(String(entry.id), (counts.get(String(entry.id)) ?? 0) + 1)
    }
    const repeated = [...counts].filter(([, count]) => count > 1)
    if (repeated.length > 0) {
      throw new Error(repeated.map(([id, count]) => `id "${id}" is used by ${count} entries`).join('; '))
    }
  },

  /** Every date typed into either file is inside the season, 1 August to 31 July. */
  seasonDates: (directory) => {
    for (const file of ['tournaments.yaml', 'results.yaml'] as const) {
      const { season, entries } = raw(directory, file)
      const first = `${season.slice(0, 4)}-08-01`
      const last = `${Number(season.slice(0, 4)) + 1}-07-31`
      entries.forEach((entry, index) => {
        for (const date of [entry.start, entry.end, entry.date]) {
          if (date !== undefined && (String(date) < first || String(date) > last)) {
            throw new Error(`content/${file}, entry ${index + 1}: ${String(date)} is outside the season (${first} to ${last})`)
          }
        }
      })
    }
  },

  /** The publishing-policy guard finds nothing in either file, in the words the pages print. */
  publishingPolicy: (directory) => {
    const { errors } = checkPublishingPolicy({
      pages: [
        ...scheduleGuardedContent(directory),
        ...resultsGuardedContent(directory),
        ...consentGuardedContent(directory),
      ],
      settings: loadSiteSettings(directory),
      consent: loadMediaConsent(directory),
    })
    if (errors.length > 0) {
      throw new Error(errors.map((finding) => `${finding.location}: ${finding.message}`).join('\n'))
    }
  },

  /**
   * Every student a result names has an entry in the consent manifest. Whether the entry allows
   * the name this season is the build's choice, which prints the team-level form when it does not.
   */
  consent: (directory) => {
    const consented = new Set(loadMediaConsent(directory).students.map((student) => student.publishedName.toLowerCase()))
    raw(directory, 'results.yaml').entries.forEach((entry, index) => {
      const names = Array.isArray(entry.students) ? entry.students.map(String) : []
      if (names.some((name) => !consented.has(name.trim().toLowerCase()))) {
        throw new Error(
          `content/results.yaml, result ${index + 1}: names a student with no entry in content/media-consent.yaml`,
        )
      }
    })
  },
}

/** The first year of the shipped season, so a planted date is inside it whichever season it is. */
const seasonYear = Number(
  String((readYaml(SHIPPED, 'tournaments.yaml', 'content/tournaments.yaml') as { season: string }).season).slice(0, 4),
)

/**
 * Adds an entry to the end of a file's list (`tournaments:` or `results:`), which is the last
 * thing in both files, whether the list holds entries or is `[]`.
 */
function appendTo(list: 'tournaments' | 'results', entry: string): (source: string) => string {
  return (source) => {
    const opened = source.replace(new RegExp(`^${list}: \\[\\]\\s*$`, 'm'), `${list}:\n`)
    const start = opened.search(new RegExp(`^${list}:\\n`, 'm'))
    if (start < 0 || /^[^\s#]/m.test(opened.slice(start).split('\n').slice(1).join('\n'))) {
      throw new Error(`appendTo: \`${list}:\` is not the last thing in the file`)
    }
    return `${opened.trimEnd()}\n\n${entry}\n`
  }
}

/** A tournament no real schedule has, valid unless `fields` makes it otherwise. */
function plantedTournament(fields: Record<string, string> = {}): string {
  const entry: Record<string, string> = {
    id: `planted-check-${seasonYear}`,
    name: 'Plantedtown',
    start: `${seasonYear}-09-12`,
    events: '[policy]',
    held: 'online-from-home',
    overnight: 'no',
    status: 'confirmed',
    ...fields,
  }
  return Object.entries(entry)
    .map(([key, value], index) => `${index === 0 ? '  - ' : '    '}${key}: ${value}`)
    .join('\n')
}

/** A team-level result at a tournament off the schedule, valid unless `fields` makes it otherwise. */
function plantedResult(fields: Record<string, string> = {}): string {
  const entry: Record<string, string> = {
    tournament: 'Plantedtown',
    date: `${seasonYear}-09-12`,
    event: 'lincoln-douglas',
    division: 'novice',
    placing: 'top speaker',
    ...fields,
  }
  return Object.entries(entry)
    .map(([key, value], index) => `${index === 0 ? '  - ' : '    '}${key}: ${value}`)
    .join('\n')
}

describe('the schedule and results the site ships', () => {
  it.each(Object.keys(checks))('pass the %s check', (name) => {
    expect(() => checks[name]!(SHIPPED)).not.toThrow()
  })

  it('carry no email address or phone number in the schedule', () => {
    const text = loadSchedule()
      .tournaments.flatMap((entry) => [entry.name, entry.notes, entry.condition, ...entry.arrangements.map((g) => g.where)])
      .join('\n')
    expect(text).not.toMatch(/@/)
    expect(text).not.toMatch(/\d{3}[\s.-]\d{4}/)
  })
})

/**
 * acceptance criterion 3: every guard still refuses on the shipped files. Each case plants one
 * break in a copy of content/ and runs the one check that guarantee belongs to.
 */
describe('a break planted in a copy of the shipped content is refused', () => {
  it.each([
    [
      'schema',
      'a tournament with a misspelt field',
      { 'tournaments.yaml': appendTo('tournaments', plantedTournament({ note: 'Bring a coat.' })) },
      /field note: is not a field a tournament has/,
    ],
    [
      'schema',
      'a result whose placing is a record',
      { 'results.yaml': appendTo('results', plantedResult({ placing: "'5-1 record'" })) },
      /field placing: .* is a record, not a placing/,
    ],
    [
      'oneSeason',
      'a results file for another season',
      {
        'results.yaml': (source: string) =>
          source.replace(/^season: '\d{4}-\d{2}'$/m, `season: '${seasonYear + 1}-${String(seasonYear + 2).slice(2)}'`),
      },
      /are for different seasons/,
    ],
    [
      'uniqueIds',
      'two tournaments with one id',
      {
        'tournaments.yaml': (source: string) =>
          appendTo('tournaments', plantedTournament({ name: 'Secondtown' }))(
            appendTo('tournaments', plantedTournament())(source),
          ),
      },
      new RegExp(`id "planted-check-${seasonYear}" is used by 2 entries`),
    ],
    [
      'seasonDates',
      'a tournament dated in the season before',
      { 'tournaments.yaml': appendTo('tournaments', plantedTournament({ start: `${seasonYear - 1}-11-07` })) },
      new RegExp(`${seasonYear - 1}-11-07 is outside the season`),
    ],
    [
      'seasonDates',
      'a result dated in the season after',
      { 'results.yaml': appendTo('results', plantedResult({ date: `${seasonYear + 1}-08-08` })) },
      new RegExp(`${seasonYear + 1}-08-08 is outside the season`),
    ],
    [
      'publishingPolicy',
      'a phone number in a tournament’s notes',
      { 'tournaments.yaml': appendTo('tournaments', plantedTournament({ notes: "'Call 414-555-0142.'" })) },
      /phone number/,
    ],
    [
      'publishingPolicy',
      'an email address in a result’s tournament',
      { 'results.yaml': appendTo('results', plantedResult({ tournament: "'Plantedtown, coach@example.org'" })) },
      /email address/,
    ],
    [
      'consent',
      'a result naming a student with no consent entry',
      { 'results.yaml': appendTo('results', plantedResult({ students: '[Taylor Brooks]' })) },
      /names a student with no entry in content\/media-consent\.yaml/,
    ],
  ])('the %s check refuses %s', (name, _plant, edits, reason) => {
    const copy = shippedContentWith(edits)
    expect(() => checks[name]!(copy)).toThrow(reason)
  })
})
