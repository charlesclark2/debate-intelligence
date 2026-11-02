import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'

import { render, screen, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import HomePage from '@/app/page'
import NewsRoute, { generateMetadata, generateStaticParams } from '@/app/news/[[...slug]]/page'
import sitemap from '@/app/sitemap'
import { SiteFrame } from '@/components/SiteFrame'
import {
  ANNOUNCEMENTS_DIRECTORY,
  NEWS_SLUG,
  announcementsGuardedContent,
  calendarDateIn,
  checkAnnouncements,
  homeAnnouncements,
  isPublished,
  loadAnnouncements,
  loadNewsLabels,
  loadPublishedAnnouncements,
  publishedAnnouncements,
  readBuildDate,
  slugFor,
} from '@/lib/announcements'
import { COMPOSED_SLUGS, buildNavigation, loadHomeContent, loadPage, loadSiteSettings } from '@/lib/content'
import { loadMediaConsent } from '@/lib/media-consent'
import {
  PublishingPolicyError,
  describeFinding,
  enforcePublishingPolicy,
  resetPolicyReporting,
} from '@/lib/publishing-policy'

import { announcementsContent, announcementsSiteRoot, validAnnouncement } from './announcements-fixture'
import { describeViolations, findAccessibilityViolations } from './axe'
import { STUDENTS } from './content-fixture'
import { TEST_BUILD_DATE } from './build-date'

/**
 * Announcements (v1-e37-t03): one Markdown file each in content/announcements/, on the home page,
 * on /news/ and on a page of their own.
 *
 * The expected pages below are written by hand from tests/fixtures/announcements/season/, whose
 * files are named for their dates. Every test builds as of TEST_BUILD_DATE, 2026-11-02, set in
 * tests/setup.ts from tests/build-date.ts, unless it stubs another day: no test reads the clock. At 2026-11-02 that set is:
 *
 *   2026-09-08-welcome-back        pinned                       published
 *   2026-10-05-fall-banquet        pinned, expired 2026-10-20   hidden, although pinned
 *   2026-10-12-practice-moves                                   published
 *   2026-10-19-novice-packets      expires 2026-11-02           published through its last day
 *   2026-10-26-parent-meeting      with an image                published
 *   2026-10-29-tournament-forms    pinned                       published
 *   2026-11-01-snow-day            expired 2026-11-01           hidden from the day after
 *   2026-11-02-food-drive          dated the build date         published
 *   2026-11-09-winter-showcase     dated next week              not yet published
 */

afterEach(() => {
  vi.restoreAllMocks()
  resetPolicyReporting()
})

const SEASON = 'season'

const PUBLISHED_ON_THE_BUILD_DATE = [
  '2026-11-02-food-drive',
  '2026-10-29-tournament-forms',
  '2026-10-26-parent-meeting',
  '2026-10-19-novice-packets',
  '2026-10-12-practice-moves',
  '2026-09-08-welcome-back',
]

/** Pinned first, newest first, then the three newest that are not pinned. */
const ON_THE_HOME_PAGE = [
  '2026-10-29-tournament-forms',
  '2026-09-08-welcome-back',
  '2026-11-02-food-drive',
  '2026-10-26-parent-meeting',
  '2026-10-19-novice-packets',
]

const NEVER_PUBLISHED_ON_THE_BUILD_DATE = [
  '2026-10-05-fall-banquet',
  '2026-11-01-snow-day',
  '2026-11-09-winter-showcase',
]

/** An environment for one call: this process's, with these settings. An empty one is unset. */
const environment = (settings: Record<string, string>): NodeJS.ProcessEnv => ({ ...process.env, ...settings })

const slugs = (announcements: ReadonlyArray<{ slug: string }>) => announcements.map((item) => item.slug)

function useSiteRoot(files: Parameters<typeof announcementsSiteRoot>[0] = SEASON): void {
  vi.spyOn(process, 'cwd').mockReturnValue(announcementsSiteRoot(files))
}

function renderInFrame(content: ReactNode) {
  const navigation = buildNavigation()
  return render(
    <SiteFrame items={navigation.primary} strings={loadSiteSettings()} utilityLinks={navigation.utility}>
      {content}
    </SiteFrame>,
    { container: document.body },
  )
}

async function newsRoute(slug?: string): Promise<ReactNode> {
  return NewsRoute({ params: Promise.resolve(slug === undefined ? {} : { slug: [slug] }) })
}

describe('the build date', () => {
  it('is pinned for every test by tests/setup.ts, so no test reads the clock', () => {
    expect(readBuildDate()).toBe(TEST_BUILD_DATE)
  })

  it('is SITE_BUILD_DATE when it is set', () => {
    expect(readBuildDate(environment({ SITE_BUILD_DATE: '2027-01-15' }), () => new Date(Date.UTC(2026, 0, 1)))).toBe('2027-01-15')
  })

  it('refuses a SITE_BUILD_DATE that is not a real date', () => {
    expect(() => readBuildDate(environment({ SITE_BUILD_DATE: '2026-02-30' }))).toThrow(/SITE_BUILD_DATE is "2026-02-30"/)
  })

  it('is otherwise the day in America/Chicago, from the instant it is given', () => {
    // 04:30 UTC on 3 November is 22:30 on 2 November in Chicago, after the clocks went back.
    expect(readBuildDate(environment({ SITE_BUILD_DATE: '' }), () => new Date('2026-11-03T04:30:00Z'))).toBe('2026-11-02')
    expect(readBuildDate(environment({ SITE_BUILD_DATE: '' }), () => new Date('2026-11-03T06:30:00Z'))).toBe('2026-11-03')
    // In summer Chicago is five hours behind: 04:30 UTC on 1 July is still 30 June there.
    expect(calendarDateIn('America/Chicago', new Date('2026-07-01T04:30:00Z'))).toBe('2026-06-30')
  })
})

describe('which announcements are published', () => {
  const all = () => loadAnnouncements(announcementsContent(SEASON))

  it('lists every published one newest first on the build date, for /news/', () => {
    expect(slugs(publishedAnnouncements(all(), TEST_BUILD_DATE))).toEqual(PUBLISHED_ON_THE_BUILD_DATE)
  })

  it('puts every pinned one first, newest first, then the three newest that are not pinned, on the home page', () => {
    expect(slugs(homeAnnouncements(publishedAnnouncements(all(), TEST_BUILD_DATE)))).toEqual(ON_THE_HOME_PAGE)
  })

  it('shows an item expiring on a date through that date, and drops it from the first build after it', () => {
    const packets = all().find((item) => item.slug === '2026-10-19-novice-packets')!
    expect(isPublished(packets, '2026-11-02')).toBe(true)
    expect(isPublished(packets, '2026-11-03')).toBe(false)
    expect(slugs(publishedAnnouncements(all(), '2026-11-03'))).toEqual([
      '2026-11-02-food-drive',
      '2026-10-29-tournament-forms',
      '2026-10-26-parent-meeting',
      '2026-10-12-practice-moves',
      '2026-09-08-welcome-back',
    ])
    // A pinned place on the home page does not count toward the three, so a fourth comes up.
    expect(slugs(homeAnnouncements(publishedAnnouncements(all(), '2026-11-03')))).toEqual([
      '2026-10-29-tournament-forms',
      '2026-09-08-welcome-back',
      '2026-11-02-food-drive',
      '2026-10-26-parent-meeting',
      '2026-10-12-practice-moves',
    ])
  })

  it('hides an expired item even when it is pinned, and one dated after the build date', () => {
    const published = slugs(publishedAnnouncements(all(), TEST_BUILD_DATE))
    for (const slug of NEVER_PUBLISHED_ON_THE_BUILD_DATE) {
      expect(published).not.toContain(slug)
    }
  })

  it('publishes an item from its own date, at the first build on or after it', () => {
    expect(slugs(publishedAnnouncements(all(), '2026-11-09'))[0]).toBe('2026-11-09-winter-showcase')
    expect(slugs(publishedAnnouncements(all(), '2026-11-08'))).not.toContain('2026-11-09-winter-showcase')
  })

  it('reads the build date for the pages', () => {
    vi.stubEnv('SITE_BUILD_DATE', '2026-11-03')
    expect(slugs(loadPublishedAnnouncements(announcementsContent(SEASON)))).not.toContain('2026-10-19-novice-packets')
  })
})

describe('an announcement as it is read', () => {
  const item = (slug: string) => loadAnnouncements(announcementsContent(SEASON)).find((candidate) => candidate.slug === slug)!

  it('takes every field from its file, and its address from the file name', () => {
    expect(item('2026-10-26-parent-meeting')).toMatchObject({
      slug: '2026-10-26-parent-meeting',
      route: '/news/2026-10-26-parent-meeting/',
      filePath: 'content/announcements/2026-10-26-parent-meeting.md',
      title: 'Parent meeting next week',
      date: '2026-10-26',
      expires: null,
      pinned: false,
      image: { path: '/brand/wfb-mark-navy-transparent.png', alt: "The team's mark in navy" },
      summary: 'Families are invited to a short meeting about travel for the rest of the season.',
      placeholders: [],
    })
  })

  it('renders the body through the Markdown path every page uses', () => {
    expect(item('2026-10-26-parent-meeting').html).toBe(
      '<p>Families are invited to a short meeting about travel for the rest of the season.</p>\n' +
        '<p>Bring your questions about rides and overnight tournaments.</p>\n',
    )
  })

  it('reads the same file twice in one build, as the layout, the pages and the sitemap each do', () => {
    const directory = announcementsContent(SEASON)
    expect(slugs(loadAnnouncements(directory))).toEqual(slugs(loadAnnouncements(directory)))
  })

  it('cuts a long opening paragraph into a summary at a word', () => {
    const long = `${'Practice is in the library after school. '.repeat(6)}Bring a pen.`
    const [announcement] = loadAnnouncements(announcementsContent({ 'long.md': validAnnouncement({}, long) }))
    expect(announcement!.summary.length).toBeLessThanOrEqual(163)
    expect(announcement!.summary).toBe(
      'Practice is in the library after school. Practice is in the library after school. Practice ' +
        'is in the library after school. Practice is in the library after...',
    )
  })
})

describe('the file name is the address', () => {
  it('is the file name in lower case, with every other run of characters one hyphen', () => {
    expect(slugFor('2026-11-03-novice-orientation.md')).toBe('2026-11-03-novice-orientation')
    expect(slugFor('Novice Orientation.md')).toBe('novice-orientation')
    expect(slugFor('café_night!.md')).toBe('cafe-night')
  })

  it('refuses two files that come to one address, naming both, and publishes neither', () => {
    const check = checkAnnouncements(
      announcementsContent({
        'novice-orientation.md': validAnnouncement(),
        'Novice Orientation.md': validAnnouncement({ title: 'Orientation again' }),
        'other.md': validAnnouncement({ title: 'Something else' }),
      }),
    )
    expect(check.problems.map(describeFinding)).toEqual([
      'content/announcements: content/announcements/Novice Orientation.md and ' +
        'content/announcements/novice-orientation.md would both publish at /news/novice-orientation/, ' +
        "because a file's name is its address. Rename one of them",
    ])
    expect(slugs(check.announcements)).toEqual(['other'])
  })

  it('refuses a file name with no letters or digits in it', () => {
    expect(checkAnnouncements(announcementsContent({ '---.md': validAnnouncement() })).problems[0]!.message).toMatch(
      /has a name with no letters or digits in it/,
    )
  })

  it("refuses a file name carrying a consented student's name, without repeating it", () => {
    const check = checkAnnouncements(
      announcementsContent({ 'congratulations-jordan-rivera.md': validAnnouncement() }),
    )
    expect(STUDENTS.jordan.publishedName).toBe('Jordan Rivera')
    const printed = check.problems.map(describeFinding).join('\n')
    expect(printed).toMatch(/content\/announcements, file 1 in alphabetical order: has a file name containing a student's name/)
    expect(printed).toMatch(/Students 10\)$/)
    expect(printed.toLowerCase()).not.toContain('jordan')
    expect(printed.toLowerCase()).not.toContain('rivera')
  })

  it('refuses a file that is not Markdown, and skips the README that explains the folder', () => {
    const check = checkAnnouncements(
      announcementsContent({
        'README.md': '# Announcements\n\nThis file explains the folder.\n',
        'notes.txt': 'not an announcement',
        'valid.md': validAnnouncement(),
      }),
    )
    expect(check.problems.map(describeFinding)).toEqual([
      'content/announcements/notes.txt: is not an announcement file. Each announcement is one ' +
        'Markdown file directly in this folder, with a name ending in .md',
    ])
    expect(slugs(check.announcements)).toEqual(['valid'])
  })

  it('reads a missing folder as no announcements', () => {
    const directory = announcementsContent({})
    expect(loadAnnouncements(directory)).toEqual([])
  })
})

describe('the front matter', () => {
  const problem = (source: string) =>
    checkAnnouncements(announcementsContent({ 'item.md': source })).problems.map(describeFinding).join('\n')

  it.each([
    ['a missing title', '---\ndate: 2026-10-20\n---\n\nBody.\n', /front matter title: must be text/],
    ['a date that does not exist', validAnnouncement({ date: '2026-02-30' }), /front matter date: must be a real date/],
    ['an expiry before the date', validAnnouncement({ expires: '2026-10-19' }), /front matter expires: is before date \(2026-10-20\)/],
    ['a misspelt field', validAnnouncement({ expiry: '2026-11-01' }), /front matter field expiry is not a field an announcement has/],
    ['a pin that is not true or false', validAnnouncement({ pinned: 'please' }), /front matter pinned: must be true or false/],
    ['an image with no alt text', validAnnouncement({ image: '/brand/wfb-mark-navy-transparent.png' }), /front matter alt: is required with image/],
    ['alt text with no image', validAnnouncement({ alt: 'The team mark' }), /front matter alt: goes with image/],
    ['an image from another site', validAnnouncement({ image: 'https://images.example.com/a.jpg', alt: 'A trophy' }), /front matter image: must be a path on this site/],
    ['no body', validAnnouncement({}, ''), /has no body/],
  ])('refuses %s, naming the file', (_case, source, reason) => {
    expect(problem(source)).toMatch(reason)
    expect(problem(source)).toMatch(/^content\/announcements\/item\.md: /)
  })

  it('reads an unquoted date as the date that was typed', () => {
    const [announcement] = loadAnnouncements(announcementsContent({ 'item.md': validAnnouncement({ date: '2026-10-20', expires: '2026-10-31' }) }))
    expect(announcement).toMatchObject({ date: '2026-10-20', expires: '2026-10-31' })
  })
})

describe('the house style', () => {
  const problem = (source: string) =>
    checkAnnouncements(announcementsContent({ 'item.md': source })).problems.map(describeFinding).join('\n')

  it('refuses an em dash in the body, naming the line', () => {
    expect(problem(validAnnouncement({}, 'Practice is on—in the library.'))).toMatch(
      /item\.md: line 6 uses an em dash/,
    )
  })

  it('refuses an em dash in the title', () => {
    expect(problem(validAnnouncement({ title: 'Practice—on as usual' }))).toMatch(/the title uses an em dash/)
  })

  it('refuses an acronym that is not spelled out', () => {
    expect(problem(validAnnouncement({}, 'The PF teams meet on Tuesday.'))).toMatch(/uses "PF" without spelling it out/)
  })
})

/**
 * Acceptance criteria 3 and 6: each file in tests/fixtures/announcements/refused/ breaks one rule,
 * and the build names the file and the rule in docs/policies/website-publishing.md. valid.md, in
 * the same folder, still publishes. Every name in them is invented.
 */
describe('the publishing-policy rules', () => {
  const check = () => checkAnnouncements(announcementsContent('refused'))
  const printedFor = (file: string) =>
    check()
      .problems.filter((problem) => problem.location === `${ANNOUNCEMENTS_DIRECTORY}/${file}`)
      .map(describeFinding)

  it.each([
    ['student-name.md', 'a student name with no consent entry', /names "Rowan Ellery", which has no entry in content\/media-consent\.yaml.*\(docs\/policies\/website-publishing\.md, Students 1 and 2\)$/],
    ['email-address.md', 'an email address', /publishes the email address "travel\.volunteer@example\.com".*\(docs\/policies\/website-publishing\.md, Students 6\)$/],
    ['phone-number.md', 'a phone number', /publishes what looks like a phone number \("414-555-0142"\).*\(docs\/policies\/website-publishing\.md, Students 6\)$/],
    ['script.md', 'a script', /contains a script \(<script>.*\(docs\/policies\/website-publishing\.md, Analytics and third parties 1 and 5\)$/],
    ['iframe.md', 'an iframe', /contains an embed \(<iframe src="https:\/\/calendar\.example\.com\/embed">.*\(docs\/policies\/website-publishing\.md, Analytics and third parties 4 and 6\)$/],
    ['raw-html.md', 'any other HTML', /contains raw HTML \(<div class="banner">.*refused rather than stripped.*\(docs\/policies\/website-publishing\.md, Analytics and third parties 5 and 6\)$/],
    ['script-link.md', 'a link that runs code', /links to "javascript:alert\(1\)".*\(docs\/policies\/website-publishing\.md, Analytics and third parties 1 and 5\)$/],
    ['image-from-another-site.md', 'an image from another site', /shows the image "https:\/\/images\.example\.com\/trophy\.jpg" from another site.*\(docs\/policies\/website-publishing\.md, Analytics and third parties 5\)$/],
    ['image-without-consent.md', 'an image with no media-consent entry', /references the image \/photos\/fixture-team-photo\.jpg, which has no entry in content\/media-consent\.yaml.*\(docs\/policies\/website-publishing\.md, Photos and media consent 4\)$/],
  ])('refuses %s: %s, naming the file and the rule', (file, _rule, reason) => {
    const printed = printedFor(file)
    expect(printed).toHaveLength(1)
    expect(printed[0]).toMatch(new RegExp(`^content/announcements/${file.replace('.', '\\.')}: `))
    expect(printed[0]).toMatch(reason)
  })

  it('refuses a name in an image alt text or caption with the message it gets in body copy', () => {
    const inBody = check().problems.find((problem) => problem.location.endsWith('/student-name.md'))!
    for (const file of ['name-in-alt-text.md', 'name-in-caption.md']) {
      const found = check().problems.filter((problem) => problem.location.endsWith(`/${file}`))
      expect(found.map((problem) => [problem.message, problem.rule])).toEqual([[inBody.message, inBody.rule]])
    }
  })

  it('still publishes the valid item beside them', () => {
    expect(slugs(check().announcements)).toEqual(['valid'])
  })

  it('fails the build, in every environment, naming every file and rule', () => {
    const directory = announcementsContent('refused')
    expect(() => loadAnnouncements(directory)).toThrow(/^content\/announcements: cannot be published:\n/)
    let message = ''
    try {
      loadAnnouncements(directory)
    } catch (error) {
      message = (error as Error).message
    }
    for (const file of readdirSync(join(process.cwd(), 'tests/fixtures/announcements/refused'))) {
      if (file !== 'valid.md') {
        expect(message).toContain(`content/announcements/${file}: `)
      }
    }
    expect(message).not.toContain('valid.md')
  })

  it('publishes an image with a current consent entry, or a line saying nobody is in it', () => {
    const directory = announcementsContent(SEASON)
    expect(loadMediaConsent(directory).nonPersonImages.map((image) => image.path)).toContain(
      '/brand/wfb-mark-navy-transparent.png',
    )
    expect(loadAnnouncements(directory).find((item) => item.image)?.slug).toBe('2026-10-26-parent-meeting')
  })

  it('names a consented student only against a current-season entry, as every page does', () => {
    const named = validAnnouncement({}, `Congratulations to ${STUDENTS.jordan.publishedName} (2028).`)
    expect(checkAnnouncements(announcementsContent({ 'item.md': named })).problems).toEqual([])
    const lapsed = validAnnouncement({}, `Congratulations to ${STUDENTS.lapsed.publishedName} (2027).`)
    expect(checkAnnouncements(announcementsContent({ 'item.md': lapsed })).problems.map(describeFinding).join('\n')).toMatch(
      /whose consent entry is for season 2025-26/,
    )
  })
})

/**
 * A fact still owed is a [[TBD]] marker, as on every page: the gap badge in a dev preview, and a
 * failed prod build from the layout's guard, which reads announcementsGuardedContent().
 */
describe('a [[TBD]] marker in an announcement', () => {
  const directory = () =>
    announcementsContent({ 'item.md': validAnnouncement({}, 'Practice is in room [[TBD: room number]].') })
  const guardInput = (content: string) => ({
    pages: announcementsGuardedContent(content),
    settings: loadSiteSettings(content),
    consent: loadMediaConsent(content),
  })

  it('shows as the gap badge', () => {
    expect(loadAnnouncements(directory())[0]!.html).toContain('<span class="placeholder">TBD</span>')
  })

  it('fails a prod build and lets a dev preview come up', () => {
    const content = directory()
    expect(() => enforcePublishingPolicy(guardInput(content), environment({ SITE_ENV: 'prod' }))).toThrow(PublishingPolicyError)
    expect(() => enforcePublishingPolicy(guardInput(content), environment({ SITE_ENV: 'prod' }))).toThrow(
      /content\/announcements\/item\.md: still has an unfilled placeholder: room number/,
    )
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    expect(() => enforcePublishingPolicy(guardInput(content), environment({ SITE_ENV: 'dev' }))).not.toThrow()
  })
})

describe('the home page', () => {
  it('shows the pinned announcements, then the three newest, in a band that links to /news/', () => {
    useSiteRoot()
    renderInFrame(<HomePage />)
    const band = document.getElementById('announcements')!
    const words = loadHomeContent().announcements
    expect(within(band).getByRole('heading', { level: 2 }).textContent).toBe(words.title)
    expect(within(band).getAllByRole('heading', { level: 3 }).map((heading) => heading.textContent)).toEqual([
      'Tournament forms are due',
      'Welcome back to the debate season',
      'Food drive this week',
      'Parent meeting next week',
      'Novice packets are ready',
    ])
    expect(within(band).getAllByText(loadNewsLabels().pinned)).toHaveLength(2)
    const all = within(band).getByRole('link', { name: words.action.label })
    expect(all.getAttribute('href')?.replace(/\/$/, '')).toBe('/news')
  })

  it('links each one to its own page and gives its date', () => {
    useSiteRoot()
    renderInFrame(<HomePage />)
    const band = document.getElementById('announcements')!
    const link = within(band).getByRole('link', { name: 'Food drive this week' })
    expect(link.getAttribute('href')?.replace(/\/$/, '')).toBe('/news/2026-11-02-food-drive')
    expect(within(band).getByText('Monday, November 2, 2026').getAttribute('datetime')).toBe('2026-11-02')
  })

  it('sits after the email-updates band and before the results', () => {
    useSiteRoot()
    renderInFrame(<HomePage />)
    const order = [...document.querySelectorAll('main section[id]')].map((section) => section.id)
    expect(order.indexOf('announcements')).toBe(order.indexOf('email-updates') + 1)
    expect(order.indexOf('announcements')).toBeLessThan(order.indexOf('recent-results'))
  })

  it('leaves the band out while no announcement is published', () => {
    useSiteRoot({})
    renderInFrame(<HomePage />)
    expect(document.getElementById('announcements')).toBeNull()
  })
})

describe('the /news/ page', () => {
  it('lists every published announcement newest first, each linking to its page', async () => {
    useSiteRoot()
    renderInFrame(await newsRoute())
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe(loadPage(NEWS_SLUG).title)
    const list = document.getElementById('news-list')!
    expect(within(list).getAllByRole('heading', { level: 2 }).map((heading) => heading.textContent)).toEqual([
      'Food drive this week',
      'Tournament forms are due',
      'Parent meeting next week',
      'Novice packets are ready',
      'Practice moves to the library',
      'Welcome back to the debate season',
    ])
    expect(within(list).queryByText(loadNewsLabels().pinned)).toBeNull()
  })

  it('says so when nothing is published', async () => {
    useSiteRoot({})
    renderInFrame(await newsRoute())
    expect(screen.getByText(loadNewsLabels().empty)).toBeDefined()
  })

  it('is not in the main navigation, and is linked from the footer of every page', () => {
    const navigation = buildNavigation()
    expect(navigation.primary.map((link) => link.href)).not.toContain('/news/')
    expect(navigation.utility.map((link) => link.href)).toContain('/news/')
  })

  it('is composed by its own route module, so the Markdown page route never generates it', () => {
    expect(COMPOSED_SLUGS).toContain(NEWS_SLUG)
  })
})

describe("an announcement's own page", () => {
  it('has its title, its date, its picture with alt text, its body and the way back to /news/', async () => {
    useSiteRoot()
    renderInFrame(await newsRoute('2026-10-26-parent-meeting'))
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Parent meeting next week')
    expect(screen.getByText('Monday, October 26, 2026').getAttribute('datetime')).toBe('2026-10-26')
    const main = screen.getByRole('main')
    expect(within(main).getByRole('img').getAttribute('alt')).toBe("The team's mark in navy")
    expect(screen.getByText('Bring your questions about rides and overnight tournaments.')).toBeDefined()
    const back = screen.getByRole('link', { name: loadNewsLabels().backToNews })
    expect(back.getAttribute('href')?.replace(/\/$/, '')).toBe('/news')
  })

  it('is generated for /news/ and for every published announcement, and no other', () => {
    useSiteRoot()
    expect(generateStaticParams()).toEqual([
      { slug: [] },
      ...PUBLISHED_ON_THE_BUILD_DATE.map((slug) => ({ slug: [slug] })),
    ])
  })

  it('takes its title and description from the announcement', async () => {
    useSiteRoot()
    const metadata = await generateMetadata({ params: Promise.resolve({ slug: ['2026-10-26-parent-meeting'] }) })
    expect(metadata.title).toBe('Parent meeting next week')
    expect(metadata.description).toBe('Families are invited to a short meeting about travel for the rest of the season.')
  })
})

describe('the sitemap', () => {
  it('lists /news/ and every published announcement, and no expired or future one', () => {
    useSiteRoot()
    vi.stubEnv('SITE_URL', 'https://wfbdebate.example.invalid')
    const paths = sitemap().map((entry) => new URL(entry.url).pathname)
    expect(paths).toContain('/news/')
    expect(paths.filter((path) => path.startsWith('/news/') && path !== '/news/')).toEqual(
      PUBLISHED_ON_THE_BUILD_DATE.map((slug) => `/news/${slug}/`),
    )
    for (const slug of NEVER_PUBLISHED_ON_THE_BUILD_DATE) {
      expect(paths).not.toContain(`/news/${slug}/`)
    }
  })
})

describe('accessibility', () => {
  it.each([
    ['the home page with its announcements band', () => <HomePage />],
    ['the /news/ list', () => newsRoute()],
    ['an announcement with a picture', () => newsRoute('2026-10-26-parent-meeting')],
  ])('%s has no WCAG 2.1 AA violation', async (_page, route) => {
    useSiteRoot()
    renderInFrame(await route())
    const violations = await findAccessibilityViolations(document.body)
    expect(violations, describeViolations(violations)).toEqual([])
  })
})

/**
 * Every word on the news pages and in the home band comes from site/content/, as on every other
 * page (v1-e36-t03): this fails if a label is typed into a component instead.
 */
describe('the news pages hold no copy of their own', () => {
  function sourceFiles(directory: string): string[] {
    return readdirSync(join(process.cwd(), directory)).flatMap((entry) => {
      const path = join(directory, entry)
      if (statSync(join(process.cwd(), path)).isDirectory()) {
        return sourceFiles(path)
      }
      return /\.tsx?$/.test(entry) ? [path] : []
    })
  }

  const sources = [...sourceFiles('src/app'), ...sourceFiles('src/components')].map(
    (path) => [path, readFileSync(join(process.cwd(), path), 'utf8')] as const,
  )
  const labels = loadNewsLabels()
  const home = loadHomeContent().announcements
  const copy = [
    loadPage(NEWS_SLUG).title,
    labels.pinned,
    labels.empty,
    labels.backToNews,
    home.eyebrow,
    home.title,
    home.intro,
    home.action.label,
  ]

  it.each(copy.map((text) => [text.slice(0, 48), text] as const))('"%s" is not written into a component', (_label, text) => {
    for (const [path, source] of sources) {
      // As text in JSX or as a string literal. A plain substring test would match "Announcements"
      // inside identifiers such as loadPublishedAnnouncements.
      const written = [`>${text}<`, `'${text}'`, `"${text}"`, `\`${text}\``].some((form) => source.includes(form))
      expect(written, `${path} contains news copy`).toBe(false)
    }
  })
})
