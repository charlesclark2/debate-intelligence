import { existsSync, readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'

import matter from 'gray-matter'
import { marked } from 'marked'
import { z } from 'zod'

/**
 * The typed content loader.
 *
 * Every word of copy on this site lives in site/content/ as Markdown with YAML front matter (or,
 * for site-wide strings, as YAML); no page component holds copy of its own. The loader runs at
 * build time only, validates each file against a schema, and throws with the offending file name
 * so `pnpm --dir site build` fails loudly rather than shipping a page with a missing title.
 *
 * It also enforces the two house-style rules the team writes by, because the audience is parents
 * and students new to debate:
 *   - no em dashes in body copy;
 *   - every acronym in ACRONYM_EXPANSIONS is spelled out somewhere on the page that uses it.
 */

/** The page whose copy renders at the site root rather than at /<slug>/. */
export const HOME_SLUG = 'home'

/**
 * Acronyms a parent or a new student cannot be expected to know. If a page uses one, the page
 * must also contain the expansion. Checked at build time; see site/README.md.
 */
export const ACRONYM_EXPANSIONS: ReadonlyMap<string, string> = new Map([
  ['NSDA', 'National Speech and Debate Association'],
  ['NCFL', 'National Catholic Forensic League'],
  ['TOC', 'Tournament of Champions'],
  ['LD', 'Lincoln-Douglas'],
  ['PF', 'Public Forum'],
  ['WDCA', 'Wisconsin Debate Coaches Association'],
])

/**
 * A fact only Charlie can supply, written into the copy as `[[TBD]]` or `[[TBD: what is needed]]`.
 *
 * The marker renders as a visible "TBD" so a dev preview shows exactly where the gaps are, and
 * `src/lib/publishing-policy.ts` fails a prod build while any of them remain. That is the build
 * guard the task spec asks for: nobody has to remember that the room number was never filled in.
 */
export const PLACEHOLDER_PATTERN = /\[\[TBD(?::\s*([^\]]*))?\]\]/g

/** The notes attached to every placeholder marker in a string, in the order they appear. */
export function findPlaceholders(text: string): string[] {
  return [...text.matchAll(PLACEHOLDER_PATTERN)].map((match) => match[1]?.trim() ?? '')
}

function renderPlaceholders(text: string): string {
  return text.replace(PLACEHOLDER_PATTERN, '<span class="placeholder">TBD</span>')
}

export const pageFrontMatterSchema = z.object({
  title: z.string().min(1, 'title must not be empty'),
  description: z.string().min(1, 'description must not be empty'),
  navLabel: z.string().min(1).optional(),
  navOrder: z.number().int().nonnegative().optional(),
  openGraphImage: z.string().min(1).optional(),
  draft: z.boolean().optional(),
})

/** One coach or team address. The site publishes no other kind of address. */
export const contactEmailSchema = z.object({
  address: z.string().min(1).regex(/^[^@\s]+@[^@\s]+\.[^@\s]+$/, 'must be an email address'),
  name: z.string().min(1),
  role: z.string().min(1),
})

export const siteSettingsSchema = z.object({
  name: z.string().min(1),
  shortName: z.string().min(1),
  tagline: z.string().min(1),
  footerNote: z.string().min(1),
  logoAlternativeText: z.string().min(1),
  navigationLabel: z.string().min(1),
  skipLinkLabel: z.string().min(1),
  contactEmails: z.array(contactEmailSchema).min(1),
  debaterLoginLabel: z.string().min(1),
})

/**
 * The structured parts of the home page, in content/home.yaml.
 *
 * The home page is the one page that is laid out rather than read straight through, so its
 * headings, panel facts, card labels and links are data rather than Markdown. The prose on it is
 * still content/pages/home.md; this schema covers everything around that prose.
 *
 * `.min(3).max(5)` on the entry-point cards is the acceptance criterion for v1-e36-t06 written
 * as a schema: a sixth card fails the build rather than quietly making the row unscannable.
 */

/** A link out of a panel or a card. Internal only: see `internalHref`. */
const internalHref = z
  .string()
  .min(1)
  .refine(
    (value) => value.startsWith('/') || value.startsWith('#'),
    'must point inside this site, so start with "/" or "#"',
  )

