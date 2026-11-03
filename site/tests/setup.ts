import { cleanup } from '@testing-library/react'
import { afterEach, beforeEach, vi } from 'vitest'

import { TEST_BUILD_DATE } from './build-date'

declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean
}

/**
 * React only suppresses its "update not wrapped in act" warning when it can see that it is
 * running inside a test environment; vitest does not set this flag for us.
 */
globalThis.IS_REACT_ACT_ENVIRONMENT = true

/**
 * jsdom implements no IntersectionObserver. next/link looks for one to decide when a link has
 * scrolled into view, and without it the component settles its internal state on a later tick,
 * outside act(), which fills the test output with React warnings. This inert stub never reports
 * an intersection, which is the correct answer in a window that does not scroll, and keeps the
 * output clean so a real warning from our own components is visible.
 */
class InertIntersectionObserver implements IntersectionObserver {
  readonly root = null
  readonly rootMargin = ''
  readonly thresholds: ReadonlyArray<number> = []
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
  takeRecords(): IntersectionObserverEntry[] {
    return []
  }
}

// Assigned rather than stubbed: vi.unstubAllGlobals() in afterEach would strip a stub after
// the first test in the file.
globalThis.IntersectionObserver = InertIntersectionObserver

/**
 * The suite is offline by construction: every fixture is a file under tests/fixtures/ or
 * site/content/. This stub turns any stray fetch into a loud failure rather than a hung test or
 * a real request, which is what docs/process/working-agreements.md §1 asks of PR-path tests.
 */
beforeEach(() => {
  // Every test builds the site as of one fixed day, so none reads the clock (tests/build-date.ts).
  // vi.unstubAllEnvs() below restores it after each test, and the next test sets it again.
  vi.stubEnv('SITE_BUILD_DATE', TEST_BUILD_DATE)
  vi.stubGlobal('fetch', () => {
    throw new Error('Network access is not allowed in the site test suite')
  })
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
})
