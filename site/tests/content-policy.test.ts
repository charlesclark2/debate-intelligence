import { existsSync, readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'

import { beforeEach, describe, expect, it } from 'vitest'

import type { AnnouncementField, ContentPage, SiteSettings } from '@/lib/content'
import {
  announcementFields,
  loadGuardedContent,
  loadSiteSettings,
  parentSessionFactSchema,
  parsePage,
} from '@/lib/content'
import type { MediaConsent } from '@/lib/media-consent'
import { isStale, loadMediaConsent, seasonStart } from '@/lib/media-consent'
import {
  PublishingPolicyError,
  checkPublishingPolicy,
  enforcePublishingPolicy,
  referencedImages,
  resetPolicyReporting,
  unreviewedNames,
  withoutScripts,
} from '@/lib/publishing-policy'

/**
 * The content guard (v1-e36-t04 acceptance criterion 3).
 *
 * docs/policies/website-publishing.md is the rule book; this suite is the part of it a build can
 * check by itself, so that an address, a phone number, an unconsented photograph, a half-written
 * page or a third-party embed cannot reach prod because nobody happened to look. The consent
 * entries carry a season and a date checked, because the district's media-consent form renews
 * annually: a prod build fails on a missing entry and warns on one that predates the current
 * season, which makes a skipped start-of-season check visible without anyone remembering it.
 */

const PROD: NodeJS.ProcessEnv = { ...process.env, SITE_ENV: 'prod' }
const DEV: NodeJS.ProcessEnv = { ...process.env, SITE_ENV: 'dev' }

const settings = loadSiteSettings()
const consent = loadMediaConsent()

/** Builds a one-page site from inline Markdown, through the real loader. */
function pageFrom(markdown: string, slug = 'example'): ContentPage {
  return parsePage(
    slug,
    `content/pages/${slug}.md`,
    `---\ntitle: Example page\ndescription: An example.\n---\n\n${markdown}\n`,
  )
}

function check(markdown: string, overrides: Partial<MediaConsent> = {}) {
  return checkPublishingPolicy({
    pages: [pageFrom(markdown)],
    settings,
    consent: { ...consent, ...overrides },
  })
}

function messages(markdown: string, overrides: Partial<MediaConsent> = {}): string {
  return check(markdown, overrides)
    .errors.map((finding) => finding.message)
    .join('\n')
}

beforeEach(() => {
  resetPolicyReporting()
})

describe('email addresses', () => {
  it('accepts an address that is in the allowlist in content/site.yaml', () => {
    expect(check('Write to <charles.clark@wfbschools.org>.').errors).toEqual([])
  })

  it('rejects any other address, however plausible', () => {
    expect(messages('Write to <debate@wfbschools.org>.')).toMatch(
      /publishes the email address "debate@wfbschools\.org", which is not in the allowlist/,
    )
  })

  it('rejects a student address, which no consent can ever permit', () => {
    expect(messages('Ask <jordan.rivera@students.wfbschools.org>.')).toMatch(
      /not in the allowlist/,
    )
  })

  it('ignores a Remind group code, which is not an address', () => {
    expect(check('Join the Remind group with the code @debatewfb.').errors).toEqual([])
  })
})

describe('phone numbers', () => {
  it.each([
    ['414-963-3921'],
    ['(414) 963-3921'],
    ['414.963.3921'],
    ['+1 414 963 3921'],
  ])('rejects %s, because the site publishes none', (number) => {
    expect(messages(`Call ${number}.`)).toMatch(/looks like a phone number/)
  })

  it('does not mistake a season label, a year range or a time for a phone number', () => {
    expect(check('The 2026-27 season runs 2026-2027, and practice is at 8:00 AM.').errors).toEqual([])
  })
})

describe('images and media consent', () => {
  it('accepts an image listed as having nobody in it', () => {
    expect(check('![The team mark](/brand/wfb-mark-navy-transparent.png)').errors).toEqual([])
  })

  it('rejects an image with no entry in the manifest at all', () => {
    expect(messages('![The team at state](/photos/state-2026.jpg)')).toMatch(
      /references the image \/photos\/state-2026\.jpg, which has no entry in content\/media-consent\.yaml/,
    )
  })

  it('accepts an image with a current-season consent entry', () => {
    const images = [
      {
        path: '/photos/orientation.jpg',
        consentReference: 'MC-2026-014',
        depicts: '2 team members, both covered',
        season: consent.season,
        dateChecked: '2026-09-18',
      },
    ]
    expect(check('![Two debaters](/photos/orientation.jpg)', { images }).errors).toEqual([])
  })

  it('finds an image referenced from HTML as well as from Markdown', () => {
    expect(referencedImages('<img src="/photos/a.jpg" alt="">')).toEqual(['/photos/a.jpg'])
    expect(referencedImages('![alt](/photos/b.jpg?v=2)')).toEqual(['/photos/b.jpg'])
  })
})

describe('named students', () => {
  it('stays quiet about capitalised phrases whose words have all been reviewed', () => {
    expect(unreviewedNames('Email Coach Clark at Whitefish Bay High School.', consent.permittedNamePhrases))
      .toEqual([])
    expect(unreviewedNames('Martin Luther King Jr weekend', consent.permittedNamePhrases)).toEqual([])
  })

  it('flags a name made of words nobody has reviewed', () => {
    expect(unreviewedNames('Jordan Rivera won.', consent.permittedNamePhrases)).toEqual(['Jordan Rivera'])
  })

  /**
   * The v1-e36-t07 review's point, as a test. When the guard checked words, reviewing the schools
   * Coach Clark has coached at left Blue, Valley, West, North and Central permitted on their own,
   * anywhere on the site. A student with any of those as a name would have passed.
   */
  it('does not leave the words of a reviewed school permitted on their own', () => {
    expect(consent.permittedNamePhrases).toContain('Blue Valley West High School')
    expect(unreviewedNames('Blue Valley West High School hosted it.', consent.permittedNamePhrases))
      .toEqual([])
    for (const invented of ['Blue Rivera', 'West Valley', 'Olathe Jordan', 'Kansas Rivera']) {
      expect(
        unreviewedNames(`${invented} spoke second.`, consent.permittedNamePhrases),
        `${invented} should not be covered by the phrases behind it`,
      ).toEqual([invented])
    }
  })

  it('covers one run of capitals with several reviewed phrases end to end', () => {
    expect(unreviewedNames('Head Coach Charlie Clark answered.', consent.permittedNamePhrases))
      .toEqual([])
    expect(
      unreviewedNames('The Whitefish Bay High School Debate Team travels.', consent.permittedNamePhrases),
    ).toEqual([])
  })

  it('permits nothing from a one-word entry, because one word is never a run', () => {
    expect(consent.permittedNamePhrases).toContain('The')
    expect(unreviewedNames('The Rivera family came.', consent.permittedNamePhrases)).toEqual([
      'The Rivera',
    ])
  })

  it('reads a typographic apostrophe as the plain one the manifest is written with', () => {
    expect(unreviewedNames('Coach Clark’s room', ["Coach Clark's"])).toEqual([])
    expect(unreviewedNames('Coach Clark’s room', ['Coach Clark'])).toEqual(['Coach Clark’s'])
  })

  it('does not run a heading into the paragraph under it', () => {
    expect(unreviewedNames('## Joining\n\nDebate is open.', consent.permittedNamePhrases)).toEqual([])
  })

  it('fails the build when a named student has no consent entry', () => {
    expect(messages('Jordan Rivera reached quarterfinals.')).toMatch(
      /names "Jordan Rivera", which has no entry in content\/media-consent\.yaml/,
    )
  })

  it('passes when the student has a current-season consent entry', () => {
    const students = [
      {
        publishedName: 'Jordan Rivera',
        publishedForm: 'full-name-and-class-year' as const,
        graduationYear: 2028,
        consentReference: 'MC-2026-014',
        season: consent.season,
        dateChecked: '2026-09-18',
      },
    ]
    expect(check('Jordan Rivera reached quarterfinals.', { students }).errors).toEqual([])
  })

  it('fails when the only consent entry is from a previous season', () => {
    const students = [
      {
        publishedName: 'Jordan Rivera',
        publishedForm: 'full-name-and-class-year' as const,
        graduationYear: 2028,
        consentReference: 'MC-2025-003',
        season: '2025-26',
        dateChecked: '2025-09-12',
      },
    ]
    expect(messages('Jordan Rivera reached quarterfinals.', { students })).toMatch(
      /whose consent entry is for season 2025-26/,
    )
  })
})

describe('the start-of-season check', () => {
  it('treats a season as beginning on 1 August', () => {
    expect(seasonStart('2026-27').toISOString()).toBe('2026-08-01T00:00:00.000Z')
  })

  it('calls an entry stale when it was last checked before the season began', () => {
    expect(isStale({ season: '2026-27', dateChecked: '2026-07-31' }, '2026-27')).toBe(true)
    expect(isStale({ season: '2026-27', dateChecked: '2026-08-01' }, '2026-27')).toBe(false)
    expect(isStale({ season: '2025-26', dateChecked: '2026-09-18' }, '2026-27')).toBe(true)
  })

  it('warns, rather than failing, when an entry predates the current season', () => {
    const images = [
      {
        path: '/photos/orientation.jpg',
        consentReference: 'MC-2026-014',
        depicts: '2 team members, both covered',
        season: consent.season,
        dateChecked: '2026-07-04',
      },
    ]
    const report = check('![Two debaters](/photos/orientation.jpg)', { images })
    expect(report.errors).toEqual([])
    expect(report.warnings.map((warning) => warning.message).join('\n')).toMatch(
      /the start-of-season check for 2026-27 has not been recorded/,
    )
  })
})

describe('placeholder markers', () => {
  it('reports every unfilled placeholder with the note beside it', () => {
    expect(messages('The room is [[TBD: room for the information session]].')).toMatch(
      /still has an unfilled placeholder: room for the information session/,
    )
  })

  it('renders as a visible TBD badge so a dev preview shows the gap', () => {
    expect(pageFrom('The room is [[TBD: the room]].').html).toContain(
      '<span class="placeholder">TBD</span>',
    )
  })
})

/**
 * The announcement guard (the v1-e36-t07 review's ruling, implemented in v1-e36-t08).
 *
 * v1-e36-t06 moved the October 1 panel out of prose and into fields, and in doing so replaced the
 * [[TBD]] marker on the room with an ordinary sentence. Nothing then flagged it: a panel with no
 * room in it is a well-formed panel, and the guard reads copy, not absences. These are the checks
 * that make an unset field speak.
 */
describe('required announcement fields', () => {
  const field = (overrides: Partial<AnnouncementField> = {}): AnnouncementField => ({
    location: 'content/home.yaml',
    announcement: 'Parent information session',
    label: 'Room',
    unsetNote: 'The room is not set yet.',
    ...overrides,
  })

  function announcementErrors(announcements: AnnouncementField[]): string {
    return checkPublishingPolicy({ pages: [], settings, consent, announcements })
      .errors.map((error) => error.message)
      .join('\n')
  }

  it('fails the build while a field is unset, naming the field and the announcement', () => {
    expect(announcementErrors([field()])).toMatch(
      /the Room of the "Parent information session" announcement is still unset/,
    )
  })

  it('is quiet once the field carries a value', () => {
    expect(announcementErrors([field({ unsetNote: null })])).toBe('')
  })

  it('accepts "To be announced" as a value, because that is a decision', () => {
    const decided = parentSessionFactSchema.parse({ label: 'Room', value: 'To be announced' })
    expect(decided.unsetNote).toBeUndefined()
    expect(announcementErrors([field({ unsetNote: null })])).toBe('')
  })

  it('refuses a fact that is neither given nor declared missing', () => {
    expect(parentSessionFactSchema.safeParse({ label: 'Room' }).success).toBe(false)
    expect(
      parentSessionFactSchema.safeParse({ label: 'Room', value: 'Room 214', unsetNote: 'unknown' })
        .success,
    ).toBe(false)
  })

  it('reports a prod build failure rather than a printed note', () => {
    expect(() =>
      enforcePublishingPolicy({ pages: [], settings, consent, announcements: [field()] }, PROD),
    ).toThrowError(PublishingPolicyError)
  })

  it('lets a dev preview come up, so the gap can be reviewed on the page', () => {
    expect(() =>
      enforcePublishingPolicy({ pages: [], settings, consent, announcements: [field()] }, DEV),
    ).not.toThrow()
  })

  it('checks nothing when it is given nothing, which is what a one-page check wants', () => {
    expect(checkPublishingPolicy({ pages: [], settings, consent }).errors).toEqual([])
  })

  it('carries the October 1 panel through from content/home.yaml', () => {
    const labels = announcementFields().map((entry) => entry.label)
    expect(labels).toContain('Room')
    for (const entry of announcementFields()) {
      expect(entry.location).toBe('content/home.yaml')
    }
  })
})

describe('third-party content in the built pages', () => {
  const builtPage = (html: string) => ({
    pages: [] as ContentPage[],
    settings: settings as SiteSettings,
    consent,
    builtPages: [{ location: '/example/', html }],
  })

  it('rejects a script loaded from another origin', () => {
    const report = checkPublishingPolicy(
      builtPage('<script src="https://www.googletagmanager.com/gtag/js"></script>'),
    )
    expect(report.errors.map((error) => error.message).join('\n')).toMatch(/another origin/)
  })

  it('rejects an iframe, embedded calendar or form service', () => {
    const report = checkPublishingPolicy(
      builtPage('<iframe src="https://calendar.example.com/embed"></iframe>'),
    )
    expect(report.errors.length).toBeGreaterThan(0)
    expect(report.errors.map((error) => error.message).join('\n')).toMatch(/iframe/)
  })

  it('accepts the site’s own scripts', () => {
    expect(checkPublishingPolicy(builtPage('<script src="/_next/static/chunks/a.js"></script>')).errors)
      .toEqual([])
  })
})

describe('the build guard', () => {
  it('throws in a prod build', () => {
    expect(() =>
      enforcePublishingPolicy({ pages: [pageFrom('Call 414-963-3921.')], settings, consent }, PROD),
    ).toThrowError(PublishingPolicyError)
  })

  it('does not throw in a dev build, so a preview still comes up with the gaps visible', () => {
    expect(() =>
      enforcePublishingPolicy({ pages: [pageFrom('The room is [[TBD]].')], settings, consent }, DEV),
    ).not.toThrow()
  })
})

describe('the content this site actually ships', () => {
  // content/home.yaml, content/faq.yaml and content/events.yaml hold copy as well, so they go
  // through the guard with the Markdown pages. src/app/layout.tsx passes exactly this list at
  // build time, which is what loadGuardedContent() is for: one definition of "everything with
  // copy in it", so a new YAML content file cannot be added and quietly left unguarded.
  const pages = loadGuardedContent()

  it('breaks no rule except the facts still waiting on Charlie', () => {
    const { errors } = checkPublishingPolicy({
      pages,
      settings,
      consent,
      announcements: announcementFields(),
    })
    const stillOwed = errors.filter(
      (error) => !error.message.includes('placeholder') && !error.message.includes('still unset'),
    )
    expect(stillOwed).toEqual([])
  })

  /**
   * The one finding this task expects to see, and the reason a prod build cannot succeed until
   * Charlie supplies the room. When he does, this test says so by failing, which is the point: it
   * is the launch gate, not a tolerated warning.
   */
  it('still owes the October 1 room, which is what stops a prod build today', () => {
    const { errors } = checkPublishingPolicy({
      pages,
      settings,
      consent,
      announcements: announcementFields(),
    })
    expect(errors.map((error) => error.message).join('\n')).toMatch(
      /the Room of the "Parent information session" announcement is still unset/,
    )
  })

  it('puts every content file that carries copy through the guard', () => {
    const guarded = pages.map((page) => page.filePath)
    for (const filePath of ['content/home.yaml', 'content/faq.yaml', 'content/events.yaml']) {
      expect(guarded, `${filePath} is not checked by the publishing-policy guard`).toContain(
        filePath,
      )
    }
  })

  it('has a media-consent manifest for the current season', () => {
    expect(consent.season).toMatch(/^\d{4}-\d{2}$/)
    expect(consent.students).toEqual([])
    expect(consent.images).toEqual([])
  })

  it('names no student, so no consent entry is needed yet', () => {
    for (const page of pages) {
      expect(unreviewedNames(page.guardedHtml, consent.permittedNamePhrases), page.filePath).toEqual(
        [],
      )
    }
  })
})

describe('the built export', () => {
  const outDirectory = join(process.cwd(), 'out')
  const hasExport = existsSync(join(outDirectory, 'index.html'))
  const builtPages = hasExport
    ? readdirSync(outDirectory, { withFileTypes: true })
        .filter((entry) => entry.isDirectory() && entry.name !== '_next')
        .map((entry) => ({
          location: `/${entry.name}/`,
          path: join(outDirectory, entry.name, 'index.html'),
        }))
        .filter((entry) => existsSync(entry.path))
        .concat([{ location: '/', path: join(outDirectory, 'index.html') }])
        .map((entry) => ({ location: entry.location, html: readFileSync(entry.path, 'utf8') }))
    : []

  it.runIf(hasExport)('loads nothing from another origin and embeds no iframe', () => {
    const { errors } = checkPublishingPolicy({ pages: [], settings, consent, builtPages })
    expect(errors).toEqual([])
  })

  it.runIf(hasExport)('publishes no address outside the allowlist and no phone number', () => {
    const allowed = new Set(settings.contactEmails.map((contact) => contact.address.toLowerCase()))
    for (const page of builtPages) {
      const text = withoutScripts(page.html)
      for (const address of text.match(/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g) ?? []) {
        expect(allowed.has(address.toLowerCase()), `${page.location} publishes ${address}`).toBe(true)
      }
    }
  })
})
