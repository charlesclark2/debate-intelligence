import { existsSync, readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'

import matter from 'gray-matter'
import { marked } from 'marked'
import type { Token, Tokens } from 'marked'
import { z } from 'zod'

import {
  ContentValidationError,
  EM_DASH,
  HOUSE_STYLE_REWRITE,
  NEWS_SLUG,
  assertAcronymsAreExpanded,
  defaultContentDirectory,
  findPlaceholders,
  formatIssues,
  loadSiteSettings,
  quoteBareDates,
  renderMarkdown,
} from './content'
import type { ContentPage } from './content'
import { loadMediaConsent } from './media-consent'
import { checkPublishingPolicy, describeFinding, visibleText } from './publishing-policy'
import type { PolicyFinding } from './publishing-policy'
import { isCalendarDate, readYaml } from './tournaments'

export { NEWS_SLUG }

/*
 * ---------------------------------------------------------------------------------------------
 * ANNOUNCEMENTS: content/announcements/*.md (v1-e37-t03, ADR-0015 point 2).
 *
 * One Markdown file per announcement, with front matter. Three things are built from them: the
 * home page's announcements band (every pinned one, then the three newest), the /news/ list
 * (every published one, newest first), and a page of its own for each at /news/<slug>/.
 *
 *   - The slug is the file's name, lower case, with every run of other characters made one
 *     hyphen: `2026-11-03-novice-orientation.md` publishes at /news/2026-11-03-novice-orientation/.
 *     Two files whose names come to the same slug are both refused, each named.
 *   - Published means dated on or before the build date and not yet expired: an item expiring on
 *     a date is shown through that date and gone from the first build after it. The build date is
 *     the day in America/Chicago (readBuildDate). Nothing is hidden by a visitor's browser: the
 *     pages are static, so an expiry takes effect at the next deploy, not on its date.
 *   - Every file is checked, published or not, so a problem in an item dated next week fails the
 *     build the day it is written rather than the day it would appear.
 *
 * The checks, each failing the build in every environment with the file and the rule (the dev
 * preview is public too):
 *   - the front matter: a missing or misspelt field, a date that does not exist, an expiry before
 *     the date, an image with no alt text;
 *   - the body is Markdown only. Raw HTML is refused rather than stripped, so what publishes is
 *     what the file says: a script, an iframe or any other tag fails the build, as do a link that
 *     runs code (javascript:) and an image from another site;
 *   - the house style the rest of content/ follows: no em dashes, every acronym spelled out;
 *   - the publishing-policy guard, src/lib/publishing-policy.ts, exactly as for a page: an email
 *     address, a phone number, a capitalised name nobody has reviewed (in the title, the body, the
 *     alt text or a caption), and an image without a current media-consent entry. A file name
 *     carrying a consented student's name is refused too, without repeating it, since the file
 *     name is the item's web address.
 * A [[TBD]] marker shows as the gap badge and fails a prod build, as on any page: that is the
 * layout's guard, reading announcementsGuardedContent().
 * ---------------------------------------------------------------------------------------------
 */

export const ANNOUNCEMENTS_DIRECTORY = 'content/announcements'
export const NEWS_CONTENT_FILE = 'content/news.yaml'

/** The file in the folder that explains it, for whoever opens it. Never an announcement. */
export const ANNOUNCEMENTS_README = 'README.md'

/** The setting tests and previews use to build as of another day. Unset, the build uses today. */
export const BUILD_DATE_VARIABLE = 'SITE_BUILD_DATE'

/** The team's time zone. "Today" for an expiry is the day here, whatever the build machine says. */
export const SITE_TIME_ZONE = 'America/Chicago'

/** How long a summary may be: about the length a search result shows of a description. */
const SUMMARY_LENGTH = 160

const calendarDate = z
  .string({ error: 'must be a date written as 2026-11-03' })
  .refine(isCalendarDate, 'must be a real date written as 2026-11-03')

const text = z.string({ error: 'must be text' }).trim().min(1, 'must not be empty')

/**
 * The front matter. `.strict()`, so a misspelt field (`expiry:`, `pin:`) fails the build instead
 * of quietly doing nothing.
 */
export const announcementFrontMatterSchema = z
  .object({
    title: text,
    date: calendarDate,
    expires: calendarDate.optional(),
    pinned: z.boolean({ error: 'must be true or false' }).optional(),
    image: z
      .string({ error: 'must be a path' })
      .regex(
        /^\/(?!\/)\S+$/,
        'must be a path on this site starting with "/", such as /photos/novice-orientation.jpg; an image is never loaded from another site',
      )
      .optional(),
    alt: text.optional(),
  })
  .strict()
  .superRefine((value, ctx) => {
    if (value.expires !== undefined && value.expires < value.date) {
      ctx.addIssue({ code: 'custom', path: ['expires'], message: `is before date (${value.date})` })
    }
    if (value.image !== undefined && value.alt === undefined) {
      ctx.addIssue({
        code: 'custom',
        path: ['alt'],
        message: 'is required with image: say what the picture shows, naming nobody unless their consent allows it',
      })
    }
    if (value.alt !== undefined && value.image === undefined) {
      ctx.addIssue({ code: 'custom', path: ['alt'], message: 'goes with image, and there is no image' })
    }
  })

const newsContentSchema = z
  .object({
    labels: z.object({ pinned: text, empty: text, backToNews: text }).strict(),
  })
  .strict()

export type NewsLabels = z.infer<typeof newsContentSchema>['labels']

export interface Announcement {
  /** The file's name, as the address publishes it: lower case words joined by hyphens. */
  slug: string
  /** `/news/<slug>/`. */
  route: string
  /** Path relative to site/, used in every message. */
  filePath: string
  title: string
  /** The publish date, 2026-11-03. */
  date: string
  /** The last day it is shown, or null for one that stays up until it is removed. */
  expires: string | null
  pinned: boolean
  image: { path: string; alt: string } | null
  /** The body rendered to HTML at build time, through the site's one Markdown path. */
  html: string
  /** The body's opening, as plain text: the list's summary and the page's meta description. */
  summary: string
  /** One entry per [[TBD]] marker left in the file. */
  placeholders: string[]
}

export interface AnnouncementsCheck {
  /** Every file that passed every check, newest first. */
  announcements: Announcement[]
  /** Every problem found, each naming its file and, where there is one, the policy rule. */
  problems: PolicyFinding[]
}

/*
 * The build date.
 */

/** The calendar day an instant falls on in a time zone, as 2026-11-03. */
export function calendarDateIn(timeZone: string, instant: Date): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(instant)
  const part = (type: string) => parts.find((candidate) => candidate.type === type)?.value ?? ''
  return `${part('year')}-${part('month')}-${part('day')}`
}

