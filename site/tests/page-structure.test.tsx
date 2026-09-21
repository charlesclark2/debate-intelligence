import { render, screen, within } from '@testing-library/react'
import { act } from 'react'
import { describe, expect, it } from 'vitest'

import ContentPageRoute from '@/app/[slug]/page'
import { SiteFrame } from '@/components/SiteFrame'
import type { ContentPage } from '@/lib/content'
import { loadPage, loadPages, loadSiteSettings } from '@/lib/content'

import { describeViolations, findAccessibilityViolations } from './axe'

/**
 * Summary first, detail second, on every page that is not the FAQ or the events page (task
 * v1-e36-t07 acceptance criterion 4).
 *
 * About, join, coaches and contact were each a title followed by one column of prose. None of
 * them was badly written; they were badly shaped. A parent who wanted to know when practice is,
 * or who to email, or whether their student could still join in November, had to start at the
 * top and read until they found it. These four pages do not need what the FAQ needed, but they
 * do need the same idea at their own scale: the handful of facts somebody came for, first.
 *
 * So the assertion this file exists for is the negative one, and it is deliberately blunt: a
 * page in this set whose body is one undifferentiated run of prose fails, whoever wrote it and
 * however good the prose is.
 */

/** The pages this criterion covers. The FAQ and the events page have suites of their own. */
const SUMMARY_FIRST_PAGES = ['about', 'join', 'coaches', 'contact'] as const

const settings = loadSiteSettings()
const navigationItems = loadPages().map((item) => ({ href: item.route, label: item.navLabel }))

async function renderRoute(slug: string) {
  const route = await ContentPageRoute({ params: Promise.resolve({ slug }) })
  return render(
    <SiteFrame items={navigationItems} strings={settings}>
      {route}
    </SiteFrame>,
    { container: document.body },
  )
}

/** next/link settles its internal state a microtask after mount. */
async function flushPendingEffects() {
  await act(async () => {})
}

function pageFor(slug: string): ContentPage {
  return loadPage(slug)
}

describe('every core page opens with a summary, not with prose', () => {
  /**
   * The criterion asks for "a summary or at-a-glance block", so the block is the part that is
   * required and the lead is optional beside it. Contact has no lead on purpose: its title and
   * its four ways to send an email say everything a paragraph would, and a page that explains
   * itself does not need a sentence explaining it. A page that does carry a lead has to say
   * something in it, which is what the length floor is for.
   */
  it.each(SUMMARY_FIRST_PAGES)('%s opens with a lead or goes straight to its summary', (slug) => {
    const page = pageFor(slug)
    if (page.lead !== undefined) {
      expect(page.lead.length, `${page.filePath} has a lead too short to be worth one`)
        .toBeGreaterThan(40)
    }
    expect(page.atAGlance, `${page.filePath} has neither a lead nor a summary block`).toBeDefined()
  })

  it.each(SUMMARY_FIRST_PAGES)('%s has an at-a-glance block', (slug) => {
    const page = pageFor(slug)
    expect(page.atAGlance, `${page.filePath} has no atAGlance block`).toBeDefined()
    expect(page.atAGlance!.items.length).toBeGreaterThanOrEqual(2)
    expect(page.atAGlance!.items.length).toBeLessThanOrEqual(6)
    for (const item of page.atAGlance!.items) {
      expect(item.label.trim().length, `${page.filePath} has an empty label`).toBeGreaterThan(0)
      expect(item.value.trim().length, `${page.filePath}: ${item.label}`).toBeGreaterThan(0)
    }
  })

  it.each(SUMMARY_FIRST_PAGES)('%s renders that block before its detail', async (slug) => {
    const page = pageFor(slug)
    const { container } = await renderRoute(slug)
    const bands = [...container.querySelectorAll('main > section')]

    const summaryBand = bands.findIndex((band) => band.querySelector('.at-a-glance'))
    expect(bands.length, `${page.filePath} renders no bands`).toBeGreaterThan(1)
    const detailBand = bands.findIndex((band) => band.querySelector('.prose'))
    expect(summaryBand, `${page.filePath} renders no at-a-glance block`).toBeGreaterThan(-1)
    expect(detailBand, `${page.filePath} renders no detail`).toBeGreaterThan(-1)
    expect(summaryBand, `${page.filePath} puts its detail above its summary`).toBeLessThan(
      detailBand,
    )
  })

  it.each(SUMMARY_FIRST_PAGES)('%s shows every label and value it declares', async (slug) => {
    const page = pageFor(slug)
    await renderRoute(slug)
    const list = document.querySelector('.at-a-glance') as HTMLElement
    expect(list.tagName).toBe('DL')
    const labels = [...list.querySelectorAll('dt')].map((term) => term.textContent)
    expect(labels).toEqual(page.atAGlance!.items.map((item) => item.label))
    expect(list.querySelectorAll('dd')).toHaveLength(page.atAGlance!.items.length)
  })
})

