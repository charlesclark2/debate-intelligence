import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

import matter from 'gray-matter'
import { z } from 'zod'

import {
  ContentValidationError,
  EM_DASH,
  HOUSE_STYLE_REWRITE,
  PLACEHOLDER_PATTERN,
  SCHEDULE_SLUG,
  assertAcronymsAreExpanded,
  defaultContentDirectory,
  formatIssues,
  loadEventsContent,
  loadPage,
  loadSiteSettings,
} from './content'
import type { ContentPage } from './content'

export { SCHEDULE_SLUG }
import { SEASON_PATTERN, loadMediaConsent, seasonStart } from './media-consent'
import { checkPublishingPolicy } from './publishing-policy'

/*
 * ---------------------------------------------------------------------------------------------
 * THE TOURNAMENT SCHEDULE: content/tournaments.yaml (v1-e37-t02, ADR-0015 as accepted).
 *
 * One file holds the season, and two things are built from it: the /schedule/ page and the
 * calendar file parents subscribe to (src/lib/icalendar.ts). Nothing is fetched from anywhere.
 *
 * Four properties a parent depends on, each held here rather than left to whoever edits the file:
 *
 *   - Identity. Every entry has an explicit id, unique in the file, and the calendar UID is that
 *     id and nothing else (calendarUid). A date correction or a new note leaves the UID alone, so
 *     a subscriber's calendar updates the event it already has instead of showing a second one.
 *   - How it is held, per event. Glenbrooks debates Lincoln-Douglas and Public Forum online from
 *     the high school and Policy in person in Illinois. One field cannot say that, so an entry
 *     either describes the whole tournament in four fields or splits them by event (byEvent).
 *   - Overlaps are computed from the dates (findOverlaps), never written into the file, and both
 *     entries stay on the page. A hand-kept flag goes stale the first time a date moves.
 *   - Nothing depends on the day the site was built. Deploys are manual, so the page lists the
 *     whole season in date order whenever it was last built, and hides nothing as "past".
 *
 * Text in the file is public, so every text field goes through the publishing-policy guard, and
 * an email address, a phone number or a name nobody has reviewed fails the build in every
 * environment, naming the entry and the field. The guard's dev-build leniency exists so a preview
 * can show an unfilled [[TBD]] for review; tournament data has no placeholders to review, and the
 * dev preview is public too.
 * ---------------------------------------------------------------------------------------------
 */

export const TOURNAMENTS_FILE = 'content/tournaments.yaml'
export const SCHEDULE_CONTENT_FILE = 'content/schedule.yaml'

/** Where the calendar file is published, beside the page. See src/app/schedule.ics/route.ts. */
export const CALENDAR_PATH = '/schedule.ics'

/**
 * The right-hand side of every calendar UID. Fixed rather than read from SITE_URL: a UID that
 * followed the build's origin would change between the dev preview and prod, or on a change of
 * domain, and every subscriber would see the whole season twice.
 */
export const CALENDAR_UID_DOMAIN = 'wfbdebate.com'

export const HELD_KINDS = ['in-person', 'online-at-school', 'online-from-home'] as const
export type HeldKind = (typeof HELD_KINDS)[number]

export const OVERNIGHT_VALUES = ['no', 'yes', 'possibly'] as const
export type Overnight = (typeof OVERNIGHT_VALUES)[number]

export const TOURNAMENT_STATUSES = ['confirmed', 'tentative', 'conditional'] as const
export type TournamentStatus = (typeof TOURNAMENT_STATUSES)[number]

/** Where a tournament debated online from the high school actually puts a student. */
export const SCHOOL_NAME = 'Whitefish Bay High School'

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/

/** True for a real calendar date written as YYYY-MM-DD: 2026-02-30 is not one. */
export function isCalendarDate(text: string): boolean {
  if (!ISO_DATE.test(text)) {
    return false
  }
  const [year, month, day] = text.split('-').map(Number) as [number, number, number]
  const date = new Date(Date.UTC(year, month - 1, day))
  return (
    date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day
  )
}