export const homeActionSchema = z.object({
  label: z.string().min(1),
  href: internalHref,
})

export const homeContentSchema = z.object({
  hero: z.object({
    lead: z.string().min(1),
    action: homeActionSchema,
  }),
  parentSession: z.object({
    eyebrow: z.string().min(1),
    title: z.string().min(1),
    intro: z.string().min(1),
    facts: z.array(z.object({ label: z.string().min(1), value: z.string().min(1) })).min(1),
    whatToExpect: z.array(z.string().min(1)).min(1),
    note: z.string().min(1),
    action: homeActionSchema,
  }),
  entryPoints: z.object({
    eyebrow: z.string().min(1),
    title: z.string().min(1),
    intro: z.string().min(1),
    cards: z
      .array(
        z.object({
          title: z.string().min(1),
          body: z.string().min(1),
          actionLabel: z.string().min(1),
          href: internalHref,
        }),
      )
      .min(3, 'the home page needs at least three entry points')
      .max(5, 'more than five entry points stops being scannable'),
  }),
  prose: z.object({
    eyebrow: z.string().min(1),
    title: z.string().min(1),
  }),
  whatDebateBuilds: z.object({
    eyebrow: z.string().min(1),
    title: z.string().min(1),
    intro: z.string().min(1),
    claims: z.array(z.object({ title: z.string().min(1), body: z.string().min(1) })).min(1),
  }),
})

export type HomeAction = z.infer<typeof homeActionSchema>
export type HomeContent = z.infer<typeof homeContentSchema>

export type PageFrontMatter = z.infer<typeof pageFrontMatterSchema>
export type ContactEmail = z.infer<typeof contactEmailSchema>
export type SiteSettings = z.infer<typeof siteSettingsSchema>

export interface ContentPage {
  /** File stem, e.g. `join` for content/pages/join.md. */
  slug: string
  /** The exported route, always with a trailing slash: `/` for home, `/join/` otherwise. */
  route: string
  /** Path relative to site/, used in error messages. */
  filePath: string
  title: string
  description: string
  navLabel: string
  navOrder: number
  openGraphImage?: string
  draft: boolean
  /** Markdown body rendered to HTML at build time. */
  html: string
  /**
   * One entry per `[[TBD]]` marker left in the file, holding the note written beside it. Empty on
   * a page that is ready to publish.
   */
  placeholders: string[]
}

/** Thrown when a content file is missing a required field or breaks a house-style rule. */
export class ContentValidationError extends Error {
  readonly filePath: string

  constructor(filePath: string, detail: string) {
    super(`${filePath}: ${detail}`)
    this.name = 'ContentValidationError'
    this.filePath = filePath
  }
}

export function defaultContentDirectory(): string {
  return join(process.cwd(), 'content')
}

function pagesDirectory(contentDirectory: string): string {
  return join(contentDirectory, 'pages')
}

function formatIssues(error: z.ZodError): string {
  return error.issues
    .map((issue) => {
      const field = issue.path.join('.')
      return field.length > 0 ? `${field}: ${issue.message}` : issue.message
    })
    .join('; ')
}

const EM_DASH = '—'
const HOUSE_STYLE_REWRITE = 'House style: rewrite with a comma, a colon or two sentences.'

/**
 * `lineOffset` is the number of lines the front matter occupies, so the line number in the error
 * is the one the author sees in their editor rather than an offset into the Markdown body.
 */
function assertNoEmDashesInBody(filePath: string, body: string, lineOffset: number): void {
  const offendingIndex = body.split('\n').findIndex((line) => line.includes(EM_DASH))
  if (offendingIndex >= 0) {
    throw new ContentValidationError(
      filePath,
      `line ${offendingIndex + 1 + lineOffset} uses an em dash. ${HOUSE_STYLE_REWRITE}`,
    )
  }
}

function assertNoEmDashesInFrontMatter(filePath: string, frontMatter: PageFrontMatter): void {
  for (const field of ['title', 'description'] as const) {
    if (frontMatter[field].includes(EM_DASH)) {
      throw new ContentValidationError(
        filePath,
        `the ${field} in the front matter uses an em dash. ${HOUSE_STYLE_REWRITE}`,
      )
    }
  }
}

