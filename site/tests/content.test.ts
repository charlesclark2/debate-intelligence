import { cpSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { afterEach, describe, expect, it } from 'vitest'

import {
  ContentValidationError,
  EVENT_COMPARISON_FIELDS,
  HOME_SLUG,
  assertNoExcludedEvidence,
  homeContentAsPage,
  loadGuardedContent,
  loadHomeContent,
  loadEventsContent,
  loadFaqContent,
  loadNotFoundPage,
  loadPages,
  loadRoutedPages,
  loadSiteSettings,
} from '@/lib/content'
import { loadMediaConsent } from '@/lib/media-consent'
import { PublishingPolicyError, enforcePublishingPolicy } from '@/lib/publishing-policy'

const fixture = (name: string) => join(process.cwd(), 'tests/fixtures', name)
const siteContent = join(process.cwd(), 'content')

describe('loading the published pages', () => {
  it('orders pages by navOrder and leaves drafts out of the export', () => {
    const pages = loadPages(fixture('ordering'))
    expect(pages.map((page) => page.slug)).toEqual(['home', 'alpha', 'zulu'])
    expect(pages.map((page) => page.slug)).not.toContain('unfinished')
  })

  it('routes the home page at the root and every other page under its slug', () => {
    const pages = loadPages(fixture('ordering'))
    expect(pages.find((page) => page.slug === HOME_SLUG)?.route).toBe('/')
    expect(pages.find((page) => page.slug === 'alpha')?.route).toBe('/alpha/')
  })

  it('falls back to the title when a page sets no navLabel', () => {
    const pages = loadPages(fixture('ordering'))
    expect(pages.find((page) => page.slug === 'alpha')?.navLabel).toBe('Alpha')
    expect(pages.find((page) => page.slug === 'zulu')?.navLabel).toBe('Zulu fixture')
  })

  it('renders the Markdown body to HTML at build time', () => {
    const zulu = loadPages(fixture('ordering')).find((page) => page.slug === 'zulu')
    expect(zulu?.html).toContain('<h2>A heading</h2>')
    expect(zulu?.html).toContain('<a href="/">link</a>')
  })

  it('keeps the home page out of the /<slug>/ routes', () => {
    expect(loadRoutedPages(fixture('ordering')).map((page) => page.slug)).toEqual(['alpha', 'zulu'])
  })

  it('validates the 404 copy with the same schema, outside pages/', () => {
    const notFound = loadNotFoundPage(fixture('ordering'))
    expect(notFound.title).toBe('Page not found fixture')
    expect(loadPages(fixture('ordering')).map((page) => page.slug)).not.toContain('not-found')
  })
})

describe('front matter validation', () => {
  it('fails, naming the file, when a page has no title', () => {
    expect(() => loadPages(fixture('missing-title'))).toThrowError(ContentValidationError)
    expect(() => loadPages(fixture('missing-title'))).toThrowError(
      /content\/pages\/broken\.md: invalid front matter \(.*title/,
    )
  })

  it('fails, naming the file, when a page has no description', () => {
    expect(() => loadPages(fixture('missing-description'))).toThrowError(
      /content\/pages\/broken\.md: invalid front matter \(.*description/,
    )
  })

  it('names the offending file on the error object as well as in the message', () => {
    try {
      loadPages(fixture('missing-title'))
      expect.unreachable('loadPages should have thrown')
    } catch (error) {
      expect(error).toBeInstanceOf(ContentValidationError)
      expect((error as ContentValidationError).filePath).toBe('content/pages/broken.md')
    }
  })
})

describe('house style', () => {
  it('rejects an em dash in body copy and points at the line', () => {
    expect(() => loadPages(fixture('em-dash'))).toThrowError(
      /content\/pages\/dash\.md: line 6 uses an em dash/,
    )
  })

  it('rejects an acronym that the page never spells out', () => {
    expect(() => loadPages(fixture('unexpanded-acronym'))).toThrowError(
      /content\/pages\/events\.md: uses "NSDA" without spelling it out/,
    )
  })
})

describe('the site settings file', () => {
  it('reads the strings the layout needs', () => {
    const settings = loadSiteSettings(fixture('ordering'))
    expect(settings.navigationLabel).toBe('Main')
    expect(settings.skipLinkLabel).toBe('Skip to main content')
  })

  it('fails, naming the file, when the settings file is missing', () => {
    expect(() => loadSiteSettings(fixture('em-dash'))).toThrowError(
      /content\/site\.yaml: file is missing/,
    )
  })
})

describe('the content this site actually ships', () => {
  it('passes every schema and house-style rule', () => {
    const pages = loadPages(siteContent)
    expect(pages.length).toBeGreaterThan(0)
    for (const page of pages) {
      expect(page.title.length).toBeGreaterThan(0)
      expect(page.description.length).toBeGreaterThan(0)
    }
    expect(() => loadNotFoundPage(siteContent)).not.toThrow()
    expect(() => loadSiteSettings(siteContent)).not.toThrow()
  })

  it('has a home page, which is what the root route renders', () => {
    expect(loadPages(siteContent).map((page) => page.slug)).toContain(HOME_SLUG)
  })
})

/**
 * The two structured content files v1-e36-t07 added (acceptance criterion 5).
 *
 * The point of moving the FAQ and the events copy out of one run of Markdown and into YAML is
 * that the shape of the page becomes something a schema can hold Charlie to: a question always
 * has an answer, an event always fills all four comparison fields, and a page where everything
 * is open by default is not a page anyone can scan. So the loader has to fail, and fail naming
 * the file, rather than let a half-filled file reach a build.
 */
describe('the grouped FAQ content', () => {
  it('reads the topics, their questions and the most-asked ones out of content/faq.yaml', () => {
    const faq = loadFaqContent(siteContent)
    expect(faq.groups.length).toBeGreaterThanOrEqual(2)
    expect(faq.indexTitle.length).toBeGreaterThan(0)

    const questions = faq.groups.flatMap((group) => group.questions)
    // The sixteen from the approved draft, plus anything later reviews added. The roster that
    // proves none of the sixteen was lost is in tests/faq.test.tsx.
    expect(questions.length).toBeGreaterThanOrEqual(16)
    for (const question of questions) {
      expect(question.question.length, 'a question with no text').toBeGreaterThan(0)
      expect(question.answerHtml, question.question).toContain('<p>')
    }

    const open = questions.filter((question) => question.openByDefault)
    expect(open.length).toBeGreaterThanOrEqual(2)
    expect(open.length).toBeLessThanOrEqual(3)
  })

  it('gives every topic an anchor id the in-page index can link to, and no two the same', () => {
    const ids = loadFaqContent(siteContent).groups.map((group) => group.id)
    expect(new Set(ids).size).toBe(ids.length)
    for (const id of ids) {
      expect(id).toMatch(/^[a-z][a-z0-9-]*$/)
    }
  })

  it('fails, naming the file, when a question has no answer', () => {
    expect(() => loadFaqContent(fixture('faq-missing-answer'))).toThrowError(
      ContentValidationError,
    )
    expect(() => loadFaqContent(fixture('faq-missing-answer'))).toThrowError(
      /content\/faq\.yaml: invalid FAQ content \(.*answer/,
    )
  })

  it('fails, naming the file, when every question is marked most-asked', () => {
    expect(() => loadFaqContent(fixture('faq-everything-open'))).toThrowError(
      /content\/faq\.yaml: invalid FAQ content \(.*openByDefault/,
    )
  })

  it('fails, naming the file, when content/faq.yaml is missing altogether', () => {
    expect(() => loadFaqContent(fixture('ordering'))).toThrowError(
      /content\/faq\.yaml: file is missing/,
    )
  })
})

describe('the events comparison content', () => {
  it('reads the three events and all four comparison fields out of content/events.yaml', () => {
    const events = loadEventsContent(siteContent)
    expect(events.events.map((event) => event.id)).toEqual([
      'public-forum',
      'lincoln-douglas',
      'policy',
    ])
    for (const event of events.events) {
      for (const field of EVENT_COMPARISON_FIELDS) {
        expect(event.comparison[field].length, `${event.name}.${field}`).toBeGreaterThan(0)
      }
      expect(event.detailHtml, event.name).toContain('<p>')
    }
    for (const section of events.closingSections) {
      expect(section.bodyHtml, section.title).toContain('<p>')
    }
  })

  it('fails, naming the file, when an event is missing a comparison field', () => {
    expect(() => loadEventsContent(fixture('events-missing-field'))).toThrowError(
      ContentValidationError,
    )
    expect(() => loadEventsContent(fixture('events-missing-field'))).toThrowError(
      /content\/events\.yaml: invalid events content \(.*topicCadence/,
    )
  })

  it('names the offending file on the error object as well as in the message', () => {
    try {
      loadEventsContent(fixture('events-missing-field'))
      expect.unreachable('loadEventsContent should have thrown')
    } catch (error) {
      expect(error).toBeInstanceOf(ContentValidationError)
      expect((error as ContentValidationError).filePath).toBe('content/events.yaml')
    }
  })

  it('fails, naming the file, when content/events.yaml is missing altogether', () => {
    expect(() => loadEventsContent(fixture('ordering'))).toThrowError(
      /content\/events\.yaml: file is missing/,
    )
  })
})

/**
 * The academic case, the excluded evidence category and the entry-point labels (v1-e36-t09
 * acceptance criteria 2 to 5).
 *
 * Each case copies the content this site actually ships into a temporary directory and breaks
 * exactly one thing, so a failure here is about that one thing and not about a fixture that has
 * drifted from the real file. Nothing leaves the machine: the copy is on local disk and is
 * deleted after each test.
 */
describe('the academic case and the entry points, when content/home.yaml is wrong', () => {
  const copies: string[] = []

  afterEach(() => {
    for (const directory of copies.splice(0)) {
      rmSync(directory, { recursive: true, force: true })
    }
  })

  /** A copy of site/content with `edit` applied to one file in it. */
  function contentWith(fileName: string, edit: (source: string) => string): string {
    const directory = mkdtempSync(join(tmpdir(), 'site-content-'))
    copies.push(directory)
    cpSync(siteContent, directory, { recursive: true })
    const path = join(directory, fileName)
    const original = readFileSync(path, 'utf8')
    const edited = edit(original)
    expect(edited, `the edit to ${fileName} changed nothing`).not.toBe(original)
    writeFileSync(path, edited)
    return directory
  }

  const home = loadHomeContent(siteContent)
  const firstClaim = home.academicCase.claims[0]!

  /** Replaces the first claim's source block in home.yaml with `replacement`. */
  function withFirstSource(replacement: string): string {
    return contentWith('home.yaml', (source) =>
      source.replace(/\n {6}source:\n(?: {8}.*\n)+/, replacement),
    )
  }

  it('ships at least one claim, each with a source object', () => {
    expect(home.academicCase.claims.length).toBeGreaterThan(0)
    for (const claim of home.academicCase.claims) {
      expect(typeof claim.source, claim.title).toBe('object')
    }
  })

  it('fails, naming the file, on a claim with no source', () => {
    const directory = withFirstSource('\n')
    expect(() => loadHomeContent(directory)).toThrowError(ContentValidationError)
    expect(() => loadHomeContent(directory)).toThrowError(
      /content\/home\.yaml: invalid home content \(academicCase\.claims\.0\.source: every claim needs a source/,
    )
  })

  it('fails on a source that leaves out what was measured', () => {
    const directory = contentWith('home.yaml', (source) =>
      source.replace(/\n {8}measured: >-\n(?: {10}.*\n)+/, '\n'),
    )
    expect(() => loadHomeContent(directory)).toThrowError(
      /content\/home\.yaml: invalid home content \(academicCase\.claims\.0\.source: a source needs authors, publication, year and measured \(measured: /,
    )
  })

  it('fails on a source written as text that is not the [[TBD: source]] marker', () => {
    const directory = withFirstSource("\n      source: 'A study I remember reading'\n")
    expect(() => loadHomeContent(directory)).toThrowError(
      /academicCase\.claims\.0\.source: a source written as text must be the \[\[TBD: source\]\] marker/,
    )
  })

  it('fails on a source link that is not https', () => {
    const directory = contentWith('home.yaml', (source) =>
      source.replace(
        '        year: 2025\n',
        '        year: 2025\n        href: http://example.org/study\n',
      ),
    )
    expect(() => loadHomeContent(directory)).toThrowError(
      /academicCase\.claims\.0\.source\.href: an external source link must start with "https:\/\/"/,
    )
  })

  it('accepts an https source link once externalLinkNote is set', () => {
    const directory = contentWith('home.yaml', (source) =>
      source.replace(
        '        year: 2025\n',
        '        year: 2025\n        href: https://example.org/study\n',
      ),
    )
    expect(loadHomeContent(directory).academicCase.claims[0]?.source).toMatchObject({
      href: 'https://example.org/study',
    })
  })

  it('fails on a source link when nothing says the link leaves the team site', () => {
    const directory = contentWith('home.yaml', (source) =>
      source
        .replace(/\n {2}externalLinkNote: .*\n/, '\n')
        .replace('        year: 2025\n', '        year: 2025\n        href: https://example.org/study\n'),
    )
    expect(() => loadHomeContent(directory)).toThrowError(/externalLinkNote must say/)
  })

  it('accepts a claim waiting on its source, marked [[TBD: source]]', () => {
    const directory = withFirstSource("\n      source: '[[TBD: source]]'\n")
    expect(loadHomeContent(directory).academicCase.claims[0]?.source).toBe('[[TBD: source]]')
  })

  it('names the claim when its source is still [[TBD: source]]', () => {
    const directory = withFirstSource("\n      source: '[[TBD: source]]'\n")
    expect(homeContentAsPage(directory).placeholders).toEqual([
      `source for the academic-case claim "${firstClaim.title}"`,
    ])
  })

  /**
   * Acceptance criterion 3: no unsourced claim can reach prod. This is the build guard exactly as
   * src/app/layout.tsx calls it, with SITE_ENV set as a prod build sets it.
   */
  it('fails a prod build, naming the file and the claim, while a source is still [[TBD: source]]', () => {
    const directory = withFirstSource("\n      source: '[[TBD: source]]'\n")
    const input = {
      pages: loadGuardedContent(directory),
      settings: loadSiteSettings(directory),
      consent: loadMediaConsent(directory),
    }
    const prod = { ...process.env, SITE_ENV: 'prod' }
    expect(() => enforcePublishingPolicy(input, prod)).toThrowError(PublishingPolicyError)
    expect(() => enforcePublishingPolicy(input, prod)).toThrowError(
      new RegExp(
        `content/home\\.yaml: still has an unfilled placeholder: source for the academic-case claim "${firstClaim.title}"`,
      ),
    )
  })

  it('lets a dev build through with the same marker, so the preview shows the gap', () => {
    const directory = withFirstSource("\n      source: '[[TBD: source]]'\n")
    const input = {
      pages: loadGuardedContent(directory),
      settings: loadSiteSettings(directory),
      consent: loadMediaConsent(directory),
    }
    const report = enforcePublishingPolicy(input, { ...process.env, SITE_ENV: 'dev' })
    expect(report.errors.map((error) => error.message).join('\n')).toMatch(
      /unfilled placeholder: source for the academic-case claim/,
    )
  })

  it('fails on an em dash in a claim, like anywhere else on the site', () => {
    const directory = contentWith('home.yaml', (source) =>
      source.replace('Students already doing well still gain', 'Students already doing well \u2014 still gain'),
    )
    expect(() => loadHomeContent(directory)).toThrowError(/content\/home\.yaml: uses an em dash/)
  })

  it('fails on an acronym in a claim that the page never spells out', () => {
    const directory = contentWith('home.yaml', (source) =>
      source.replace('taking part in policy debate', 'taking part in NSDA policy debate').replace(
        'Taking part in policy debate',
        'Taking part in NSDA policy debate',
      ),
    )
    expect(() => loadHomeContent(directory)).toThrowError(
      /content\/home\.yaml: uses "NSDA" without spelling it out/,
    )
  })

  it('fails, naming the card, on an entry-point card that points at no page', () => {
    const directory = contentWith('home.yaml', (source) =>
      source.replace('      href: /coaches/\n', '      href: /coaching-staff/\n'),
    )
    expect(() => loadHomeContent(directory)).toThrowError(
      /content\/home\.yaml: the entry-point card "Coaches" links to \/coaching-staff\/, which is not a published page/,
    )
  })

  it('fails, naming the card and the page, on a card labelled differently from its destination', () => {
    const directory = contentWith('home.yaml', (source) =>
      source.replace('    - title: Coaches\n', '    - title: Who coaches the team\n'),
    )
    expect(() => loadHomeContent(directory)).toThrowError(
      /the entry-point card "Who coaches the team" links to \/coaches\/, whose title is "Coaches" \(content\/pages\/coaches\.md\)/,
    )
  })

  it('fails when a destination page is renamed and the card is not', () => {
    const directory = contentWith('pages/coaches.md', (source) =>
      source.replace('title: Coaches\n', 'title: Our coaches\n'),
    )
    expect(() => loadHomeContent(directory)).toThrowError(
      /the entry-point card "Coaches" links to \/coaches\/, whose title is "Our coaches"/,
    )
  })
})

/**
 * The evidence category the brand guide excludes (v1-e36-t09 acceptance criterion 4). The check
 * reads every Markdown and YAML file in content/, and fails naming the file and the line.
 */
describe('the excluded evidence category', () => {
  const copies: string[] = []

  afterEach(() => {
    for (const directory of copies.splice(0)) {
      rmSync(directory, { recursive: true, force: true })
    }
  })

  function contentWithLineAppended(fileName: string, line: string): string {
    const directory = mkdtempSync(join(tmpdir(), 'site-content-'))
    copies.push(directory)
    cpSync(siteContent, directory, { recursive: true })
    const path = join(directory, fileName)
    writeFileSync(path, `${readFileSync(path, 'utf8').replace(/\n*$/, '\n')}${line}\n`)
    return directory
  }

  function lineCount(fileName: string): number {
    return readFileSync(join(siteContent, fileName), 'utf8').replace(/\n*$/, '\n').split('\n')
      .length
  }

  it('finds none of it in the content this site ships', () => {
    expect(() => assertNoExcludedEvidence(siteContent)).not.toThrow()
  })

  it.each([
    ['graduation rate', 'home.yaml', '# Debaters had a higher graduation rate.'],
    ['graduation-rate', 'faq.yaml', '# graduation-rate research'],
    ['dropout', 'pages/about.md', 'Debaters had a lower dropout rate.'],
    ['drop-out', 'events.yaml', '# the drop-out figures'],
    ['at risk', 'pages/join.md', 'Debate helps students at risk of falling behind.'],
    ['at-risk', 'home.yaml', '# at-risk students'],
  ])('fails on "%s", naming the file and the line', (words, fileName, line) => {
    const directory = contentWithLineAppended(fileName, line)
    const expectedLine = lineCount(fileName)
    expect(() => assertNoExcludedEvidence(directory)).toThrowError(ContentValidationError)
    expect(() => assertNoExcludedEvidence(directory)).toThrowError(
      `content/${fileName}: line ${expectedLine} uses "${words}"`,
    )
  })

  it('runs as part of the build, through the guarded content the layout loads', () => {
    const directory = contentWithLineAppended('pages/about.md', 'A lower dropout rate.')
    expect(() => loadGuardedContent(directory)).toThrowError(/content\/pages\/about\.md: line \d+ uses "dropout"/)
  })

  it('does not trip on ordinary words that merely contain the letters', () => {
    const directory = contentWithLineAppended(
      'pages/about.md',
      'Graduation is in June. Students drop off forms at the office; the risk is low.',
    )
    expect(() => assertNoExcludedEvidence(directory)).not.toThrow()
  })
})
