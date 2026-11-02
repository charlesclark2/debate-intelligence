import type { AnnouncementField, ContentPage, SiteSettings } from './content'
import type { MediaConsent } from './media-consent'
import { isReferenceToCome, isStale } from './media-consent'
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
  /**
   * The rule in docs/policies/website-publishing.md the problem breaks, such as "Students 6", so
   * the person fixing it can read why. Left out for a house-style finding, which is the site's
   * own rule rather than the policy's.
   */
  rule?: string
}

/** Where every finding's rule is written. */
export const POLICY_DOCUMENT = 'docs/policies/website-publishing.md'


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
 * One capitalised word: a capital and at least one lower-case letter, with an apostrophe inside
 * it, so O'Brien, O'Neill and Clark's are each one word. Until v1-e37-t03 the capital after an
 * apostrophe ended the word, so a name like O'Neill was reported as "O'".
 */
const CAPITALISED_WORD = String.raw`[A-Z](?:[a-z]+(?:['’][A-Z]?[a-z]+)*|['’][A-Z]?[a-z]+)`

/**
 * Runs of two or more capitalised words, which is what a person's name looks like in prose. The
 * match is greedy so "Martin Luther King" is one candidate rather than two overlapping ones. A
 * single space or newline separates the words: a blank line ends the phrase, so a heading and the
 * paragraph under it are never read as one name.
 */
const CAPITALISED_PHRASE = new RegExp(
  String.raw`\b${CAPITALISED_WORD}(?:\s(?!\s)${CAPITALISED_WORD})+['’]?\b`,
  'g',
)

function collect(text: string, pattern: RegExp): string[] {
  return [...text.matchAll(pattern)].map((match) => match[0])
}

/**
 * Every email address and phone number in a piece of text, whatever the allowlist says.
 * content/results.yaml uses it: a result is about a student, so no address belongs in one, not
 * even a coach's (docs/policies/website-publishing.md, Students 6).
 */
export function contactDetails(text: string): string[] {
  return [...collect(text, EMAIL_PATTERN), ...collect(text, PHONE_PATTERN)].map((found) => found.trim())
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

/**
 * Inline formatting, which sits inside a run of words rather than between blocks. Dropped without
 * a gap, so `<strong>Jordan</strong> Rivera` is read as the one name a visitor sees; every other
 * tag ends the run, so a heading never runs into the paragraph under it.
 */
const INLINE_TAG = /^<\/?(?:a|abbr|b|cite|code|em|i|mark|q|s|small|span|strong|sub|sup|u)\b[^>]*>$/i

/**
 * The attributes a visitor reads as text: an image's alt text, which a screen reader speaks and a
 * browser shows when the image does not load, and a title, which is a Markdown image's caption and
 * a link's tooltip. Each is published copy, read as a run of its own (v1-e37-t03).
 */
const READABLE_ATTRIBUTE = /\b(?:alt|title)\s*=\s*(?:"([^"]*)"|'([^']*)')/gi

/** A Markdown link or image, with the title a Markdown image uses as its caption. */
const MARKDOWN_LINK = /\[([^\]]*)\]\([^)\s]*(?:\s+(?:"([^"]*)"|'([^']*)'))?\s*\)/g

const NAMED_ENTITIES: Readonly<Record<string, string>> = {
  amp: '&',
  lt: '<',
  gt: '>',
  quot: '"',
  apos: "'",
  nbsp: ' ',
}

/**
 * The characters a renderer escapes, back as a visitor reads them. The Markdown renderer writes
 * O'Neill as `O&#39;Neill`, which no run of capitalised words matches, so without this a name
 * with an apostrophe passed the name rules in every rendered page.
 */
function decodeEntities(text: string): string {
  return text.replace(/&(?:#(\d+)|#x([0-9a-f]+)|([a-z]+));/gi, (entity, decimal, hex, name) => {
    if (decimal !== undefined) {
      return String.fromCodePoint(Number.parseInt(decimal as string, 10))
    }
    if (hex !== undefined) {
      return String.fromCodePoint(Number.parseInt(hex as string, 16))
    }
    return NAMED_ENTITIES[(name as string).toLowerCase()] ?? entity
  })
}

/** Each readable attribute in one tag, as a run of its own, or a blank line for a tag with none. */
function readTag(tag: string): string {
  const readable = [...tag.matchAll(READABLE_ATTRIBUTE)].map((match) => match[1] ?? match[2] ?? '')
  if (readable.length > 0) {
    return `\n\n${readable.join('\n\n')}\n\n`
  }
  return INLINE_TAG.test(tag) ? '' : '\n\n'
}

/**
 * The words a visitor reads on a page: its text, its images' alt text and captions, and its links'
 * titles, with Markdown link targets and code removed and escaped characters decoded.
 */