function assertAcronymsAreExpanded(filePath: string, text: string): void {
  for (const [acronym, expansion] of ACRONYM_EXPANSIONS) {
    const usesAcronym = new RegExp(`\\b${acronym}\\b`).test(text)
    if (usesAcronym && !text.includes(expansion)) {
      throw new ContentValidationError(
        filePath,
        `uses "${acronym}" without spelling it out. Write "${expansion} (${acronym})" the first ` +
          'time it appears.',
      )
    }
  }
}

/** Reads and validates one Markdown page. `filePath` is only used for error messages. */
export function parsePage(slug: string, filePath: string, source: string): ContentPage {
  const parsed = matter(source)
  const result = pageFrontMatterSchema.safeParse(parsed.data)
  if (!result.success) {
    throw new ContentValidationError(filePath, `invalid front matter (${formatIssues(result.error)})`)
  }

  const frontMatter = result.data
  const body = parsed.content
  // gray-matter strips the front matter, so the body starts this many lines into the file.
  const lineOffset = source.split('\n').length - body.split('\n').length
  assertNoEmDashesInFrontMatter(filePath, frontMatter)
  assertNoEmDashesInBody(filePath, body, lineOffset)
  assertAcronymsAreExpanded(filePath, `${frontMatter.title}\n${frontMatter.description}\n${body}`)

  const rendered = marked.parse(renderPlaceholders(body), { async: false })
  if (typeof rendered !== 'string') {
    throw new ContentValidationError(filePath, 'Markdown could not be rendered synchronously')
  }

  return {
    slug,
    route: slug === HOME_SLUG ? '/' : `/${slug}/`,
    filePath,
    title: frontMatter.title,
    description: frontMatter.description,
    navLabel: frontMatter.navLabel ?? frontMatter.title,
    navOrder: frontMatter.navOrder ?? Number.MAX_SAFE_INTEGER,
    ...(frontMatter.openGraphImage ? { openGraphImage: frontMatter.openGraphImage } : {}),
    draft: frontMatter.draft ?? false,
    html: rendered,
    placeholders: findPlaceholders(`${frontMatter.title}\n${frontMatter.description}\n${body}`),
  }
}

/**
 * Every published page, ordered by navOrder and then by title. Draft pages are left out of the
 * export entirely, so they never reach the sitemap or the navigation.
 */
export function loadPages(contentDirectory: string = defaultContentDirectory()): ContentPage[] {
  const directory = pagesDirectory(contentDirectory)
  if (!existsSync(directory)) {
    throw new Error(`Content directory not found: ${directory}`)
  }

  const pages = readdirSync(directory)
    .filter((entry) => entry.endsWith('.md'))
    .sort()
    .map((entry) => {
      const slug = entry.replace(/\.md$/, '')
      const filePath = `content/pages/${entry}`
      return parsePage(slug, filePath, readFileSync(join(directory, entry), 'utf8'))
    })
    .filter((page) => !page.draft)

  return pages.sort((left, right) =>
    left.navOrder === right.navOrder
      ? left.title.localeCompare(right.title)
      : left.navOrder - right.navOrder,
  )
}

export function loadPage(
  slug: string,
  contentDirectory: string = defaultContentDirectory(),
): ContentPage {
  const page = loadPages(contentDirectory).find((candidate) => candidate.slug === slug)
  if (!page) {
    throw new Error(`No content page for slug "${slug}" in ${pagesDirectory(contentDirectory)}`)
  }
  return page
}

/** Pages that get their own route under /<slug>/; the home page renders at the root instead. */
export function loadRoutedPages(
  contentDirectory: string = defaultContentDirectory(),
): ContentPage[] {
  return loadPages(contentDirectory).filter((page) => page.slug !== HOME_SLUG)
}

export function loadSiteSettings(
  contentDirectory: string = defaultContentDirectory(),
): SiteSettings {
  const filePath = 'content/site.yaml'
  const absolutePath = join(contentDirectory, 'site.yaml')
  if (!existsSync(absolutePath)) {
    throw new ContentValidationError(filePath, 'file is missing')
  }

  // gray-matter parses a bare YAML document when it is fenced as front matter, so the settings
  // file is read through the same YAML parser the pages use rather than a second dependency.
  const parsed = matter(`---\n${readFileSync(absolutePath, 'utf8')}\n---\n`)
  const result = siteSettingsSchema.safeParse(parsed.data)
  if (!result.success) {
    throw new ContentValidationError(filePath, `invalid settings (${formatIssues(result.error)})`)
  }
  return result.data
}