/** The day after an ISO date, for the iCalendar end date, which is exclusive. */
export function nextDay(isoDate: string): string {
  const [year, month, day] = isoDate.split('-').map(Number) as [number, number, number]
  return new Date(Date.UTC(year, month - 1, day + 1)).toISOString().slice(0, 10)
}

const calendarDate = z
  .string({ error: 'must be a date written as 2026-11-21' })
  .refine(isCalendarDate, 'must be a real date written as 2026-11-21')

const entryId = z
  .string()
  .regex(
    /^[a-z][a-z0-9]*(?:-[a-z0-9]+)*-\d{4}$/,
    'must be lower case words joined by hyphens, ending in the year, such as "glenbrooks-2026"',
  )

const text = z.string().trim().min(1, 'must not be empty')

/** `overnight: false` is what a person types for "no"; it means the same thing. */
const overnight = z.preprocess(
  (value) => (typeof value === 'boolean' ? (value ? 'yes' : 'no') : value),
  z.enum(OVERNIGHT_VALUES, { error: 'must be no, yes or possibly' }),
)

const eventList = z
  .array(z.string().min(1))
  .min(1, 'must name at least one event')
  .refine((events) => new Set(events).size === events.length, 'lists the same event twice')

/** How one group of a tournament's events is held. The `where` rule depends on `held`. */
const arrangementShape = {
  events: eventList,
  held: z.enum(HELD_KINDS, { error: `must be one of ${HELD_KINDS.join(', ')}` }),
  where: text.optional(),
  overnight,
}

function checkWhere(
  arrangement: { held: HeldKind; where?: string | undefined },
  ctx: z.RefinementCtx,
  path: Array<string | number>,
): void {
  if (arrangement.held === 'in-person' && arrangement.where === undefined) {
    ctx.addIssue({
      code: 'custom',
      path: [...path, 'where'],
      message: 'an in-person tournament needs `where` (write "To be announced" if it is not known yet)',
    })
  }
  if (arrangement.held === 'online-at-school' && arrangement.where !== undefined) {
    ctx.addIssue({
      code: 'custom',
      path: [...path, 'where'],
      message: `online-at-school is debated at ${SCHOOL_NAME}, which the page says; leave \`where\` out`,
    })
  }
  if (arrangement.held === 'online-from-home' && arrangement.where !== undefined) {
    ctx.addIssue({
      code: 'custom',
      path: [...path, 'where'],
      message: 'online-from-home has no place to go to; leave `where` out',
    })
  }
}

const arrangementSchema = z.object(arrangementShape).strict()

/**
 * One tournament as content/tournaments.yaml holds it. `.strict()` so a misspelt field (`note:`,
 * `overnite:`) fails the build instead of quietly vanishing from the page.
 */
