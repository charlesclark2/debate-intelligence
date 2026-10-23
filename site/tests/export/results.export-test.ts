import { existsSync, readFileSync } from 'node:fs'

import { describe, expect, it } from 'vitest'

import { RESULTS_SLUG, loadPages } from '@/lib/content'
import { loadResults, newestResults } from '@/lib/results'

import { builtPageFiles, exportedPagePath } from './built-export'

/**
 * The season's results as the build wrote them (v1-e37-t06 acceptance criteria 1 and 5): the page,
 * one anchored card per tournament with every placing under it, and the newest three on the home
 * page. tests/results.test.tsx checks the same things from the sources with fixture content; these
 * read the files CloudFront serves, built from the content that ships.
 *
 * Counts, not names: the export holds whatever students the shipped content names, and a test
 * names none of them (docs/policies/website-publishing.md, Students 11).
 */

const results = loadResults()

describe('the exported results page', () => {
  it('writes /results/', () => {
    expect(existsSync(exportedPagePath(RESULTS_SLUG))).toBe(true)
  })

  it('is one of the built pages the accessibility and content-policy passes read', () => {
    // tests/export/pages-a11y.export-test.ts sweeps loadPages(); content-policy.export-test.ts
    // sweeps builtPageFiles(). Asserted so /results/ cannot fall out of either sweep unnoticed.
    expect(loadPages().map((page) => page.slug)).toContain(RESULTS_SLUG)
    expect(builtPageFiles().map((page) => page.location)).toContain(`/${RESULTS_SLUG}/`)
  })

  it('carries one card per tournament, newest first, and every placing under it', () => {
    const html = readFileSync(exportedPagePath(RESULTS_SLUG), 'utf8')
    const anchors = [...html.matchAll(/<li class="results-group" id="([^"]+)"/g)].map((match) => match[1])
    expect(anchors).toEqual(results.groups.map((group) => group.tournament.key))
    const placings = html.match(/class="results-group__result"/g) ?? []
    expect(placings).toHaveLength(results.groups.reduce((sum, group) => sum + group.results.length, 0))
  })
})

describe('the exported home page', () => {
  it('shows the newest results, at most three, linking to /results/', () => {
    const html = readFileSync(exportedPagePath('home'), 'utf8')
    const shown = html.match(/class="recent-results__item"/g) ?? []
    expect(shown).toHaveLength(newestResults(results).length)
    if (shown.length > 0) {
      expect(html).toMatch(/id="recent-results"[\s\S]*href="\/results\/"/)
    }
  })
})