/**
 * The day the build is for: SITE_BUILD_DATE when it is set, which is how the tests pin it and how
 * a dev preview can show next week's page, and otherwise today in America/Chicago. The deploy
 * blocks refuse to run with any SITE_ variable left over, so a prod build uses today.
 */
export function readBuildDate(env: NodeJS.ProcessEnv = process.env, now: () => Date = () => new Date()): string {
  const set = env[BUILD_DATE_VARIABLE]
  if (set !== undefined && set !== '') {
    if (!isCalendarDate(set)) {
      throw new Error(`${BUILD_DATE_VARIABLE} is "${set}", which is not a date written as 2026-11-03`)
    }
    return set
  }
  return calendarDateIn(SITE_TIME_ZONE, now())
}

/** Shown on the build date: dated on or before it, and expiring on or after it. */
export function isPublished(announcement: Pick<Announcement, 'date' | 'expires'>, buildDate: string): boolean {
  return announcement.date <= buildDate && (announcement.expires === null || buildDate <= announcement.expires)
}

/** Newest first: by date, then by title, then by slug, so the order never depends on the disk. */
function compareNewestFirst(left: Announcement, right: Announcement): number {
  return (
    right.date.localeCompare(left.date) ||
    left.title.localeCompare(right.title) ||
    left.slug.localeCompare(right.slug)
  )
}

/** What /news/ lists: every announcement published on the build date, newest first. */
export function publishedAnnouncements(announcements: readonly Announcement[], buildDate: string): Announcement[] {
  return announcements.filter((announcement) => isPublished(announcement, buildDate)).sort(compareNewestFirst)
}

