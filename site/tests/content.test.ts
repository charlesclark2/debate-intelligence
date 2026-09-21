import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

import {
  ContentValidationError,
  EVENT_COMPARISON_FIELDS,
  HOME_SLUG,
  loadEventsContent,
  loadFaqContent,
  loadNotFoundPage,
  loadPages,
  loadRoutedPages,
  loadSiteSettings,
} from '@/lib/content'

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
