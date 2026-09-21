import type { AnnouncementField, ContentPage, SiteSettings } from './content'
import type { MediaConsent } from './media-consent'
import { isStale } from './media-consent'
import { readSiteEnvironment } from './site-settings'

/**
 * The content guard.
 *
 * docs/policies/website-publishing.md sets what may be published; this file is the part of it a
 * build can check by itself, so that a lapsed consent or a half-written page cannot reach prod
 * because nobody happened to look. It runs over site/content/ during `next build` (from
 * src/app/layout.tsx) and again over the built HTML in tests/content-policy.test.ts.
 *
 * Errors fail a prod build. Warnings are printed in every environment and are the things a
 * person has to look at, chiefly a consent entry that predates the current season.
 *
 * Deliberately not here: detecting an unknown "First Last" name is only as good as its
 * vocabulary, and the policy assigns the full published-names allowlist to v1-e37-t03. What this
 * guard does is flag a capitalised name made of words nobody has reviewed, which is enough to
 * stop a student name reaching prod unnoticed.
 */

export interface PolicyFinding {
  /** Where the problem is: a content file path, or a built page route. */
  location: string
  message: string
}

export interface PolicyReport {
  errors: PolicyFinding[]
  warnings: PolicyFinding[]
}

/** Any address that looks like an email, so a non-allowlisted one cannot slip through. */
const EMAIL_PATTERN = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g

/**
 * North American phone numbers in the shapes a coach would actually type. The policy forbids
 * publishing a phone number at all (Students 6), so this errs towards catching too much: a year
 * range like 2026-2027 is excluded by requiring a 3-3-4 or 3-4 grouping with a separator.
 */
const PHONE_PATTERN = /(?:\+?1[\s.-]?)?(?:\(\d{3}\)|\b\d{3})[\s.-]\d{3}[\s.-]\d{4}\b/g

/** A script or an iframe whose source is not this site's own origin. */
const CROSS_ORIGIN_SCRIPT = /<script\b[^>]*\bsrc\s*=\s*["'](?:[a-z]+:)?\/\//gi
const CROSS_ORIGIN_IFRAME = /<iframe\b[^>]*\bsrc\s*=\s*["'](?:[a-z]+:)?\/\//gi
const ANY_IFRAME = /<iframe\b/gi

/** Image references in Markdown, in HTML and in a CSS url(). */
const IMAGE_REFERENCE = /!\[[^\]]*\]\(([^)\s]+)\)|<img\b[^>]*\bsrc\s*=\s*["']([^"']+)["']/gi

/**
 * Runs of two or more capitalised words, which is what a person's name looks like in prose. The
 * apostrophe allows O'Brien, and the match is greedy so "Martin Luther King" is one candidate
 * rather than two overlapping ones. A single space or newline separates the words: a blank line
 * ends the phrase, so a heading and the paragraph under it are never read as one name.
 */
const CAPITALISED_PHRASE = /\b[A-Z][a-z'’]+(?:\s(?!\s)[A-Z][a-z'’]+)+\b/g

function collect(text: string, pattern: RegExp): string[] {
  return [...text.matchAll(pattern)].map((match) => match[0])
}

/**
 * A built page carries Next's React payload inside <script> tags: the same copy again, escaped
 * as JSON. Scanning it would report every address and name twice, with the escaping mangled into
 * nonsense like `u003echarles.clark@`. The text rules therefore read the page without its
 * scripts and styles; the cross-origin rules read the raw HTML, because a forbidden script tag is
 * exactly what they are looking for.
 */
export function withoutScripts(html: string): string {
  return html
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, ' ')
    .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, ' ')
}

