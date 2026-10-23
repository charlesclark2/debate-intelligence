import { beforeEach, describe, expect, it } from 'vitest'

import type { AnnouncementField, ContentPage, SiteSettings } from '@/lib/content'
import {
  announcementFields,
  loadGuardedContent,
  loadPages,
  loadSiteSettings,
  parsePage,
} from '@/lib/content'
import type { MediaConsent } from '@/lib/media-consent'
import {
  consentGuardedContent,
  consentPlaceholders,
  consentedStudentSchema,
  isStale,
  loadMediaConsent,
  seasonStart,
} from '@/lib/media-consent'
import {
  PublishingPolicyError,
  checkPublishingPolicy,
  enforcePublishingPolicy,
  referencedImages,
  resetPolicyReporting,
  unreviewedNames,
} from '@/lib/publishing-policy'
import { resultsGuardedContent } from '@/lib/results'
import { scheduleGuardedContent } from '@/lib/tournaments'

import { STUDENTS, withConsent } from './results-fixture'
import { contentWith } from './schedule-fixture'

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
    expect(check('Write to <charles.clark@wfbschools.com>.').errors).toEqual([])
  })

  it('rejects any other address, however plausible', () => {
    expect(messages('Write to <debate@wfbschools.com>.')).toMatch(
      /publishes the email address "debate@wfbschools\.com", which is not in the allowlist/,
    )
  })

  it('rejects a student address, which no consent can ever permit', () => {
    expect(messages('Ask <jordan.rivera@students.wfbschools.com>.')).toMatch(
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

/**
 * The front matter a page publishes outside its body (v1-e37-t02 review, change 1). A title is
 * the page's <h1> and its <title>, a description is the meta description a search result or a
 * shared link shows, and a navLabel is printed in the navigation. Until the review only the export
 * checks read them, and scripts/site_deploy.sh runs no checks, so a student named in a title went
 * through a clean prod build.
 */
describe("a page's title, description and navigation label", () => {
  function pageWith(frontMatter: string): ContentPage {
    return parsePage('example', 'content/pages/example.md', `---\n${frontMatter}\n---\n\nBody.\n`)
  }

  function errorsFor(page: ContentPage): string {
    return checkPublishingPolicy({ pages: [page], settings, consent })
      .errors.map((error) => `${error.location}: ${error.message}`)
      .join('\n')
  }

  it('fails on a student named in the title', () => {
    expect(errorsFor(pageWith('title: Results for Jordan Rivera\ndescription: An example.'))).toMatch(
      /content\/pages\/example\.md: names "Jordan Rivera"/,
    )
  })

  it('fails on a student named in the description', () => {
    expect(
      errorsFor(pageWith('title: Example page\ndescription: A team with Avery Chen reached quarterfinals.')),
    ).toMatch(/names "Avery Chen"/)
  })

  it('fails on a student named in the navigation label', () => {
    expect(
      errorsFor(pageWith('title: Example page\ndescription: An example.\nnavLabel: Sam Okafor')),
    ).toMatch(/names "Sam Okafor"/)
  })

  it('fails on an address or a phone number in the description', () => {
    const errors = errorsFor(
      pageWith('title: Example page\ndescription: Write to a.parent@example.com or call 414-555-0142.'),
    )
    expect(errors).toMatch(/publishes the email address "a\.parent@example\.com"/)
    expect(errors).toMatch(/looks like a phone number/)
  })

  /**
   * The titles that are written in title case pass because each one is a reviewed phrase in
   * content/media-consent.yaml, not because the guard skips titles. Take the phrase away and the
   * real page fails.
   */
  it.each([
    ['schedule', 'Tournament Schedule'],
    ['events', 'Debate Events Offered'],
  ])('passes the real %s page only because "%s" is a reviewed phrase', (slug, phrase) => {
    const page = loadPages().find((candidate) => candidate.slug === slug)!
    expect(errorsFor(page)).toBe('')
    const withoutPhrase = {
      ...consent,
      permittedNamePhrases: consent.permittedNamePhrases.filter((entry) => entry !== phrase),
    }
    const errors = checkPublishingPolicy({ pages: [page], settings, consent: withoutPhrase }).errors
    expect(errors.map((error) => error.message).join('\n')).toMatch(new RegExp(`names "${phrase}"`))
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

  /**
   * Warnings print in every build, so a lapsed student entry is named by its opaque consent
   * reference: a build log carries no student name (Students 10). Until v1-e37-t06 the warning
   * printed the name, which nothing noticed while the manifest held no student.
   */
  it('names a lapsed student entry by its consent reference, never by the name', () => {
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
    const warnings = check('Nobody is named here.', { students })
      .warnings.map((warning) => warning.message)
      .join('\n')
    expect(warnings).toMatch(/consent MC-2025-003 was last checked 2025-09-12 for season 2025-26/)
    expect(warnings).not.toMatch(/Jordan|Rivera/)
  })
})

/**
 * The manifest's own example writes `dateChecked: 2026-09-18` unquoted. The YAML parser reads
 * that as a Date, which the schema refused, so the first entry written as documented would have
 * failed the build; and it moves an impossible date such as 2026-09-31 to October 1 without a
 * word. Bare dates are now quoted before parsing, as content/tournaments.yaml's are (v1-e37-t06).
 */
describe('dates in the media-consent manifest', () => {
  it('reads an unquoted dateChecked as the date that was typed', () => {
    const directory = contentWith({ 'media-consent.yaml': withConsent([STUDENTS.jordan]) })
    const entry = loadMediaConsent(directory).students.find(
      (student) => student.consentReference === STUDENTS.jordan.consentReference,
    )
    expect(entry?.dateChecked).toBe('2026-09-18')
  })

  it('refuses a full-name entry with no graduation year to print', () => {
    const withoutYear = {
      publishedName: STUDENTS.jordan.publishedName,
      consentReference: STUDENTS.jordan.consentReference,
    }
    const directory = contentWith({ 'media-consent.yaml': withConsent([withoutYear]) })
    expect(() => loadMediaConsent(directory)).toThrow(
      /graduationYear: is required when publishedForm is full-name-and-class-year/,
    )
  })
})

/**
 * A consent reference the activities office has not supplied yet is written as a [[TBD]] marker,
 * like any other fact still owed (v1-e37-t06). A dev build prints it so the preview can be
 * reviewed with the name on it; a prod build fails until the reference is filled in. The finding
 * names the entry by position, never the student, because it prints in every build log.
 */
describe('a consent reference still to come', () => {
  const owed = { ...STUDENTS.jordan, consentReference: "'[[TBD: form reference from the office]]'" }

  it('is reported by its position and the note beside it, with no name', () => {
    const directory = contentWith({ 'media-consent.yaml': withConsent([owed]) })
    const notes = consentPlaceholders(loadMediaConsent(directory))
    expect(notes).toEqual(['form reference from the office (consentReference of student entry 1)'])
    expect(notes.join('\n')).not.toMatch(/Jordan|Rivera/)
  })

  it('fails a prod build and lets a dev preview come up', () => {
    const directory = contentWith({ 'media-consent.yaml': withConsent([owed]) })
    const input = { pages: consentGuardedContent(directory), settings, consent: loadMediaConsent(directory) }
    expect(() => enforcePublishingPolicy(input, PROD)).toThrow(
      /content\/media-consent\.yaml: still has an unfilled placeholder: form reference from the office \(consentReference of student entry 1\)/,
    )
    expect(enforcePublishingPolicy(input, DEV).errors).toHaveLength(1)
  })

  it('is quiet once the reference is filled in', () => {
    const directory = contentWith({ 'media-consent.yaml': withConsent([STUDENTS.jordan]) })
    expect(consentPlaceholders(loadMediaConsent(directory))).toEqual([])
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

  /**
   * The October 1 panel was the one announcement with required facts, and v1-e37-t02 replaced it
   * with a pointer to the tournament schedule once the session had happened. The guard above
   * stays for v1-e37-t03's announcements; until they exist there is nothing to feed it.
   */
  it('has no announcement facts to carry since the October 1 panel was replaced', () => {
    expect(announcementFields()).toEqual([])
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
  // copy in it", so a new YAML content file cannot be added and quietly left unguarded. The
  // schedule's files join it through scheduleGuardedContent(), and the results through
  // resultsGuardedContent(), which the layout passes too.
  const pages = [
    ...loadGuardedContent(),
    ...scheduleGuardedContent(),
    ...resultsGuardedContent(),
    ...consentGuardedContent(),
  ]

  /**
   * The facts still waiting on Charlie, written out so that each one is a decision to change this
   * test rather than a gap that goes quiet. On 2026-10-23 that is one: the consent reference for
   * the first student named on the site, which the activities office has not supplied. Charlie
   * confirmed the form itself is on file (2026-10-01). Until the reference is filled in, a dev
   * preview builds and a prod build fails, which is the gate this list documents.
   */
  const STILL_WAITING_ON_CHARLIE = [
    'content/media-consent.yaml: still has an unfilled placeholder: ' +
      "the 2026-27 form's reference, from the activities office (consentReference of student entry 1)",
  ]

  it('breaks no rule except the facts still waiting on Charlie', () => {
    const { errors } = checkPublishingPolicy({
      pages,
      settings,
      consent,
      announcements: announcementFields(),
    })
    expect(errors.map((error) => `${error.location}: ${error.message}`)).toEqual(
      STILL_WAITING_ON_CHARLIE,
    )
  })

  /**
   * This began life as a tripwire asserting the room was still missing, on the reasoning that it
   * should fail the day Charlie supplied it. It has now fired and been turned around: the room
   * carries "To be announced", a decision rather than a gap, and the gate this test guards is that
   * no announcement fact goes back to being silently unset.
   */
  it('leaves no announcement fact unset', () => {
    const { errors } = checkPublishingPolicy({
      pages,
      settings,
      consent,
      announcements: announcementFields(),
    })
    expect(errors.map((error) => error.message).join('\n')).not.toMatch(/still unset/)
  })

  it('puts every content file that carries copy through the guard', () => {
    const guarded = pages.map((page) => page.filePath)
    for (const filePath of [
      'content/home.yaml',
      'content/faq.yaml',
      'content/events.yaml',
      'content/schedule.yaml',
      'content/results.yaml, labels',
    ]) {
      expect(guarded, `${filePath} is not checked by the publishing-policy guard`).toContain(
        filePath,
      )
    }
    // Every tournament is guarded field by field, so a finding names the entry and the field.
    expect(guarded).toContain('content/tournaments.yaml, tournament "glenbrooks-2026" (entry 6), field notes')
  })

  it('has a media-consent manifest for the current season, with no photograph in it yet', () => {
    expect(consent.season).toMatch(/^\d{4}-\d{2}$/)
    expect(consent.images).toEqual([])
  })

  /**
   * Every student entry, checked for its shape and its season and never by who it is: the
   * names live in content/ and nowhere else, so no test names a real student (the PM's ruling
   * for v1-e37-t06, and docs/policies/website-publishing.md, Students 10 and 11). Each entry is
   * identified below by its position, never by its name, so a failure prints no name either.
   */
  describe('every student entry', () => {
    const firstDay = seasonStart(consent.season)
    const lastDay = new Date(Date.UTC(firstDay.getUTCFullYear() + 1, 6, 31))

    it.each(consent.students.map((student, index) => [index + 1, student] as const))(
      'entry %i has the manifest shape, for the current season, checked inside it',
      (_position, student) => {
        expect(consentedStudentSchema.safeParse(student).success).toBe(true)
        expect(student.season).toBe(consent.season)
        expect(isStale(student, consent.season)).toBe(false)
        expect(new Date(student.dateChecked) <= lastDay).toBe(true)
      },
    )

    it.each(consent.students.map((student, index) => [index + 1, student] as const))(
      'entry %i publishes a whole name with a plausible graduation year, and an opaque reference',
      (_position, student) => {
        expect(student.publishedName.trim().split(/\s+/).length).toBeGreaterThanOrEqual(
          student.publishedForm === 'full-name-and-class-year' ? 2 : 1,
        )
        if (student.graduationYear !== undefined) {
          const seasonEndYear = firstDay.getUTCFullYear() + 1
          expect(student.graduationYear).toBeGreaterThanOrEqual(seasonEndYear)
          expect(student.graduationYear).toBeLessThanOrEqual(seasonEndYear + 4)
        }
        // The reference points at a form; it must not carry any part of the name it stands for.
        for (const word of student.publishedName.toLowerCase().split(/\s+/)) {
          expect(student.consentReference.toLowerCase().includes(word)).toBe(false)
        }
      },
    )

    it('uses each consent reference once', () => {
      const references = consent.students.map((student) => student.consentReference)
      expect(new Set(references).size).toBe(references.length)
    })
  })

  it('names nobody but students with a current-season consent entry', () => {
    const consented = new Map(
      consent.students.map((student) => [student.publishedName.toLowerCase(), student]),
    )
    for (const page of pages) {
      for (const name of unreviewedNames(page.guardedHtml, consent.permittedNamePhrases)) {
        const entry = consented.get(name.toLowerCase())
        // The message names the file, not the name, so a failure prints no student's name.
        expect(entry, `${page.filePath} prints a name with no consent entry`).toBeDefined()
        expect(isStale(entry!, consent.season), `${page.filePath} prints a lapsed name`).toBe(false)
      }
    }
  })
})
