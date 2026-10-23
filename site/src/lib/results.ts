import { z } from 'zod'

import {
  ContentValidationError,
  EM_DASH,
  HOUSE_STYLE_REWRITE,
  PLACEHOLDER_PATTERN,
  RESULTS_SLUG,
  assertAcronymsAreExpanded,
  defaultContentDirectory,
  formatIssues,
  loadEventsContent,
  loadPage,
} from './content'
import type { ContentPage } from './content'
import { SEASON_PATTERN, isStale, loadMediaConsent, seasonStart } from './media-consent'
import type { ConsentedStudent, MediaConsent } from './media-consent'
import { contactDetails, unreviewedNames } from './publishing-policy'
import { isCalendarDate, loadSchedule, readYaml } from './tournaments'
import type { Tournament } from './tournaments'

export { RESULTS_SLUG }

/*
 * ---------------------------------------------------------------------------------------------
 * THE SEASON'S RESULTS: content/results.yaml (v1-e37-t06).
 *
 * One entry per placing, from which the /results/ page and the home page's three newest results
 * are built. Results are the content most likely to name a child, so the file is held to
 * docs/policies/website-publishing.md, Results and awards, by the build rather than by a reviewer:
 *
 *   - Who it names. Lincoln-Douglas names one student and a partner event both partners or
 *     neither (rule 1). A name with no consent entry at all fails the build. A name whose entry
 *     is not current for the season, or asks for less than the full name, is published in
 *     team-level form by the build itself (rule 2), so a lapsed form or a reduced-name request
 *     takes the name off every result with an edit to content/media-consent.yaml alone. Nobody
 *     writes a team-level result by hand.
 *   - What a placing is. A placing is one of a fixed set of single-tournament placings. Anything
 *     else fails the build, and a record, a win-loss line, a points total or a ranking (rule 3)
 *     or a loss (rule 4) is named as such.
 *   - Nobody else. A capitalised name in a free-text field is an opponent student as far as the
 *     build can tell (rule 5), and so is an address or a phone number (Students 6).
 *
 * Every refusal names the entry by its position and its tournament, the field and the rule, in
 * every environment: the dev preview is public too. It never repeats a student's name, because
 * a build log carries none (Students 10).
 * ---------------------------------------------------------------------------------------------
 */

export const RESULTS_FILE = 'content/results.yaml'

const POLICY = 'docs/policies/website-publishing.md'

export const DIVISIONS = ['varsity', 'junior-varsity', 'novice'] as const
export type Division = (typeof DIVISIONS)[number]

/**
 * Which events name one student and which name a partnership (Results and awards 1). An event in
 * content/events.yaml that is in neither list fails the build rather than being guessed at.
 */
export const INDIVIDUAL_EVENTS: readonly string[] = ['lincoln-douglas']
export const PARTNER_EVENTS: readonly string[] = ['policy', 'public-forum']

const ORDINALS = [
  'first',
  'second',
  'third',
  'fourth',
  'fifth',
  'sixth',
  'seventh',
  'eighth',
  'ninth',
  'tenth',
] as const

/**
 * Every placing the site publishes: a place, a speaker award, or how far the debater advanced.
 * Each one is a single placing at a single tournament. The list is closed on purpose: a free
 * text field would accept "went 5-1" as readily as "quarterfinalist".
 */
export const PLACINGS: readonly string[] = [
  ...ORDINALS.map((ordinal) => `${ordinal} place`),
  'top speaker',
  ...ORDINALS.slice(1).map((ordinal) => `${ordinal} speaker`),
  'champion',
  'finalist',
  'semifinalist',
  'quarterfinalist',
  'octofinalist',
  'double-octofinalist',
  'triple-octofinalist',
]