/** The visible words of a page, with Markdown link targets and code removed. */
export function visibleText(markdownOrHtml: string): string {
  return markdownOrHtml
    .replace(/<[^>]+>/g, ' ')
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/`[^`]*`/g, ' ')
}

/**
 * A capitalised phrase is a candidate person name unless every word in it has been reviewed and
 * listed in the manifest's `permittedNameWords`. Checking words rather than whole phrases is what
 * keeps "Email Coach Clark" and "Whitefish Bay High School" quiet while "Jordan Rivera" is not.
 */
export function unreviewedNames(text: string, permittedWords: readonly string[]): string[] {
  const permitted = new Set(permittedWords.map((word) => word.toLowerCase()))
  const found = collect(visibleText(text), CAPITALISED_PHRASE).filter((phrase) =>
    phrase.split(/\s+/).some((word) => !permitted.has(word.toLowerCase())),
  )
  return [...new Set(found)]
}

/** Every image path a page references, normalised to the site-relative path it will be served at. */
export function referencedImages(source: string): string[] {
  return [...source.matchAll(IMAGE_REFERENCE)]
    .map((match) => match[1] ?? match[2] ?? '')
    .filter((path) => path.length > 0)
    .map((path) => path.replace(/[?#].*$/, ''))
}

export interface PolicyInput {
  pages: ContentPage[]
  settings: SiteSettings
  consent: MediaConsent
  /** Built pages, when there are any: `[{ location: '/faq/', html }]`. */
  builtPages?: Array<{ location: string; html: string }>
  /**
   * The facts the site's announcements promise, from `announcementFields()`. Left out, nothing is
   * checked, which is right for the many call sites that hand this function one page of Markdown.
   */
  announcements?: AnnouncementField[]
}

export function checkPublishingPolicy({
  pages,
  settings,
  consent,
  builtPages = [],
  announcements = [],
}: PolicyInput): PolicyReport {
  const errors: PolicyFinding[] = []
  const warnings: PolicyFinding[] = []
  const allowedAddresses = new Set(
    settings.contactEmails.map((contact) => contact.address.toLowerCase()),
  )
  const consentedImagePaths = new Set(consent.images.map((image) => image.path))
  const nonPersonImagePaths = new Set(consent.nonPersonImages.map((image) => image.path))
  const consentedNames = new Map(
    consent.students.map((student) => [student.publishedName.toLowerCase(), student]),
  )

  // Every consent entry is for the current season and has been checked since the season began.
  for (const student of consent.students) {
    if (isStale(student, consent.season)) {
      warnings.push({
        location: 'content/media-consent.yaml',
        message:
          `consent for "${student.publishedName}" was last checked ${student.dateChecked} for ` +
          `season ${student.season}; the start-of-season check for ${consent.season} has not ` +
          'been recorded. Confirm it with the activities office and update dateChecked.',
      })
    }
  }
  for (const image of consent.images) {
    if (isStale(image, consent.season)) {
      warnings.push({
        location: 'content/media-consent.yaml',
        message:
          `consent for image ${image.path} was last checked ${image.dateChecked} for season ` +
          `${image.season}; the start-of-season check for ${consent.season} has not been ` +
          'recorded. Confirm it with the activities office and update dateChecked.',
      })
    }
  }

  const sources: Array<{ location: string; text: string; raw: string | null }> = [
    // guardedHtml, not html: a page's lead and its at-a-glance values live in the front matter
    // and are rendered by the route module rather than by Prose, and they are published copy
    // exactly as a paragraph is. Reading html alone would leave the guard blind to the part of a
    // page that carries its most important facts.
    ...pages.map((page) => ({ location: page.filePath, text: page.guardedHtml, raw: null })),
    ...builtPages.map((page) => ({
      location: page.location,
      text: withoutScripts(page.html),
      raw: page.html,
    })),
  ]

  for (const { location, text, raw } of sources) {
    for (const address of collect(text, EMAIL_PATTERN)) {
      if (!allowedAddresses.has(address.toLowerCase())) {
        errors.push({
          location,
          message:
            `publishes the email address "${address}", which is not in the allowlist in ` +
            'content/site.yaml. Only coach and team addresses may appear on this site.',
        })
      }
    }

    for (const phone of collect(text, PHONE_PATTERN)) {
      errors.push({
        location,
        message: `publishes what looks like a phone number ("${phone.trim()}"). The site publishes none.`,
      })
    }

    for (const image of referencedImages(text)) {
      if (!consentedImagePaths.has(image) && !nonPersonImagePaths.has(image)) {
        errors.push({
          location,
          message:
            `references the image ${image}, which has no entry in content/media-consent.yaml. ` +
            'Add a consent entry for an image of a person, or a nonPersonImages entry for one ' +
            'with nobody in it.',
        })
      }
    }

    for (const name of unreviewedNames(text, consent.permittedNameWords)) {
      const entry = consentedNames.get(name.toLowerCase())
      if (!entry) {
        errors.push({
          location,
          message:
            `names "${name}", which has no entry in content/media-consent.yaml. If this is a ` +
            'student, add a consent entry confirmed with the activities office for season ' +
            `${consent.season}. If it is not a person, add its words to permittedNameWords.`,
        })
      } else if (isStale(entry, consent.season)) {
        errors.push({
          location,
          message:
            `names "${name}", whose consent entry is for season ${entry.season}, checked ` +
            `${entry.dateChecked}. Consent does not carry over between seasons.`,
        })
      }
    }

    if (raw !== null) {
      for (const tag of [
        ...collect(raw, CROSS_ORIGIN_SCRIPT),
        ...collect(raw, CROSS_ORIGIN_IFRAME),
      ]) {
        errors.push({
          location,
          message: `loads something from another origin: ${tag.trim()}`,
        })
      }
      for (const tag of collect(raw, ANY_IFRAME)) {
        errors.push({ location, message: `contains an iframe, which this site does not use: ${tag}` })
      }
    }
  }

  // An announcement states every fact it lists. A [[TBD]] marker catches this in prose, where
  // the missing fact is a hole in a sentence; in a panel built from fields there is no sentence
  // to leave a hole in, so a fact nobody has supplied is simply a field with nothing in it, and
  // nothing in the copy says so. These findings are that missing signal. A room of "To be
  // announced" passes here, because that is an answer; an unset one does not, because it is not.
  for (const field of announcements) {
    if (field.unsetNote === null) {
      continue
    }
    errors.push({
      location: field.location,
      message:
        `the ${field.label} of the "${field.announcement}" announcement is still unset ` +
        `("${field.unsetNote}"). Replace unsetNote with the value, or, if not knowing is the ` +
        'answer, with a value that says so such as "To be announced".',
    })
  }

  for (const page of pages) {
    for (const note of page.placeholders) {
      errors.push({
        location: page.filePath,
        message: note
          ? `still has an unfilled placeholder: ${note}`
          : 'still has an unfilled placeholder',
      })
    }
  }

  return { errors, warnings }
}

function format(findings: PolicyFinding[]): string {
  return findings.map((finding) => `  ${finding.location}: ${finding.message}`).join('\n')
}

/**
 * Next builds the layout once per route, in several workers, so without this the same finding
 * would be printed a dozen times and the real output would scroll away. Each distinct block is
 * printed once per process.
 */
const alreadyReported = new Set<string>()

function reportOnce(heading: string, findings: PolicyFinding[]): void {
  const block = `${heading}\n${format(findings)}`
  if (alreadyReported.has(block)) {
    return
  }
  alreadyReported.add(block)
  console.warn(block)
}

/** Test-only: forget what has been printed, so a later test sees its own output. */
export function resetPolicyReporting(): void {
  alreadyReported.clear()
}

/** Thrown by the build when content breaks the publishing policy. */
export class PublishingPolicyError extends Error {
  readonly findings: PolicyFinding[]

  constructor(findings: PolicyFinding[]) {
    super(
      `Content breaks docs/policies/website-publishing.md and cannot be published:\n${format(findings)}`,
    )
    this.name = 'PublishingPolicyError'
    this.findings = findings
  }
}

/**
 * The build guard. A prod build stops on any error; a dev build prints them so a preview still
 * comes up with the placeholders visible on the page, which is how Charlie reviews the copy.
 * Warnings print in both.
 */
export function enforcePublishingPolicy(
  input: PolicyInput,
  env: NodeJS.ProcessEnv = process.env,
): PolicyReport {
  const report = checkPublishingPolicy(input)
  if (report.warnings.length > 0) {
    reportOnce('Publishing policy warnings:', report.warnings)
  }
  if (report.errors.length === 0) {
    return report
  }
  if (readSiteEnvironment(env) === 'prod') {
    throw new PublishingPolicyError(report.errors)
  }
  reportOnce('Publishing policy problems, which will fail a prod build:', report.errors)
  return report
}