export const tournamentEntrySchema = z
  .object({
    id: entryId,
    name: text,
    start: calendarDate,
    end: calendarDate.optional(),
    events: eventList.optional(),
    held: arrangementShape.held.optional(),
    where: text.optional(),
    overnight: overnight.optional(),
    byEvent: z.array(arrangementSchema).min(2, 'byEvent is for two or more groups of events').optional(),
    status: z.enum(TOURNAMENT_STATUSES, {
      error: `must be one of ${TOURNAMENT_STATUSES.join(', ')}`,
    }),
    condition: text.optional(),
    signUpBy: calendarDate.optional(),
    notes: text.optional(),
    nationals: z.boolean().optional(),
  })
  .strict()
  .superRefine((entry, ctx) => {
    if (entry.end !== undefined && entry.end < entry.start) {
      ctx.addIssue({ code: 'custom', path: ['end'], message: `is before start (${entry.start})` })
    }
    if (entry.signUpBy !== undefined && entry.signUpBy > entry.start) {
      ctx.addIssue({
        code: 'custom',
        path: ['signUpBy'],
        message: `is after the tournament starts (${entry.start})`,
      })
    }
    if (entry.status === 'conditional' && entry.condition === undefined) {
      ctx.addIssue({
        code: 'custom',
        path: ['condition'],
        message: 'a conditional tournament needs `condition`: the sentence saying what it depends on',
      })
    }
    if (entry.status !== 'conditional' && entry.condition !== undefined) {
      ctx.addIssue({
        code: 'custom',
        path: ['condition'],
        message: `only a conditional tournament has a condition; this one is ${entry.status}`,
      })
    }

    const whole = ['events', 'held', 'where', 'overnight'] as const
    const present = whole.filter((field) => entry[field] !== undefined)
    if (entry.byEvent !== undefined) {
      for (const field of present) {
        ctx.addIssue({
          code: 'custom',
          path: [field],
          message: 'goes inside each byEvent group when byEvent is used, not beside it',
        })
      }
      entry.byEvent.forEach((group, index) => checkWhere(group, ctx, ['byEvent', index]))
      const all = entry.byEvent.flatMap((group) => group.events)
      if (new Set(all).size !== all.length) {
        ctx.addIssue({
          code: 'custom',
          path: ['byEvent'],
          message: 'names the same event in two groups; each event is held one way',
        })
      }
      return
    }
    for (const field of ['events', 'held', 'overnight'] as const) {
      if (entry[field] === undefined) {
        ctx.addIssue({
          code: 'custom',
          path: [field],
          message: 'is required (or describe each group of events under byEvent)',
        })
      }
    }
    if (entry.held !== undefined) {
      checkWhere({ held: entry.held, where: entry.where }, ctx, [])
    }
  })

export type TournamentEntry = z.infer<typeof tournamentEntrySchema>

const tournamentsFileSchema = z
  .object({
    season: z.string().regex(SEASON_PATTERN, 'must look like 2026-27'),
    revised: calendarDate,
    tournaments: z.array(z.unknown()).min(1, 'the schedule needs at least one tournament'),
  })
  .strict()

/** How one group of a tournament's events is held. A tournament has one or more. */
export interface Arrangement {
  /** Event ids from content/events.yaml, in that file's order. */
  events: string[]
  held: HeldKind
  /** Where a student goes, or null when the kind says it (online from school, or from home). */
  where: string | null
  overnight: Overnight
}

export interface Tournament {
  id: string
  /** Where the entry is in content/tournaments.yaml, from 1, so an error can point at it. */
  position: number
  name: string
  /** First day, YYYY-MM-DD. */
  start: string
  /** Last day, inclusive: the same as `start` for a one-day tournament. */
  end: string
  /** Every event offered, in content/events.yaml order. */
  events: string[]
  arrangements: Arrangement[]
  status: TournamentStatus
  condition: string | null
  signUpBy: string | null
  notes: string | null
  nationals: boolean
}

export interface Schedule {
  season: string
  /** The day content/tournaments.yaml was last changed, YYYY-MM-DD. */
  revised: string
  /** Every tournament, nationals included, in date order. */
  tournaments: Tournament[]
}

/** A date range, inclusive at both ends, as ISO dates (which compare correctly as strings). */
export interface DateRange {
  start: string
  end: string
}

/** True when two inclusive date ranges share at least one day. */
export function datesOverlap(left: DateRange, right: DateRange): boolean {
  return left.start <= right.end && right.start <= left.end
}

/**
 * For every tournament, the other tournaments on any of the same days, in date order. Computed
 * from the dates every build, so a moved date moves its marks with it, and symmetric: if A is
 * marked against B, B is marked against A. Nothing is merged or dropped; this only annotates.
 */
