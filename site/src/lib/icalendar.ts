import {
  CALENDAR_PATH,
  SCHEDULE_SLUG,
  SCHOOL_NAME,
  calendarUid,
  formatDateRange,
  nextDay,
} from './tournaments'
import type { ScheduleView, Tournament } from './tournaments'

/*
 * ---------------------------------------------------------------------------------------------
 * The calendar file parents subscribe to: /schedule.ics, generated at build time from
 * content/tournaments.yaml by src/app/schedule.ics/route.ts. RFC 5545, by hand, because what it
 * needs is small and every rule it follows is written down here:
 *
 *   - every tournament is an all-day event: DTSTART;VALUE=DATE and DTEND;VALUE=DATE, with DTEND
 *     the day AFTER the last day, because an iCalendar end date is exclusive (RFC 5545 3.6.1);
 *   - TEXT values escape backslash, semicolon, comma and newline (3.3.11);
 *   - lines longer than 75 octets are folded with CRLF and a space, counting octets of UTF-8 and
 *     never splitting a character (3.1);
 *   - every line ends in CRLF (3.1).
 *
 * The UID is the entry's id (calendarUid), so an edit to anything else updates the event a
 * subscriber already has.
 *
 * DTSTAMP is required on every event and is meant to say when the object was created. The build
 * time would satisfy that and make every rebuild of an unchanged schedule a different file, which
 * is noise for every subscriber's calendar app and makes a rebuild impossible to compare with the
 * last one byte for byte. So DTSTAMP is the `revised` date at the top of content/tournaments.yaml:
 * the day the schedule was last changed, which is the honest answer to "when was this issued",
 * and the same input gives the same file whenever it is built.
 *
 * tests/icalendar.test.ts parses the output back with ical.js, an independent parser, rather than
 * with anything written here, so a mistake in this file cannot be confirmed by its own twin.
 * ---------------------------------------------------------------------------------------------
 */

const CRLF = '\r\n'

/** The longest a content line may be, in octets, before it is folded (RFC 5545 3.1). */
export const MAX_LINE_OCTETS = 75

const encoder = new TextEncoder()

/** Escapes a TEXT value: backslash first, so the escapes it adds are not themselves escaped. */
export function escapeText(value: string): string {
  return value
    .replace(/\\/g, '\\\\')
    .replace(/;/g, '\\;')
    .replace(/,/g, '\\,')
    .replace(/\r\n|\r|\n/g, '\\n')
}

/**
 * Folds one content line into lines of at most 75 octets. A continuation line starts with a
 * single space, which counts towards its 75. Splitting is by whole characters (a JavaScript
 * string iterates by code point), so a multi-byte character is never cut in two.
 */
export function foldLine(line: string): string {
  const lines: string[] = []
  let current = ''
  let octets = 0
  for (const character of line) {
    const size = encoder.encode(character).length
    if (octets + size > MAX_LINE_OCTETS) {
      lines.push(current)
      current = ` ${character}`
      octets = 1 + size
    } else {
      current += character
      octets += size
    }
  }
  lines.push(current)
  return lines.join(CRLF)
}

/** 2026-10-10 as an iCalendar DATE: 20261010. */
function icsDate(isoDate: string): string {
  return isoDate.replace(/-/g, '')
}

/** One property line, before folding. `value` is already in the property's own format. */
function property(name: string, value: string): string {
  return `${name}:${value}`
}

/** The schedule page's own URL, for the link back from each event. */
export function schedulePageUrl(siteUrl: string): string {
  return `${siteUrl}/${SCHEDULE_SLUG}/`
}

/** The https address of the calendar file. */
export function calendarHttpsUrl(siteUrl: string): string {
  return `${siteUrl}${CALENDAR_PATH}`
}

/**
 * The same address with the webcal scheme, which tells a browser to hand it to the calendar app
 * as a subscription rather than download it once. Only the scheme changes.
 */