/**
 * The copy for the 404 page. It lives outside content/pages/ so it never appears in the
 * navigation or the sitemap, but it is validated by exactly the same schema.
 */
export function loadNotFoundPage(
  contentDirectory: string = defaultContentDirectory(),
): ContentPage {
  const filePath = 'content/not-found.md'
  const absolutePath = join(contentDirectory, 'not-found.md')
  if (!existsSync(absolutePath)) {
    throw new ContentValidationError(filePath, 'file is missing')
  }
  return parsePage('not-found', filePath, readFileSync(absolutePath, 'utf8'))
}

/** Every string in the home content, in reading order, for the checks that scan copy. */
function homeContentStrings(content: HomeContent): string[] {
  const { hero, parentSession, entryPoints, prose, whatDebateBuilds } = content
  return [
    hero.lead,
    hero.action.label,
    parentSession.eyebrow,
    parentSession.title,
    parentSession.intro,
    ...parentSession.facts.flatMap((fact) => [fact.label, fact.value]),
    ...parentSession.whatToExpect,
    parentSession.note,
    parentSession.action.label,
    entryPoints.eyebrow,
    entryPoints.title,
    entryPoints.intro,
    ...entryPoints.cards.flatMap((card) => [card.title, card.body, card.actionLabel]),
    prose.eyebrow,
    prose.title,
    whatDebateBuilds.eyebrow,
    whatDebateBuilds.title,
    whatDebateBuilds.intro,
    ...whatDebateBuilds.claims.flatMap((claim) => [claim.title, claim.body]),
  ]
}

/**
 * The structured home-page content, validated and held to the same house style as the Markdown
 * pages: no em dashes, and no acronym left unexpanded. Both rules exist because the audience is
 * parents and students new to debate, and a heading in a panel is read by exactly the same people
 * as a sentence in a paragraph.
 */
export function loadHomeContent(
  contentDirectory: string = defaultContentDirectory(),
): HomeContent {
  const filePath = 'content/home.yaml'
  const absolutePath = join(contentDirectory, 'home.yaml')
  if (!existsSync(absolutePath)) {
    throw new ContentValidationError(filePath, 'file is missing')
  }

  // Read through gray-matter, the same YAML parser the pages and site.yaml use.
  const parsed = matter(`---\n${readFileSync(absolutePath, 'utf8')}\n---\n`)
  const result = homeContentSchema.safeParse(parsed.data)
  if (!result.success) {
    throw new ContentValidationError(filePath, `invalid home content (${formatIssues(result.error)})`)
  }

  const content = result.data
  const text = homeContentStrings(content).join('\n')
  if (text.includes(EM_DASH)) {
    throw new ContentValidationError(filePath, `uses an em dash. ${HOUSE_STYLE_REWRITE}`)
  }
  assertAcronymsAreExpanded(filePath, text)
  return content
}

/**
 * content/home.yaml as the publishing-policy guard sees it.
 *
 * The guard reads pages, so copy that lives in a YAML file would otherwise be the one place on
 * the site where an email address, a phone number, an unreviewed name or an unfilled placeholder
 * is not checked. Giving it a ContentPage shape costs one function and closes that hole: the
 * root layout passes this alongside loadPages(), and tests/content-policy.test.ts checks it with
 * the rest of the content.
 */
export function homeContentAsPage(
  contentDirectory: string = defaultContentDirectory(),
): ContentPage {
  const content = loadHomeContent(contentDirectory)
  const text = homeContentStrings(content).join('\n\n')
  return {
    slug: 'home-content',
    route: '/',
    filePath: 'content/home.yaml',
    title: content.parentSession.title,
    description: content.hero.lead,
    navLabel: content.parentSession.title,
    navOrder: Number.MAX_SAFE_INTEGER,
    draft: false,
    html: text,
    placeholders: findPlaceholders(text),
  }
}