/** What a loss looks like written down (Results and awards 4). */
const LOSS_SHAPE =
  /\b(?:lost|loss|losses|lose|losing|eliminated|dropped|did not|didn't|went out|out in|defeated by|beaten|fell)\b/i

/**
 * What a record looks like written down (Results and awards 3): a win-loss line such as 5-1, or
 * the words that only an accumulation or a comparison uses.
 */
const RECORD_SHAPE =
  /\d+\s*[-–‐]\s*\d+|\b(?:wins?|record|undefeated|points?|speaks|average|total|ranked|ranking|rank|overall|season|bids?|leaderboard|seed|seeded|streak)\b/i

/** A student's name as the consent manifest publishes it: letters, spaces, hyphens, apostrophes. */
const NAME_SHAPE = /^\p{L}[\p{L}.'’ -]*\p{L}$/u

const calendarDate = z
  .string({ error: 'must be a date written as 2026-10-17' })
  .refine(isCalendarDate, 'must be a real date written as 2026-10-17')

const text = z.string().trim().min(1, 'must not be empty')

export const resultEntrySchema = z
  .object({
    scheduleId: text.optional(),
    tournament: text.optional(),
    date: calendarDate.optional(),
    end: calendarDate.optional(),
    event: text,
    division: z.enum(DIVISIONS, { error: `must be one of ${DIVISIONS.join(', ')}` }),
    placing: text,
    students: z.array(z.string({ error: 'must be a name' })).optional(),
  })
  .strict()
  .superRefine((entry, ctx) => {
    if (entry.scheduleId !== undefined) {
      for (const field of ['tournament', 'date', 'end'] as const) {
        if (entry[field] !== undefined) {
          ctx.addIssue({
            code: 'custom',
            path: [field],
            message:
              'goes with a tournament that is off the schedule. A result with scheduleId takes ' +
              'its name and dates from content/tournaments.yaml; use one or the other',
          })
        }
      }
      return
    }
    if (entry.tournament === undefined || entry.date === undefined) {
      ctx.addIssue({
        code: 'custom',
        path: [entry.tournament === undefined ? 'tournament' : 'date'],
        message:
          'is required: name the tournament by its scheduleId, or, once it has come off the ' +
          'schedule, by `tournament` and `date`',
      })
    }
    if (entry.date !== undefined && entry.end !== undefined && entry.end < entry.date) {
      ctx.addIssue({ code: 'custom', path: ['end'], message: `is before date (${entry.date})` })
    }
  })

export type ResultEntry = z.infer<typeof resultEntrySchema>

const labelsSchema = z
  .object({
    seasonTitle: text,
    revised: text,
    empty: text,
    individual: text,
    partners: text,
    partnersJoinedBy: text,
    divisions: z.object({ varsity: text, 'junior-varsity': text, novice: text }).strict(),
  })
  .strict()

export type ResultsLabels = z.infer<typeof labelsSchema>

const resultsFileSchema = z
  .object({
    season: z.string().regex(SEASON_PATTERN, 'must look like 2026-27'),
    revised: calendarDate,
    labels: labelsSchema,
    results: z.array(z.unknown()),
  })
  .strict()

/** The tournament a result was won at, from the schedule or as the entry names it. */
export interface ResultTournament {
  /** The anchor its group carries on the page: the schedule id, or the name and first day. */
  key: string
  name: string
  start: string
  end: string
  /** The id in content/tournaments.yaml, or null for a tournament that is off the schedule. */
  scheduleId: string | null
}

export interface PublishedResult {
  /** Where the entry is in content/results.yaml, from 1. */
  position: number
  tournament: ResultTournament
  event: string
  eventName: string
  division: Division
  divisionLabel: string
  /** The placing as the file writes it, lower case: "first place". */
  placing: string
  /** The same, as the page starts a line with it: "First place". */
  placingLabel: string
  /** Who placed: "Jordan Rivera (2028)", both partners, or the team-level words. */
  who: string
  /** True when `who` names students, false for the team-level form. */
  named: boolean
}

export interface ResultGroup {
  tournament: ResultTournament
  /** In the order content/results.yaml lists them. */
  results: PublishedResult[]
}

export interface Results {
  season: string
  revised: string
  labels: ResultsLabels
  /** Newest tournament first. */
  groups: ResultGroup[]
}

/** How an error names an entry: its position, and its tournament when that is readable. */
function describeEntry(raw: unknown, index: number): string {
  const value = typeof raw === 'object' && raw !== null ? (raw as Record<string, unknown>) : {}
  const named =
    typeof value.scheduleId === 'string'
      ? value.scheduleId
      : typeof value.tournament === 'string'
        ? [value.tournament, typeof value.date === 'string' ? value.date : null]
            .filter(Boolean)
            .join(', ')
        : null
  return named ? `result ${index + 1} (${named})` : `result ${index + 1}`
}

function entryError(entry: string, field: string, message: string): ContentValidationError {
  return new ContentValidationError(RESULTS_FILE, `${entry}, field ${field}: ${message}`)
}

function rule(section: string): string {
  return `(${POLICY}, ${section})`
}

/** "Fort Atkinson" on 2026-10-17 becomes "fort-atkinson-2026-10-17". */
function anchorFor(name: string, start: string): string {
  const words = name
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return `${words || 'tournament'}-${start}`
}

/**
 * Why a placing is refused, in the policy's words, or null for one the site publishes. A loss is
 * named before a record, so "lost 2-1" is called the loss it is.
 */
export function placingProblem(placing: string): string | null {
  const written = placing.trim().toLowerCase()
  if (PLACINGS.includes(written)) {
    return null
  }
  if (LOSS_SHAPE.test(written)) {
    return (
      `"${placing}" describes a loss. The site publishes a student's result only where they ` +
      `placed or advanced, never a loss ${rule('Results and awards 4')}.`
    )
  }
  if (RECORD_SHAPE.test(written)) {
    return (
      `"${placing}" is a record, not a placing. A result is a single placing at one ` +
      'tournament, never a win-loss line, a points total or a ranking across tournaments ' +
      `${rule('Results and awards 3')}.`
    )
  }
  return (
    `"${placing}" is not a placing this site publishes. Write one of: ${PLACINGS.join(', ')} ` +
    `${rule('Results and awards 3 and 4')}.`
  )
}

/** A student's entry is good for printing their full name this season. */
function canBeNamed(entry: ConsentedStudent, consent: MediaConsent): boolean {
  return (
    !isStale(entry, consent.season) &&
    entry.publishedForm === 'full-name-and-class-year' &&
    entry.graduationYear !== undefined
  )
}

/** The checks that apply to every free-text field a result publishes. */
function checkPublishedText(
  entry: string,
  field: string,
  value: string,
  consent: MediaConsent,
): void {
  if (value.includes(EM_DASH)) {
    throw entryError(entry, field, `uses an em dash. ${HOUSE_STYLE_REWRITE}`)
  }
  if (new RegExp(PLACEHOLDER_PATTERN.source).test(value)) {
    throw entryError(entry, field, 'holds a [[TBD]] marker. A result is a fact, or it is not published.')
  }
  if (contactDetails(value).length > 0) {
    throw entryError(
      entry,
      field,
      'holds an email address or a phone number. A result publishes no contact detail of ' +
        `anyone ${rule('Students 6')}.`,
    )
  }
  if (unreviewedNames(value, consent.permittedNamePhrases).length > 0) {
    throw entryError(
      entry,
      field,
      'holds a name the site has not been told about. No opponent student is ever named ' +
        `${rule('Results and awards 5')}, and a student on this team is named only in ` +
        '`students`. If it is a school, a tournament or a place, add the whole phrase to ' +
        'permittedNamePhrases in content/media-consent.yaml.',
    )
  }
}

/**
 * Who a result names, or the team-level words, decided by the build from the consent manifest.
 * Refuses a name that is not a name, a name with no consent entry, and a result naming the wrong
 * number of students for its event.
 */
function whoPlaced(
  entry: string,
  value: ResultEntry,
  partnerEvent: boolean,
  consent: MediaConsent,
  labels: ResultsLabels,
): { who: string; named: boolean } {
  const students = value.students ?? []
  const consentByName = new Map(
    consent.students.map((student) => [student.publishedName.toLowerCase(), student]),
  )

  students.forEach((name, index) => {
    const field = `students.${index}`
    if (contactDetails(name).length > 0) {
      throw entryError(
        entry,
        field,
        `is an email address or a phone number, not a name. A student's contact details are ` +
          `never published ${rule('Students 6')}.`,
      )
    }
    if (!NAME_SHAPE.test(name.trim())) {
      throw entryError(entry, field, 'is not a name as content/media-consent.yaml writes one.')
    }
  })

  if (new Set(students.map((name) => name.trim().toLowerCase())).size !== students.length) {
    throw entryError(entry, 'students', 'names the same student twice.')
  }
  if (!partnerEvent && students.length > 1) {
    throw entryError(
      entry,
      'students',
      `names ${students.length} students for an individual event. Lincoln-Douglas names the one ` +
        `student who placed ${rule('Results and awards 1')}.`,
    )
  }
  if (partnerEvent && students.length === 1) {
    throw entryError(
      entry,
      'students',
      'names one partner of a partnership. A partner event names both partners or neither: ' +
        'add the other partner, or leave `students` out and the team-level form is published ' +
        `${rule('Results and awards 1 and 2')}.`,
    )
  }
  if (partnerEvent && students.length > 2) {
    throw entryError(
      entry,
      'students',
      `names ${students.length} students. A partnership is two ${rule('Results and awards 1')}.`,
    )
  }

  const entries = students.map((name, index) => {
    const found = consentByName.get(name.trim().toLowerCase())
    if (!found) {
      throw entryError(
        entry,
        `students.${index}`,
        'names a student with no entry in content/media-consent.yaml. A student is named only ' +
          'with a current-season consent form confirmed with the activities office, and an ' +
          `opponent student never ${rule('Students 2; Results and awards 1, 2 and 5')}. Add the ` +
          'consent entry, or leave `students` out and the team-level form is published.',
      )
    }
    return found
  })

  const teamLevel = { who: partnerEvent ? labels.partners : labels.individual, named: false }
  if (entries.length === 0 || !entries.every((student) => canBeNamed(student, consent))) {
    return teamLevel
  }
  return {
    who: entries
      .map((student) => `${student.publishedName} (${student.graduationYear})`)
      .join(` ${labels.partnersJoinedBy} `),
    named: true,
  }
}

function capitalise(phrase: string): string {
  return phrase.charAt(0).toUpperCase() + phrase.slice(1)
}

/** Newest first: by last day, then first day, then name. */
function compareNewestFirst(left: ResultTournament, right: ResultTournament): number {
  return (
    right.end.localeCompare(left.end) ||
    right.start.localeCompare(left.start) ||
    left.name.localeCompare(right.name)
  )
}

/**
 * Validates content/results.yaml against the schedule, the events and the consent manifest, and
 * returns the results as the page prints them. The first problem found throws, naming the entry,
 * the field and the rule.
 */
export function loadResults(contentDirectory: string = defaultContentDirectory()): Results {
  const raw = readYaml(contentDirectory, 'results.yaml', RESULTS_FILE)
  const file = resultsFileSchema.safeParse(raw)
  if (!file.success) {
    throw new ContentValidationError(RESULTS_FILE, `invalid results file (${formatIssues(file.error)})`)
  }
  const { labels, season } = file.data

  if ([...labelStrings(labels), labels.partnersJoinedBy].some((value) => value.includes(EM_DASH))) {
    throw new ContentValidationError(RESULTS_FILE, `the labels use an em dash. ${HOUSE_STYLE_REWRITE}`)
  }

  const consent = loadMediaConsent(contentDirectory)
  const schedule = new Map<string, Tournament>(
    loadSchedule(contentDirectory).tournaments.map((tournament) => [tournament.id, tournament]),
  )
  const events = new Map(loadEventsContent(contentDirectory).events.map((event) => [event.id, event.name]))
  const firstDay = seasonStart(season).toISOString().slice(0, 10)
  const lastDay = `${Number(firstDay.slice(0, 4)) + 1}-07-31`

  const published = file.data.results.map((rawEntry, index): PublishedResult => {
    const entry = describeEntry(rawEntry, index)
    const parsed = resultEntrySchema.safeParse(rawEntry)
    if (!parsed.success) {
      const issue = parsed.error.issues[0]!
      const unknownKeys = issue.code === 'unrecognized_keys' ? issue.keys : []
      const where = [...issue.path, ...(unknownKeys.length > 0 ? [unknownKeys.join(', ')] : [])]
      throw entryError(
        entry,
        where.length > 0 ? where.join('.') : '(the entry)',
        unknownKeys.length > 0
          ? 'is not a field a result has. Check the spelling against the list at the top of the file.'
          : issue.message,
      )
    }
    const value = parsed.data

    let tournament: ResultTournament
    if (value.scheduleId !== undefined) {
      const scheduled = schedule.get(value.scheduleId)
      if (!scheduled) {
        throw entryError(
          entry,
          'scheduleId',
          `"${value.scheduleId}" is not a tournament in content/tournaments.yaml. A tournament ` +
            'that has come off the schedule is written with `tournament` and `date` instead.',
        )
      }
      tournament = {
        key: scheduled.id,
        name: scheduled.name,
        start: scheduled.start,
        end: scheduled.end,
        scheduleId: scheduled.id,
      }
    } else {
      const name = value.tournament!
      checkPublishedText(entry, 'tournament', name, consent)
      const start = value.date!
      tournament = { key: anchorFor(name, start), name, start, end: value.end ?? start, scheduleId: null }
    }
    for (const [field, date] of [
      ['date', tournament.start],
      ['end', tournament.end],
    ] as const) {
      if (date < firstDay || date > lastDay) {
        throw entryError(entry, field, `${date} is outside the ${season} season (${firstDay} to ${lastDay})`)
      }
    }

    const eventName = events.get(value.event)
    if (eventName === undefined) {
      throw entryError(
        entry,
        'event',
        `"${value.event}" is not an event in content/events.yaml (${[...events.keys()].join(', ')})`,
      )
    }
    const partnerEvent = PARTNER_EVENTS.includes(value.event)
    if (!partnerEvent && !INDIVIDUAL_EVENTS.includes(value.event)) {
      throw entryError(
        entry,
        'event',
        `"${value.event}" is not known to be an individual or a partner event, which decides ` +
          `who a result may name ${rule('Results and awards 1')}. Add it to src/lib/results.ts.`,
      )
    }

    checkPublishedText(entry, 'placing', value.placing, consent)
    const problem = placingProblem(value.placing)
    if (problem !== null) {
      throw entryError(entry, 'placing', problem)
    }

    const placing = value.placing.trim().toLowerCase()
    return {
      position: index + 1,
      tournament,
      event: value.event,
      eventName,
      division: value.division,
      divisionLabel: labels.divisions[value.division],
      placing,
      placingLabel: capitalise(placing),
      ...whoPlaced(entry, value, partnerEvent, consent, labels),
    }
  })

  const groups = new Map<string, ResultGroup>()
  for (const result of published) {
    const group = groups.get(result.tournament.key)
    if (group) {
      group.results.push(result)
    } else {
      groups.set(result.tournament.key, { tournament: result.tournament, results: [result] })
    }
  }

  return {
    season,
    revised: file.data.revised,
    labels,
    groups: [...groups.values()].sort((left, right) => compareNewestFirst(left.tournament, right.tournament)),
  }
}

/** The season's results, newest first, for the home page: the first `count` of them. */
export function newestResults(results: Results, count = 3): PublishedResult[] {
  return results.groups.flatMap((group) => group.results).slice(0, count)
}

const SEASON_TOKEN = '{season}'

export interface ResultsView extends Results {
  /** The season title with the season filled in: "Results from the 2026-27 season". */
  seasonTitle: string
}

/**
 * Everything the page needs. The acronym rule is applied to the page as a whole, because that
 * is where a reader meets an acronym.
 */
export function loadResultsView(contentDirectory: string = defaultContentDirectory()): ResultsView {
  const results = loadResults(contentDirectory)
  const page = loadPage(RESULTS_SLUG, contentDirectory)
  assertAcronymsAreExpanded(
    RESULTS_FILE,
    [page.title, page.html, ...resultsCopy(results)].join('\n'),
  )
  return { ...results, seasonTitle: results.labels.seasonTitle.replaceAll(SEASON_TOKEN, results.season) }
}

/** Every string the labels put on the page. */
function labelStrings(labels: ResultsLabels): string[] {
  return [
    labels.seasonTitle,
    labels.revised,
    labels.empty,
    labels.individual,
    labels.partners,
    ...Object.values(labels.divisions),
  ]
}

/** One result as a line of the page prints it, which is also how the guard reads it. */
export function resultLine(result: PublishedResult): string {
  return `${result.placingLabel}, ${result.divisionLabel} ${result.eventName}: ${result.who}`
}

function resultsCopy(results: Results): string[] {
  return [
    ...labelStrings(results.labels),
    ...results.groups.flatMap((group) => [
      group.tournament.name,
      ...group.results.map(resultLine),
    ]),
  ]
}

function guardedPage(slug: string, filePath: string, title: string, copy: string): ContentPage {
  return {
    slug,
    route: `/${RESULTS_SLUG}/`,
    filePath,
    title,
    description: title,
    navLabel: title,
    navOrder: Number.MAX_SAFE_INTEGER,
    excludeFromNavigation: true,
    draft: false,
    html: copy,
    guardedHtml: copy,
    placeholders: [],
  }
}

/**
 * The results as the layout's publishing-policy guard reads them: the labels, and every result
 * as the line the page prints, one page per result so a finding names the entry. What is
 * guarded is what is published, so a team-level result is checked in its team-level words.
 */
export function resultsGuardedContent(
  contentDirectory: string = defaultContentDirectory(),
): ContentPage[] {
  const results = loadResults(contentDirectory)
  return [
    guardedPage('results-labels', `${RESULTS_FILE}, labels`, results.labels.seasonTitle, labelStrings(results.labels).join('\n\n')),
    ...results.groups.flatMap((group) =>
      group.results.map((result) =>
        guardedPage(
          `result-${result.position}`,
          `${RESULTS_FILE}, result ${result.position} (${group.tournament.scheduleId ?? `${group.tournament.name}, ${group.tournament.start}`})`,
          group.tournament.name,
          [group.tournament.name, resultLine(result)].join('\n\n'),
        ),
      ),
    ),
  ]
}