export function findOverlaps(tournaments: readonly Tournament[]): Map<string, Tournament[]> {
  const overlaps = new Map<string, Tournament[]>(tournaments.map((entry) => [entry.id, []]))
  for (const [index, left] of tournaments.entries()) {
    for (const right of tournaments.slice(index + 1)) {
      if (datesOverlap(left, right)) {
        overlaps.get(left.id)?.push(right)
        overlaps.get(right.id)?.push(left)
      }
    }
  }
  for (const others of overlaps.values()) {
    others.sort(compareTournaments)
  }
  return overlaps
}

/**
 * The calendar UID for an entry: its id, and only its id. Never a hash of the content, which
 * would change with every correction and leave subscribers holding the old event beside the new.
 */
export function calendarUid(tournament: Pick<Tournament, 'id'>): string {
  return `tournament-${tournament.id}@${CALENDAR_UID_DOMAIN}`
}

/** Date order: first day, then last day, then name, then id, so the order is total. */
export function compareTournaments(left: Tournament, right: Tournament): number {
  return (
    left.start.localeCompare(right.start) ||
    left.end.localeCompare(right.end) ||
    left.name.localeCompare(right.name) ||
    left.id.localeCompare(right.id)
  )
}

const MONTHS = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
] as const
const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'] as const

function dateParts(isoDate: string) {
  const [year, month, day] = isoDate.split('-').map(Number) as [number, number, number]
  const weekday = new Date(Date.UTC(year, month - 1, day)).getUTCDay()
  return { year, month: MONTHS[month - 1]!, day, weekday: WEEKDAYS[weekday]! }
}

/** "Saturday, October 10, 2026". Spelled out in full, for a parent and for a screen reader. */
export function formatDate(isoDate: string): string {
  const { year, month, day, weekday } = dateParts(isoDate)
  return `${weekday}, ${month} ${day}, ${year}`
}

/** "Friday, October 23 to Sunday, October 25, 2026", with the year once unless it changes. */
export function formatDateRange(range: DateRange): string {
  if (range.start === range.end) {
    return formatDate(range.start)
  }
  const first = dateParts(range.start)
  const last = dateParts(range.end)
  const opening = `${first.weekday}, ${first.month} ${first.day}`
  return first.year === last.year
    ? `${opening} to ${formatDate(range.end)}`
    : `${opening}, ${first.year} to ${formatDate(range.end)}`
}

/*
 * Reading the file.
 */

/**
 * The YAML parser turns an unquoted 2026-02-30 into March 2 without a word. Every bare date in
 * the file is therefore quoted before parsing, so a date reaches the schema exactly as it was
 * typed and an impossible one fails the build instead of moving.
 */
