import { describe, expect, it, vi } from 'vitest'

import RootLayout from '@/app/layout'
import type * as PublishingPolicy from '@/lib/publishing-policy'
import type { PolicyInput } from '@/lib/publishing-policy'

/**
 * What the build's publishing-policy guard is actually handed (src/app/layout.tsx).
 *
 * tests/content-policy.test.ts checks the shipped content with the same lists the layout builds,
 * but by building them itself, so the layout could stop passing a file to the guard and every
 * test there would still pass. A mutation run in v1-e37-t02 showed exactly that: removing the
 * schedule files from the layout's list left the suite green. This calls the layout and reads
 * the argument the guard received.
 */

const received = vi.hoisted(() => ({ inputs: [] as PolicyInput[] }))

vi.mock('@/lib/publishing-policy', async (importOriginal) => {
  const actual = await importOriginal<typeof PublishingPolicy>()
  return {
    ...actual,
    enforcePublishingPolicy: (input: PolicyInput) => {
      received.inputs.push(input)
      return actual.enforcePublishingPolicy(input)
    },
  }
})

describe('the root layout runs the publishing-policy guard over every file with copy', () => {
  RootLayout({ children: null })
  const guarded = received.inputs.flatMap((input) => input.pages.map((page) => page.filePath))

  it('runs the guard once per layout build', () => {
    expect(received.inputs).toHaveLength(1)
  })

  it.each([
    'content/pages/home.md',
    'content/pages/schedule.md',
    'content/home.yaml',
    'content/faq.yaml',
    'content/events.yaml',
    'content/email-updates.json',
    'content/schedule.yaml',
  ])('hands the guard %s', (filePath) => {
    expect(guarded).toContain(filePath)
  })

  it('hands the guard every text field of every tournament, named by entry and field', () => {
    expect(guarded).toContain('content/tournaments.yaml, tournament "glenbrooks-2026" (entry 10), field notes')
    expect(guarded).toContain(
      'content/tournaments.yaml, tournament "whitefish-bay-home-2026" (entry 11), field condition',
    )
    expect(guarded.filter((path) => path.startsWith('content/tournaments.yaml, ')).length).toBeGreaterThanOrEqual(20)
  })
})
