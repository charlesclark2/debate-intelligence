import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

import ICAL from 'ical.js'
import { describe, expect, it } from 'vitest'

import { SCHEDULE_SLUG, loadPages, loadSiteSettings } from '@/lib/content'
import { loadMediaConsent } from '@/lib/media-consent'
import { checkPublishingPolicy } from '@/lib/publishing-policy'
import { readSiteUrl } from '@/lib/site-settings'
import { CALENDAR_PATH, loadSchedule } from '@/lib/tournaments'

import { builtPageFiles, exportDirectory, exportedPagePath, readExported } from './built-export'

/**
 * The tournament schedule as the build wrote it (v1-e37-t02 acceptance criteria 2, 3 and 5): the
 * page, the calendar file beside it, and the links between them, with the SITE_URL this export
 * was built for. tests/schedule.test.tsx and tests/icalendar.test.ts check the same things from
 * the sources; these read the files CloudFront serves.
 */

const calendarFile = CALENDAR_PATH.replace(/^\//, '')

describe('the exported schedule', () => {
  it('writes /schedule/ and the calendar file beside it', () => {
    expect(existsSync(exportedPagePath(SCHEDULE_SLUG))).toBe(true)
    expect(existsSync(join(exportDirectory, calendarFile))).toBe(true)
  })

  it('is one of the built pages the accessibility and content-policy passes read', () => {
    // tests/export/pages-a11y.export-test.ts sweeps loadPages(); content-policy.export-test.ts
    // sweeps builtPageFiles(). Asserted so /schedule/ cannot fall out of either sweep unnoticed.
    expect(loadPages().map((page) => page.slug)).toContain(SCHEDULE_SLUG)
    expect(builtPageFiles().map((page) => page.location)).toContain(`/${SCHEDULE_SLUG}/`)
  })

  it('links to the calendar as webcal:// and as https, for the origin it was built for', () => {
    const html = readFileSync(exportedPagePath(SCHEDULE_SLUG), 'utf8')
    const https = `${readSiteUrl()}${CALENDAR_PATH}`
    const webcal = https.replace(/^https?:\/\//, 'webcal://')
    expect(html).toContain(`href="${webcal}"`)
    expect(html).toContain(`href="${https}"`)
  })

  it('lists every tournament on the page, marked as the sources say', () => {
    const html = readFileSync(exportedPagePath(SCHEDULE_SLUG), 'utf8')
    for (const tournament of loadSchedule().tournaments) {
      expect(html, tournament.id).toContain(`id="${tournament.id}"`)
    }
    expect(html.match(/class="schedule-entry__overlap"/g)).toHaveLength(8)
  })
})

describe('the exported calendar file', () => {
  const ics = readExported(calendarFile)
  const calendar = new ICAL.Component(ICAL.parse(ics))
  const events = calendar.getAllSubcomponents('vevent').map((component) => new ICAL.Event(component))

  it('parses, with one all-day event per tournament', () => {
    expect(events).toHaveLength(loadSchedule().tournaments.length)
    for (const event of events) {
      expect(event.startDate.isDate, event.summary).toBe(true)
      expect(event.endDate.isDate, event.summary).toBe(true)
    }
  })

  it('uses CRLF line endings throughout', () => {
    expect(ics.replace(/\r\n/g, '')).not.toMatch(/[\r\n]/)
  })

  it('links back to the schedule page on the origin it was built for', () => {
    for (const event of events) {
      expect(event.component.getFirstPropertyValue('url')).toMatch(
        new RegExp(`^${readSiteUrl().replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}/schedule/#`),
      )
    }
  })

  it('publishes nothing the publishing policy forbids', () => {
    // One fact per paragraph, as the page sets them apart: the description's lines are separate
    // facts ("Where: ...", "How it is held: ..."), and read as one run the guard would take the
    // last word of one and the label of the next for a two-word name.
    const text = events
      .flatMap((event) => [event.summary, event.location ?? '', ...event.description.split('\n')])
      .join('\n\n')
    const { errors } = checkPublishingPolicy({
      pages: [],
      settings: loadSiteSettings(),
      consent: loadMediaConsent(),
      builtPages: [{ location: CALENDAR_PATH, html: text }],
    })
    expect(errors).toEqual([])
  })
})