function quoteBareDates(source: string): string {
  return source.replace(/^(\s*(?:-\s+)?[A-Za-z]+:\s*)(\d{4}-\d{2}-\d{2})(\s*(?:#.*)?)$/gm, "$1'$2'$3")
}

function readYaml(contentDirectory: string, fileName: string, filePath: string): unknown {
  const absolutePath = join(contentDirectory, fileName)
  if (!existsSync(absolutePath)) {
    throw new ContentValidationError(filePath, 'file is missing')
  }
  return matter(`---\n${quoteBareDates(readFileSync(absolutePath, 'utf8'))}\n---\n`).data
}

/** How an error names an entry: its id when it has a readable one, and its position always. */
function describeEntry(raw: unknown, index: number): string {
  const id = typeof raw === 'object' && raw !== null ? (raw as { id?: unknown }).id : undefined
  return typeof id === 'string' && id.length > 0
    ? `tournament "${id}" (entry ${index + 1})`
    : `tournament entry ${index + 1}`
}

/** One problem with one field of one entry, in the words every tournament error uses. */
function entryError(entry: string, field: string, message: string): ContentValidationError {
  return new ContentValidationError(TOURNAMENTS_FILE, `${entry}, field ${field}: ${message}`)
}

function normalise(entry: TournamentEntry, position: number, eventOrder: readonly string[]): Tournament {
  const ordered = (events: string[]) =>
    [...events].sort((left, right) => eventOrder.indexOf(left) - eventOrder.indexOf(right))
  const arrangements: Arrangement[] = entry.byEvent
    ? entry.byEvent.map((group) => ({
        events: ordered(group.events),
        held: group.held,
        where: group.where ?? null,
        overnight: group.overnight,
      }))
    : [
        {
          events: ordered(entry.events ?? []),
          held: entry.held!,
          where: entry.where ?? null,
          overnight: entry.overnight!,
        },
      ]
  return {
    id: entry.id,
    position,
    name: entry.name,
    start: entry.start,
    end: entry.end ?? entry.start,
    events: ordered(arrangements.flatMap((arrangement) => arrangement.events)),
    arrangements,
    status: entry.status,
    condition: entry.condition ?? null,
    signUpBy: entry.signUpBy ?? null,
    notes: entry.notes ?? null,
    nationals: entry.nationals ?? false,
  }
}

/** Every published text field of an entry, named as the error messages name it. */
export function tournamentTextFields(tournament: Tournament): Array<{ field: string; text: string }> {
  const multiple = tournament.arrangements.length > 1
  return [
    { field: 'name', text: tournament.name },
    ...tournament.arrangements.flatMap((arrangement, index) =>
      arrangement.where === null
        ? []
        : [{ field: multiple ? `byEvent.${index}.where` : 'where', text: arrangement.where }],
    ),
    ...(tournament.condition === null ? [] : [{ field: 'condition', text: tournament.condition }]),
    ...(tournament.notes === null ? [] : [{ field: 'notes', text: tournament.notes }]),
  ]
}

/**
 * Validates content/tournaments.yaml: the shape of every entry, unique ids, known events, dates
 * inside the season, house style, and the publishing policy. The first problem found throws,
 * naming the entry and the field; a policy breach lists every finding at once.
 */
export function loadSchedule(contentDirectory: string = defaultContentDirectory()): Schedule {
  const raw = readYaml(contentDirectory, 'tournaments.yaml', TOURNAMENTS_FILE)
  const file = tournamentsFileSchema.safeParse(raw)
  if (!file.success) {
    throw new ContentValidationError(TOURNAMENTS_FILE, `invalid schedule (${formatIssues(file.error)})`)
  }

  const eventOrder = loadEventsContent(contentDirectory).events.map((event) => event.id)
  // A season runs 1 August to 31 July (docs/policies/website-publishing.md). A date outside it
  // is almost always a mistyped year, which would put a tournament in the wrong place on the page.
  const firstDay = seasonStart(file.data.season).toISOString().slice(0, 10)
  const seasonEnd = `${Number(firstDay.slice(0, 4)) + 1}-07-31`

  const seen = new Map<string, string>()
  const tournaments = file.data.tournaments.map((rawEntry, index) => {
    const entry = describeEntry(rawEntry, index)
    const parsed = tournamentEntrySchema.safeParse(rawEntry)
    if (!parsed.success) {
      const issue = parsed.error.issues[0]!
      const field = issue.path.length > 0 ? issue.path.join('.') : '(the entry)'
      throw entryError(entry, field, issue.message)
    }
    const value = parsed.data

    const earlier = seen.get(value.id)
    if (earlier !== undefined) {
      throw entryError(
        entry,
        'id',
        `"${value.id}" is already used by ${earlier}. Every entry needs its own id, and a ` +
          "published id never changes: it is how a subscriber's calendar recognises the event.",
      )
    }
    seen.set(value.id, entry)

    const groups = value.byEvent ?? [{ events: value.events ?? [] }]
    groups.forEach((group, groupIndex) => {
      for (const event of group.events) {
        if (!eventOrder.includes(event)) {
          throw entryError(
            entry,
            value.byEvent ? `byEvent.${groupIndex}.events` : 'events',
            `"${event}" is not an event in content/events.yaml (${eventOrder.join(', ')})`,
          )
        }
      }
    })

    for (const field of ['start', 'end'] as const) {
      const date = value[field]
      if (date !== undefined && (date < firstDay || date > seasonEnd)) {
        throw entryError(
          entry,
          field,
          `${date} is outside the ${file.data.season} season (${firstDay} to ${seasonEnd})`,
        )
      }
    }

    const tournament = normalise(value, index + 1, eventOrder)
    for (const { field, text: fieldText } of tournamentTextFields(tournament)) {
      if (fieldText.includes(EM_DASH)) {
        throw entryError(entry, field, `uses an em dash. ${HOUSE_STYLE_REWRITE}`)
      }
      if (new RegExp(PLACEHOLDER_PATTERN.source).test(fieldText)) {
        throw entryError(
          entry,
          field,
          'holds a [[TBD]] marker. Tournament data has no placeholders: write what is known, ' +
            'such as "To be announced".',
        )
      }
    }
    return tournament
  })

  assertTournamentsArePublishable(tournaments, contentDirectory)

  return {
    season: file.data.season,
    revised: file.data.revised,
    tournaments: [...tournaments].sort(compareTournaments),
  }
}

/**
 * Every text field of every entry, as the publishing-policy guard reads pages: one page per
 * field, so a finding says which entry and which field it is in.
 */
export function tournamentFieldPages(tournaments: readonly Tournament[]): ContentPage[] {
  return tournaments.flatMap((tournament) =>
    tournamentTextFields(tournament).map(({ field, text: fieldText }) => ({
      slug: `tournament-${tournament.id}-${field}`,
      route: `/${SCHEDULE_SLUG}/`,
      filePath: `${TOURNAMENTS_FILE}, ${describeEntry(tournament, tournament.position - 1)}, field ${field}`,
      title: tournament.name,
      description: tournament.name,
      navLabel: tournament.name,
      navOrder: Number.MAX_SAFE_INTEGER,
      excludeFromNavigation: true,
      draft: false,
      html: fieldText,
      guardedHtml: fieldText,
      placeholders: [],
    })),
  )
}

/**
 * The publishing-policy guard over the tournament data, failing in every environment. Uses the
 * same checker as every other page (src/lib/publishing-policy.ts), so an address is judged
 * against the same allowlist and a name against the same reviewed phrases.
 */
function assertTournamentsArePublishable(
  tournaments: readonly Tournament[],
  contentDirectory: string,
): void {
  const { errors } = checkPublishingPolicy({
    pages: tournamentFieldPages(tournaments),
    settings: loadSiteSettings(contentDirectory),
    consent: loadMediaConsent(contentDirectory),
  })
  if (errors.length > 0) {
    throw new ContentValidationError(
      TOURNAMENTS_FILE,
      'breaks docs/policies/website-publishing.md, and tournament data is public:\n' +
        errors.map((finding) => `  ${finding.location}: ${finding.message}`).join('\n'),
    )
  }
}

/*
 * The words around the schedule: content/schedule.yaml.
 */

const SEASON_TOKEN = '{season}'

const heldLabelsSchema = z
  .object({
    'in-person': text,
    'online-at-school': text,
    'online-from-home': text,
  })
  .strict()
  // The page must never call a tournament debated from the high school simply "online": it is
  // what decides whether a student needs a ride to school (task spec, forbidden list).
  .refine(
    (labels) => labels['online-at-school'].includes(SCHOOL_NAME),
    `the online-at-school label must say the tournament is debated at ${SCHOOL_NAME}`,
  )

export const scheduleContentSchema = z
  .object({
    subscribe: z
      .object({
        title: text,
        intro: text,
        subscribeLabel: text,
        linkLabel: text,
        steps: z.array(text).min(1),
      })
      .strict(),
    seasonTitle: text,
    seasonIntro: text,
    nationalsTitle: text,
    nationalsIntro: text,
    labels: z
      .object({
        dates: text,
        where: text,
        held: text,
        events: text,
        overnight: text,
        status: text,
        signUpBy: text,
        notes: text,
        overlap: text,
        revised: text,
        page: text,
      })
      .strict(),
    held: heldLabelsSchema,
    overnight: z.object({ no: text, yes: text, possibly: text }).strict(),
    status: z.object({ confirmed: text, tentative: text, conditional: text }).strict(),
    calendar: z.object({ name: text, description: text }).strict(),
  })
  .strict()

export type ScheduleContent = z.infer<typeof scheduleContentSchema>

/** Every string content/schedule.yaml can put on the page or in the calendar file. */
function scheduleContentStrings(content: ScheduleContent): string[] {
  return [
    content.subscribe.title,
    content.subscribe.intro,
    content.subscribe.subscribeLabel,
    content.subscribe.linkLabel,
    ...content.subscribe.steps,
    content.seasonTitle,
    content.seasonIntro,
    content.nationalsTitle,
    content.nationalsIntro,
    ...Object.values(content.labels),
    ...Object.values(content.held),
    ...Object.values(content.overnight),
    ...Object.values(content.status),
    content.calendar.name,
    content.calendar.description,
  ]
}

export function loadScheduleContent(
  contentDirectory: string = defaultContentDirectory(),
): ScheduleContent {
  const raw = readYaml(contentDirectory, 'schedule.yaml', SCHEDULE_CONTENT_FILE)
  const result = scheduleContentSchema.safeParse(raw)
  if (!result.success) {
    throw new ContentValidationError(
      SCHEDULE_CONTENT_FILE,
      `invalid schedule content (${formatIssues(result.error)})`,
    )
  }
  const strings = scheduleContentStrings(result.data)
  if (strings.some((value) => value.includes(EM_DASH))) {
    throw new ContentValidationError(SCHEDULE_CONTENT_FILE, `uses an em dash. ${HOUSE_STYLE_REWRITE}`)
  }
  return result.data
}

/** content/schedule.yaml as the publishing-policy guard sees it, beside the other YAML files. */
export function scheduleContentAsPage(
  contentDirectory: string = defaultContentDirectory(),
): ContentPage {
  const content = loadScheduleContent(contentDirectory)
  const copy = scheduleContentStrings(content).join('\n\n')
  return {
    slug: 'schedule-content',
    route: `/${SCHEDULE_SLUG}/`,
    filePath: SCHEDULE_CONTENT_FILE,
    title: content.subscribe.title,
    description: content.subscribe.title,
    navLabel: content.subscribe.title,
    navOrder: Number.MAX_SAFE_INTEGER,
    excludeFromNavigation: true,
    draft: false,
    html: copy,
    guardedHtml: copy,
    placeholders: [],
  }
}

/*
 * The page and the calendar file, described once.
 */

/** One labelled fact about a tournament, as the page lists it and the calendar file repeats it. */
export interface TournamentFact {
  key: 'where' | 'held' | 'events' | 'overnight' | 'arrangement' | 'status' | 'signUpBy' | 'notes'
  label: string
  value: string
  /** The condition, under a conditional status. Shown in full, never reduced to a badge. */
  detail?: string
}

export interface ScheduleView {
  content: ScheduleContent
  season: string
  revised: string
  /** The season title with the season filled in: "The 2026-27 season". */
  seasonTitle: string
  /** Every tournament but nationals, in date order. */
  seasonTournaments: Tournament[]
  nationals: Tournament[]
  overlaps: Map<string, Tournament[]>
  eventNames: ReadonlyMap<string, string>
  facts: (tournament: Tournament) => TournamentFact[]
}

/**
 * Everything the page and the calendar file need, from the three content files: the
 * tournaments, the words around them, and the page whose title and lead introduce them.
 *
 * The acronym rule is applied to the page as a whole, because that is where a reader meets an
 * acronym: "NSDA Nationals" in an entry is spelled out by the nationals introduction above it.
 */
export function loadScheduleView(contentDirectory: string = defaultContentDirectory()): ScheduleView {
  const schedule = loadSchedule(contentDirectory)
  const content = loadScheduleContent(contentDirectory)
  const events = loadEventsContent(contentDirectory).events
  const eventNames = new Map(events.map((event) => [event.id, event.name]))
  const page = loadPage(SCHEDULE_SLUG, contentDirectory)

  assertAcronymsAreExpanded(
    `${TOURNAMENTS_FILE} with ${SCHEDULE_CONTENT_FILE}`,
    [
      page.title,
      page.html,
      ...scheduleContentStrings(content),
      ...schedule.tournaments.flatMap((tournament) =>
        tournamentTextFields(tournament).map((field) => field.text),
      ),
    ].join('\n'),
  )

  const names = (ids: string[]) => ids.map((id) => eventNames.get(id) ?? id).join(', ')
  const placeAndKind = (arrangement: Arrangement) =>
    arrangement.where === null
      ? content.held[arrangement.held]
      : `${content.held[arrangement.held]}, ${arrangement.where}`

  const facts = (tournament: Tournament): TournamentFact[] => {
    const { labels } = content
    const [only] = tournament.arrangements
    const howHeld: TournamentFact[] =
      tournament.arrangements.length === 1 && only
        ? [
            ...(only.where === null ? [] : [{ key: 'where' as const, label: labels.where, value: only.where }]),
            { key: 'held', label: labels.held, value: content.held[only.held] },
            { key: 'events', label: labels.events, value: names(tournament.events) },
            { key: 'overnight', label: labels.overnight, value: content.overnight[only.overnight] },
          ]
        : [
            { key: 'events', label: labels.events, value: names(tournament.events) },
            ...tournament.arrangements.map((arrangement) => ({
              key: 'arrangement' as const,
              label: names(arrangement.events),
              value:
                `${placeAndKind(arrangement)}. ` +
                `${labels.overnight}: ${content.overnight[arrangement.overnight]}.`,
            })),
          ]
    return [
      ...howHeld,
      {
        key: 'status',
        label: labels.status,
        value: content.status[tournament.status],
        ...(tournament.condition === null ? {} : { detail: tournament.condition }),
      },
      ...(tournament.signUpBy === null
        ? []
        : [{ key: 'signUpBy' as const, label: labels.signUpBy, value: formatDate(tournament.signUpBy) }]),
      ...(tournament.notes === null
        ? []
        : [{ key: 'notes' as const, label: labels.notes, value: tournament.notes }]),
    ]
  }

  return {
    content,
    season: schedule.season,
    revised: schedule.revised,
    seasonTitle: content.seasonTitle.replaceAll(SEASON_TOKEN, schedule.season),
    seasonTournaments: schedule.tournaments.filter((tournament) => !tournament.nationals),
    nationals: schedule.tournaments.filter((tournament) => tournament.nationals),
    overlaps: findOverlaps(schedule.tournaments),
    eventNames,
    facts,
  }
}

/**
 * The schedule's copy as the layout's publishing-policy guard reads it: the words in
 * content/schedule.yaml, and every text field of every tournament. loadSchedule() already refuses
 * a tournament that breaks the policy, in every environment; passing the fields to the layout's
 * guard as well keeps "everything published is in the guard's list" true without exceptions.
 *
 * It sits beside loadGuardedContent() in src/lib/content.ts rather than inside it because
 * content.ts cannot import this module without a cycle, and src/app/layout.tsx and
 * tests/content-policy.test.ts pass both.
 */
export function scheduleGuardedContent(
  contentDirectory: string = defaultContentDirectory(),
): ContentPage[] {
  return [
    scheduleContentAsPage(contentDirectory),
    ...tournamentFieldPages(loadSchedule(contentDirectory).tournaments),
  ]
}