/**
 * What the home page shows (the PM's ruling of 2026-11-02): every pinned announcement, newest
 * first, then the `count` newest that are not pinned. A pinned one does not count toward them.
 * Expects published announcements; an expired pinned one is not among them.
 */
export function homeAnnouncements(published: readonly Announcement[], count = 3): Announcement[] {
  const ordered = [...published].sort(compareNewestFirst)
  return [
    ...ordered.filter((announcement) => announcement.pinned),
    ...ordered.filter((announcement) => !announcement.pinned).slice(0, count),
  ]
}

/*
 * Reading and checking the files.
 */

/** A file name as the address publishes it. */
export function slugFor(fileName: string): string {
  return fileName
    .replace(/\.md$/i, '')
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
}

function finding(location: string, message: string, rule?: string): PolicyFinding {
  return rule === undefined ? { location, message } : { location, message, rule }
}

/** The tag as the message quotes it: enough to find it in the file. */
function quoteTag(raw: string): string {
  const tag = raw.trim().replace(/\s+/g, ' ')
  return tag.length > 60 ? `${tag.slice(0, 57)}...` : tag
}

/** A link target that is a place, not a program: this site, another page, or an address. */
const SAFE_LINK = /^(?:\/(?!\/)|#|https?:\/\/|mailto:)/i

/**
 * Everything in a body the Markdown-only rule refuses, by walking the tokens the renderer itself
 * reads, so nothing is judged on a reading of the text that differs from what would render.
 */
function bodyProblems(location: string, tokens: Token[]): PolicyFinding[] {
  const problems: PolicyFinding[] = []
  marked.walkTokens(tokens, (token) => {
    if (token.type === 'html') {
      const raw = (token as Tokens.HTML).raw
      const tag = quoteTag(raw)
      if (/<\s*script\b/i.test(raw)) {
        problems.push(
          finding(
            location,
            `contains a script (${tag}). An announcement is Markdown only, and the site runs no code from a content file`,
            'Analytics and third parties 1 and 5',
          ),
        )
      } else if (/<\s*(?:iframe|frame|embed|object)\b/i.test(raw)) {
        problems.push(
          finding(
            location,
            `contains an embed (${tag}). Nothing is embedded from another site: link to it instead, ` +
              'with an ordinary Markdown link',
            'Analytics and third parties 4 and 6',
          ),
        )
      } else {
        problems.push(
          finding(
            location,
            `contains raw HTML (${tag}). An announcement is Markdown only: HTML is refused rather ` +
              'than stripped, so what publishes is what the file says. Write it in Markdown: ' +
              '**bold**, *italic*, [a link](/schedule/), a list',
            'Analytics and third parties 5 and 6',
          ),
        )
      }
    } else if (token.type === 'link' && !SAFE_LINK.test((token as Tokens.Link).href)) {
      problems.push(
        finding(
          location,
          `links to "${quoteTag((token as Tokens.Link).href)}". A link goes to a page on this site, ` +
            'an https:// address or a mailto: address; anything else can run code in the browser',
          'Analytics and third parties 1 and 5',
        ),
      )
    } else if (token.type === 'image' && !/^\/(?!\/)/.test((token as Tokens.Image).href)) {
      problems.push(
        finding(
          location,
          `shows the image "${quoteTag((token as Tokens.Image).href)}" from another site. Every ` +
            'image is served from this site, from a path starting with "/", with its media-consent entry',
          'Analytics and third parties 5',
        ),
      )
    }
  })
  return problems
}

/** The body's opening paragraph as plain text, cut at a word near SUMMARY_LENGTH. */
function summaryOf(html: string): string {
  // Alt text and captions are left out: the summary is the opening words, not a picture's.
  const opening =
    visibleText(html.replace(/\s(?:alt|title)\s*=\s*(?:"[^"]*"|'[^']*')/gi, ''))
      .split(/\n\s*\n/)
      .map((block) => block.replace(/\s+/g, ' ').trim())
      .find((block) => block.length > 0) ?? ''
  if (opening.length <= SUMMARY_LENGTH) {
    return opening
  }
  const cut = opening.slice(0, SUMMARY_LENGTH)
  return `${cut.slice(0, Math.max(cut.lastIndexOf(' '), 1)).replace(/[\s,;:.]+$/, '')}...`
}

function escapeAttribute(value: string): string {
  return value.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;')
}

/**
 * What an announcement publishes, as the guard reads a page: its title (the <h1> and the <title>),
 * its summary (the meta description and the list's line), its image with the alt text the page
 * gives it, and its body.
 */
function guardedHtml(announcement: Announcement): string {
  return [
    `<p>${announcement.title}</p>`,
    `<p>${announcement.summary}</p>`,
    ...(announcement.image
      ? [`<figure><img src="${announcement.image.path}" alt="${escapeAttribute(announcement.image.alt)}"></figure>`]
      : []),
    announcement.html,
  ].join('\n')
}

/**
 * One announcement as a content page: how the publishing-policy guard reads it, and what its own
 * page's metadata is built from (its summary is the meta description).
 */
export function announcementAsPage(announcement: Announcement): ContentPage {
  return {
    slug: `announcement-${announcement.slug}`,
    route: announcement.route,
    filePath: announcement.filePath,
    title: announcement.title,
    description: announcement.summary,
    navLabel: announcement.title,
    navOrder: Number.MAX_SAFE_INTEGER,
    excludeFromNavigation: true,
    draft: false,
    html: announcement.html,
    guardedHtml: guardedHtml(announcement),
    placeholders: announcement.placeholders,
  }
}

/**
 * Reads one file into an announcement, or the problems that stop it publishing. The house style,
 * the Markdown-only rule and the schema; the publishing-policy guard runs over the result in
 * checkAnnouncements, with the site's settings and consent manifest.
 */
function readAnnouncement(fileName: string, source: string): Announcement | PolicyFinding[] {
  const filePath = `${ANNOUNCEMENTS_DIRECTORY}/${fileName}`
  const slug = slugFor(fileName)
  if (slug === '') {
    return [finding(filePath, 'has a name with no letters or digits in it, so it has no web address. Rename it, for example 2026-11-03-novice-orientation.md')]
  }

  let frontMatter: unknown
  let body: string
  try {
    // An options object, even an empty one, keeps gray-matter from answering out of its cache: its
    // copy of a file it has read before has no `matter`, so the second read of an announcement in
    // one build failed (found by this task's first build with an announcement in it).
    const document = matter(source, {})
    body = document.content
    // The front matter is parsed again with its bare dates quoted, so `date: 2026-11-03` reaches
    // the schema as typed rather than as a moment in UTC, and an impossible date fails instead of
    // moving (quoteBareDates in src/lib/content.ts). The body is left exactly as written.
    frontMatter = matter(`---\n${quoteBareDates(document.matter)}\n---\n`, {}).data
  } catch (error) {
    return [finding(filePath, `has front matter that cannot be read (${(error as Error).message})`)]
  }
  const result = announcementFrontMatterSchema.safeParse(frontMatter)
  if (!result.success) {
    const issue = result.error.issues[0]!
    if (issue.code === 'unrecognized_keys') {
      return [
        finding(
          filePath,
          `front matter field ${issue.keys.join(', ')} is not a field an announcement has. The ` +
            'fields are title, date, expires, pinned, image and alt',
        ),
      ]
    }
    return [finding(filePath, `front matter ${formatIssues(result.error)}`)]
  }
  const front = result.data
  if (body.trim() === '') {
    return [finding(filePath, 'has no body. Write the announcement under the front matter')]
  }

  const problems: PolicyFinding[] = []
  // gray-matter strips the front matter, so the body starts this many lines into the file.
  const lineOffset = source.split('\n').length - body.split('\n').length
  for (const [field, value] of [
    ['title', front.title],
    ['alt', front.alt ?? ''],
  ] as const) {
    if (value.includes(EM_DASH)) {
      problems.push(finding(filePath, `the ${field} uses an em dash. ${HOUSE_STYLE_REWRITE}`))
    }
  }
  const dashedLine = body.split('\n').findIndex((line) => line.includes(EM_DASH))
  if (dashedLine >= 0) {
    problems.push(finding(filePath, `line ${dashedLine + 1 + lineOffset} uses an em dash. ${HOUSE_STYLE_REWRITE}`))
  }
  try {
    assertAcronymsAreExpanded(filePath, [front.title, front.alt ?? '', body].join('\n'))
  } catch (error) {
    if (!(error instanceof ContentValidationError)) {
      throw error
    }
    problems.push(finding(filePath, error.message.slice(`${filePath}: `.length)))
  }
  problems.push(...bodyProblems(filePath, marked.lexer(body)))
  if (problems.length > 0) {
    return problems
  }

  const html = renderMarkdown(filePath, body)
  return {
    slug,
    route: `/${NEWS_SLUG}/${slug}/`,
    filePath,
    title: front.title,
    date: front.date,
    expires: front.expires ?? null,
    pinned: front.pinned ?? false,
    image: front.image !== undefined && front.alt !== undefined ? { path: front.image, alt: front.alt } : null,
    html,
    summary: summaryOf(html),
    placeholders: findPlaceholders([front.title, front.alt ?? '', body].join('\n')),
  }
}

/** The announcement files in the folder, sorted, with anything that is not one refused. */
function announcementFiles(directory: string): { files: string[]; problems: PolicyFinding[] } {
  if (!existsSync(directory)) {
    return { files: [], problems: [] }
  }
  const files: string[] = []
  const problems: PolicyFinding[] = []
  for (const entry of readdirSync(directory, { withFileTypes: true }).sort((left, right) =>
    left.name.localeCompare(right.name),
  )) {
    if (entry.name === ANNOUNCEMENTS_README || entry.name.startsWith('.')) {
      continue
    }
    if (!entry.isFile() || !entry.name.endsWith('.md')) {
      problems.push(
        finding(
          `${ANNOUNCEMENTS_DIRECTORY}/${entry.name}`,
          'is not an announcement file. Each announcement is one Markdown file directly in this ' +
            'folder, with a name ending in .md',
        ),
      )
      continue
    }
    files.push(entry.name)
  }
  return { files, problems }
}

/**
 * True when the slug carries a consented student's whole name, hyphenated as a slug writes it.
 * Only names the manifest knows can be recognised; the guide asks for none in a file name at all.
 */
function slugNamesStudent(slug: string, studentNames: readonly string[]): boolean {
  return studentNames.some((name) => `-${slug}-`.includes(`-${slugFor(name)}-`))
}

/**
 * Every announcement file checked, without throwing: the ones that pass, newest first, and every
 * problem with the others. loadAnnouncements is the build's use of it; tests read both halves.
 */
export function checkAnnouncements(contentDirectory: string = defaultContentDirectory()): AnnouncementsCheck {
  const directory = join(contentDirectory, 'announcements')
  const { files, problems } = announcementFiles(directory)
  const settings = loadSiteSettings(contentDirectory)
  const consent = loadMediaConsent(contentDirectory)
  const studentNames = consent.students
    .map((student) => student.publishedName)
    .filter((name) => name.trim().split(/\s+/).length > 1)

  const read: Announcement[] = []
  files.forEach((fileName, index) => {
    const outcome = readAnnouncement(fileName, readFileSync(join(directory, fileName), 'utf8'))
    if (Array.isArray(outcome)) {
      problems.push(...outcome)
      return
    }
    if (slugNamesStudent(outcome.slug, studentNames)) {
      // Named by position, not by file name: the file name is the student's name, and a build log
      // carries none (docs/policies/website-publishing.md, Students 10).
      problems.push(
        finding(
          `${ANNOUNCEMENTS_DIRECTORY}, file ${index + 1} in alphabetical order`,
          "has a file name containing a student's name from content/media-consent.yaml. The file " +
            'name is the announcement\'s web address, and carries no name: rename it for what it ' +
            'announces',
          'Students 10',
        ),
      )
      return
    }
    // The guard every page goes through, with this file's own copy. [[TBD]] markers are left to
    // the layout's guard, which fails a prod build on them and lets a dev preview show the badge.
    const { errors } = checkPublishingPolicy({
      pages: [{ ...announcementAsPage(outcome), placeholders: [] }],
      settings,
      consent,
    })
    if (errors.length > 0) {
      // Once each: the summary repeats the body's opening, and a linked address is in the link
      // text and its target, so the guard meets the same problem more than once in one file.
      const seen = new Set<string>()
      for (const error of errors) {
        if (!seen.has(describeFinding(error))) {
          seen.add(describeFinding(error))
          problems.push(error)
        }
      }
      return
    }
    read.push(outcome)
  })

  const bySlug = new Map<string, Announcement[]>()
  for (const announcement of read) {
    bySlug.set(announcement.slug, [...(bySlug.get(announcement.slug) ?? []), announcement])
  }
  for (const [slug, sharing] of bySlug) {
    if (sharing.length > 1) {
      problems.push(
        finding(
          ANNOUNCEMENTS_DIRECTORY,
          `${sharing.map((announcement) => announcement.filePath).join(' and ')} would both publish ` +
            `at /${NEWS_SLUG}/${slug}/, because a file's name is its address. Rename one of them`,
        ),
      )
    }
  }

  return {
    announcements: read
      .filter((announcement) => bySlug.get(announcement.slug)!.length === 1)
      .sort(compareNewestFirst),
    problems,
  }
}

/** Thrown by the build when an announcement file cannot be published. */
export class AnnouncementsError extends ContentValidationError {
  readonly problems: PolicyFinding[]

  constructor(problems: PolicyFinding[]) {
    super(
      ANNOUNCEMENTS_DIRECTORY,
      'cannot be published:\n' + problems.map((problem) => `  ${describeFinding(problem)}`).join('\n'),
    )
    this.name = 'AnnouncementsError'
    this.problems = problems
  }
}

/**
 * Every announcement file, checked. Any problem with any file fails the build, in every
 * environment, naming each file and rule; published or not, every file is held to the same rules.
 */
export function loadAnnouncements(contentDirectory: string = defaultContentDirectory()): Announcement[] {
  const { announcements, problems } = checkAnnouncements(contentDirectory)
  if (problems.length > 0) {
    throw new AnnouncementsError(problems)
  }
  return announcements
}

export function loadNewsLabels(contentDirectory: string = defaultContentDirectory()): NewsLabels {
  const result = newsContentSchema.safeParse(readYaml(contentDirectory, 'news.yaml', NEWS_CONTENT_FILE))
  if (!result.success) {
    throw new ContentValidationError(NEWS_CONTENT_FILE, `invalid news labels (${formatIssues(result.error)})`)
  }
  const { labels } = result.data
  const strings = Object.values(labels)
  if (strings.some((value) => value.includes(EM_DASH))) {
    throw new ContentValidationError(NEWS_CONTENT_FILE, `uses an em dash. ${HOUSE_STYLE_REWRITE}`)
  }
  assertAcronymsAreExpanded(NEWS_CONTENT_FILE, strings.join('\n'))
  return labels
}

/** The announcements published on the build date, newest first, for the pages and the sitemap. */
export function loadPublishedAnnouncements(
  contentDirectory: string = defaultContentDirectory(),
  buildDate: string = readBuildDate(),
): Announcement[] {
  return publishedAnnouncements(loadAnnouncements(contentDirectory), buildDate)
}

/**
 * The announcements and content/news.yaml as the layout's publishing-policy guard reads them:
 * every file, published or not, so a [[TBD]] marker fails a prod build and shows in a dev preview,
 * and the guard's list is still everything with copy in it. loadAnnouncements() has already
 * refused any other problem, in every environment.
 */
export function announcementsGuardedContent(contentDirectory: string = defaultContentDirectory()): ContentPage[] {
  const labels = Object.values(loadNewsLabels(contentDirectory)).join('\n\n')
  return [
    {
      slug: 'news-labels',
      route: `/${NEWS_SLUG}/`,
      filePath: NEWS_CONTENT_FILE,
      title: NEWS_CONTENT_FILE,
      description: NEWS_CONTENT_FILE,
      navLabel: NEWS_CONTENT_FILE,
      navOrder: Number.MAX_SAFE_INTEGER,
      excludeFromNavigation: true,
      draft: false,
      html: labels,
      guardedHtml: labels,
      placeholders: findPlaceholders(labels),
    },
    ...loadAnnouncements(contentDirectory).map(announcementAsPage),
  ]
}