/**
 * The blunt one. "Sub-structure" means the body is broken up by something a reader's eye can
 * land on: a heading, a list, or a table. A page whose whole body is paragraphs is the shape
 * this task set out to remove, and it fails here rather than in a review.
 */
describe('no core page is one undifferentiated run of prose', () => {
  it.each(SUMMARY_FIRST_PAGES)('%s breaks its detail up', (slug) => {
    const page = pageFor(slug)
    const headings = (page.html.match(/<h[2-4]\b/g) ?? []).length
    const lists = (page.html.match(/<(?:ul|ol|table)\b/g) ?? []).length
    expect(
      headings + lists,
      `${page.filePath} is one run of prose: no heading, list or table in its body`,
    ).toBeGreaterThan(0)
    expect(headings, `${page.filePath} has no heading in its body`).toBeGreaterThan(0)
  })

  it.each(SUMMARY_FIRST_PAGES)('%s does not bury a fact its summary should carry', (slug) => {
    // A summary that repeats the first paragraph is not a summary. The lead and the at-a-glance
    // values have to differ from each other.
    const page = pageFor(slug)
    for (const item of page.atAGlance!.items) {
      expect(page.lead, `${page.filePath}: "${item.label}" simply repeats the lead`).not.toBe(
        item.value,
      )
    }
  })
})

describe('a page with no summary still renders', () => {
  /**
   * The lead and the at-a-glance block are optional, because not every page needs one: the
   * accessibility statement is a short document that is read rather than scanned. The route has
   * to render it without either, or adding an ordinary page to the site would mean writing a
   * summary block for it whether or not one helps.
   */
  it('renders the accessibility statement, which has neither', async () => {
    const page = pageFor('accessibility')
    expect(page.lead).toBeUndefined()
    expect(page.atAGlance).toBeUndefined()

    const { container } = await renderRoute('accessibility')
    expect(screen.getByRole('heading', { level: 1, name: page.title })).toBeDefined()
    expect(container.querySelector('.at-a-glance')).toBeNull()
    expect(container.querySelector('.prose')).not.toBeNull()
  })
})

describe('the summary block is accessible and correctly outlined', () => {
  it.each(SUMMARY_FIRST_PAGES)('%s has one h1 and skips no level', async (slug) => {
    await renderRoute(slug)
    expect(document.querySelectorAll('h1')).toHaveLength(1)
    const levels = [...document.querySelectorAll('h1, h2, h3, h4, h5, h6')].map((heading) =>
      Number.parseInt(heading.tagName.slice(1), 10),
    )
    for (const [index, level] of levels.entries()) {
      if (index > 0) {
        expect(level, `jumps from h${levels[index - 1]} to h${level}`).toBeLessThanOrEqual(
          (levels[index - 1] as number) + 1,
        )
      }
    }
  })

  it.each(SUMMARY_FIRST_PAGES)('%s names its summary band for a screen reader', async (slug) => {
    const page = pageFor(slug)
    await renderRoute(slug)
    const band = document.getElementById('at-a-glance')
    expect(band, `${page.filePath} summary band`).not.toBeNull()
    expect(band?.getAttribute('aria-labelledby')).toBe('at-a-glance-title')
    expect(within(band as HTMLElement).getByRole('heading', { level: 2 }).textContent).toBe(
      page.atAGlance!.title,
    )
  })

  it.each(SUMMARY_FIRST_PAGES)('%s has no WCAG 2.1 AA violation', async (slug) => {
    await renderRoute(slug)
    await flushPendingEffects()
    const violations = await findAccessibilityViolations(document.body)
    expect(violations, describeViolations(violations)).toEqual([])
  })
})