export function calendarWebcalUrl(siteUrl: string): string {
  return calendarHttpsUrl(siteUrl).replace(/^https?:\/\//, 'webcal://')
}

/** The place a calendar app shows, and maps: where a student physically goes. */
function location(tournament: Tournament): string | null {
  const places = tournament.arrangements
    .map((arrangement) => (arrangement.held === 'online-at-school' ? SCHOOL_NAME : arrangement.where))
    .filter((place): place is string => place !== null)
  const unique = [...new Set(places)]
  return unique.length > 0 ? unique.join('; ') : null
}

/** The event's description: the same facts the page lists, as "Label: value" lines. */
function description(tournament: Tournament, view: ScheduleView, siteUrl: string): string {
  const { labels } = view.content
  const lines = view.facts(tournament).map((fact) =>
    fact.detail === undefined
      ? `${fact.label}: ${fact.value}`
      : `${fact.label}: ${fact.value}. ${fact.detail}`,
  )
  const others = view.overlaps.get(tournament.id) ?? []
  if (others.length > 0) {
    lines.push(
      `${labels.overlap}: ${others
        .map((other) => `${other.name} (${formatDateRange(other)})`)
        .join('; ')}`,
    )
  }
  lines.push(`${labels.page}: ${schedulePageUrl(siteUrl)}#${tournament.id}`)
  return lines.join('\n')
}

/** What a calendar app's list shows. A tournament that may not happen says so in its title. */
function summary(tournament: Tournament, view: ScheduleView): string {
  return tournament.status === 'confirmed'
    ? tournament.name
    : `${view.content.status[tournament.status]}: ${tournament.name}`
}

const ICS_STATUS: Record<Tournament['status'], string> = {
  confirmed: 'CONFIRMED',
  tentative: 'TENTATIVE',
  conditional: 'TENTATIVE',
}

function eventLines(tournament: Tournament, view: ScheduleView, siteUrl: string): string[] {
  const place = location(tournament)
  return [
    'BEGIN:VEVENT',
    property('UID', escapeText(calendarUid(tournament))),
    property('DTSTAMP', `${icsDate(view.revised)}T000000Z`),
    property('DTSTART;VALUE=DATE', icsDate(tournament.start)),
    property('DTEND;VALUE=DATE', icsDate(nextDay(tournament.end))),
    property('SUMMARY', escapeText(summary(tournament, view))),
    ...(place === null ? [] : [property('LOCATION', escapeText(place))]),
    property('DESCRIPTION', escapeText(description(tournament, view, siteUrl))),
    property('STATUS', ICS_STATUS[tournament.status]),
    // An all-day tournament should not mark a parent's whole day as busy in their calendar.
    property('TRANSP', 'TRANSPARENT'),
    property('URL', `${schedulePageUrl(siteUrl)}#${tournament.id}`),
    'END:VEVENT',
  ]
}

/**
 * The whole calendar, every tournament in date order (nationals included), as the bytes the file
 * holds. `siteUrl` is the origin the build is for, with no trailing slash.
 */
export function buildScheduleCalendar(view: ScheduleView, siteUrl: string): string {
  const { calendar } = view.content
  const tournaments = [...view.seasonTournaments, ...view.nationals]
  const lines = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    property('PRODID', '-//Whitefish Bay Debate//Tournament schedule//EN'),
    'CALSCALE:GREGORIAN',
    'METHOD:PUBLISH',
    property('NAME', escapeText(calendar.name)),
    property('X-WR-CALNAME', escapeText(calendar.name)),
    property('DESCRIPTION', escapeText(calendar.description)),
    property('X-WR-CALDESC', escapeText(calendar.description)),
    // How often a subscribed app should look again (RFC 7986, and the older name Outlook reads).
    property('REFRESH-INTERVAL;VALUE=DURATION', 'P1D'),
    property('X-PUBLISHED-TTL', 'P1D'),
    ...tournaments.flatMap((tournament) => eventLines(tournament, view, siteUrl)),
    'END:VCALENDAR',
  ]
  return lines.map(foldLine).join(CRLF) + CRLF
}