export function visibleText(markdownOrHtml: string): string {
  return decodeEntities(
    markdownOrHtml
      .replace(/<[^>]+>/g, readTag)
      .replace(MARKDOWN_LINK, (_link, text: string, doubleQuoted?: string, singleQuoted?: string) => {
        const caption = doubleQuoted ?? singleQuoted
        return caption === undefined ? text : `${text}\n\n${caption}\n\n`
      })
      .replace(/`[^`]*`/g, ' '),
  )
}

/** Lower case, with a typographic apostrophe folded to a plain one, for comparing names. */
function fold(text: string): string {
  return text.toLowerCase().replace(/’/g, "'")
}

/**
 * True when the whole run of words can be covered, end to end, by entries from the allowlist.
 *
 * Longest match is not enough on its own: "Blue Valley West" is covered by one entry, and
 * "Whitefish Bay High School" by two, so the covering has to be searched rather than chosen
 * greedily. This walks positions left to right and marks each one reachable, which is a match if
 * and only if the last position is reached. Every word has to be inside some entry, so a single
 * unreviewed word anywhere in the phrase leaves it uncovered, which is the property the guard
 * depends on.
 */
function isCoveredByPhrases(words: string[], permitted: ReadonlySet<string>, longest: number): boolean {
  const reachable = new Set<number>([0])
  for (let start = 0; start < words.length; start += 1) {
    if (!reachable.has(start)) {
      continue
    }
    for (let length = 1; length <= longest && start + length <= words.length; length += 1) {
      if (permitted.has(words.slice(start, start + length).join(' '))) {
        reachable.add(start + length)
      }
    }
  }
  return reachable.has(words.length)
}

/**
 * A capitalised phrase is a candidate person name unless it is covered, word for word, by the
 * phrases in the manifest's `permittedNamePhrases`. That is what keeps "Email Coach Clark" and
 * "Whitefish Bay High School" quiet while "Jordan Rivera" is not.
 *
 * Phrases rather than the bare words this used to check (the v1-e36-t07 review). A word list has
 * to admit every word of every reviewed name separately, so reviewing "Blue Valley West High
 * School" and "Olathe North High School" left North, West, Blue and Valley permitted on their
 * own, anywhere, for ever. A student called Blue or West would have passed, and each later name
 * loosened the guard again for the prose after it. An entry here permits the words only in the
 * order they were reviewed in, so the list can grow without the guard weakening.
 */
export function unreviewedNames(text: string, permittedPhrases: readonly string[]): string[] {
  const permitted = new Set(permittedPhrases.map(fold))
  const longest = Math.max(1, ...permittedPhrases.map((phrase) => phrase.trim().split(/\s+/).length))
  const found = collect(visibleText(text), CAPITALISED_PHRASE).filter(
    (phrase) => !isCoveredByPhrases(fold(phrase).split(/\s+/), permitted, longest),
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
  const consentedImages = new Map(consent.images.map((image) => [image.path, image]))
  const nonPersonImagePaths = new Set(consent.nonPersonImages.map((image) => image.path))
  const consentedNames = new Map(
    consent.students.map((student) => [student.publishedName.toLowerCase(), student]),
  )

  // Every consent entry is for the current season and was last checked within it (isStale).
  // A student's entry is named by its consent reference, never by the name: warnings are printed
  // in every build, and a build log carries no student name (Students 10).
  for (const student of consent.students) {
    if (isStale(student, consent.season)) {
      warnings.push({
        location: 'content/media-consent.yaml',
        message:
          `consent ${student.consentReference} was last checked ${student.dateChecked} for ` +
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
          rule: 'Students 6',
        })
      }
    }

    for (const phone of collect(text, PHONE_PATTERN)) {
      errors.push({
        location,
        message: `publishes what looks like a phone number ("${phone.trim()}"). The site publishes none.`,
        rule: 'Students 6',
      })
    }

    // An image of a person publishes only against a current-season form, as a name does: "current"
    // is isStale's, the same test the name rule below applies, and a reference still to come is
    // no form at all (v1-e37-t12). The finding names the image by its path, never who it shows.
    for (const image of referencedImages(text)) {
      const entry = consentedImages.get(image)
      if (entry && isReferenceToCome(entry.consentReference)) {
        errors.push({
          location,
          message:
            `references the image ${image}, whose consent reference is still to come. An image ` +
            'of a person publishes only against a form the activities office has confirmed.',
          rule: 'Photos and media consent 1 and 4',
        })
      } else if (entry && isStale(entry, consent.season)) {
        errors.push({
          location,
          message:
            `references the image ${image}, whose consent entry is for season ${entry.season}, ` +
            `checked ${entry.dateChecked}. Consent does not carry over between seasons: confirm ` +
            `the form for ${consent.season} and update the entry.`,
          rule: 'Photos and media consent 1 and 11',
        })
      } else if (!entry && !nonPersonImagePaths.has(image)) {
        errors.push({
          location,
          message:
            `references the image ${image}, which has no entry in content/media-consent.yaml. ` +
            'Add a consent entry for an image of a person, or a nonPersonImages entry for one ' +
            'with nobody in it.',
          rule: 'Photos and media consent 4',
        })
      }
    }

    for (const name of unreviewedNames(text, consent.permittedNamePhrases)) {
      const entry = consentedNames.get(name.toLowerCase())
      if (!entry) {
        errors.push({
          location,
          message:
            `names "${name}", which has no entry in content/media-consent.yaml. If this is a ` +
            'student, add a consent entry confirmed with the activities office for season ' +
            `${consent.season}. If it is not a person, add the whole phrase to ` +
            'permittedNamePhrases.',
          rule: 'Students 1 and 2',
        })
      } else if (isStale(entry, consent.season)) {
        errors.push({
          location,
          message:
            `names "${name}", whose consent entry is for season ${entry.season}, checked ` +
            `${entry.dateChecked}. Consent does not carry over between seasons.`,
          rule: 'Students 2; Consent renewal and the start-of-season check 1',
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
          rule: 'Analytics and third parties 5 and 6',
        })
      }
      for (const tag of collect(raw, ANY_IFRAME)) {
        errors.push({
          location,
          message: `contains an iframe, which this site does not use: ${tag}`,
          rule: 'Analytics and third parties 6',
        })
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

/** One finding as the build prints it: where, what, and the policy rule when there is one. */
export function describeFinding(finding: PolicyFinding): string {
  const rule = finding.rule === undefined ? '' : ` (${POLICY_DOCUMENT}, ${finding.rule})`
  return `${finding.location}: ${finding.message}${rule}`
}

function format(findings: PolicyFinding[]): string {
  return findings.map((finding) => `  ${describeFinding(finding)}`).join('\n')
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
