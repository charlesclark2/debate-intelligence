import { describe, expect, it, vi } from 'vitest'

import RootLayout from '@/app/layout'
import type * as PublishingPolicy from '@/lib/publishing-policy'
import type { PolicyInput } from '@/lib/publishing-policy'
import { loadSchedule } from '@/lib/tournaments'

import { siteRootWith } from './content-fixture'

/**
 * What the build's publishing-policy guard is actually handed (src/app/layout.tsx).
 *
 * tests/content-policy.test.ts checks the shipped content with the same lists the layout builds,
 * but by building them itself, so the layout could stop passing a file to the guard and every
 * test there would still pass. A mutation run in v1-e37-t02 showed exactly that: removing the
 * schedule files from the layout's list left the suite green. This calls the layout and reads
 * the argument the guard received.
 *
 * The layout is built twice: over the content the site ships, where every tournament is checked
 * for being handed over whatever the coach has put in the file, and over the synthetic season in
 * tests/fixtures/season/, where the fields handed over are counted by hand (v1-e37-t10).
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

/** Builds the layout, over `siteRoot`'s content when one is given, and returns what the guard got. */
function guardInputs(siteRoot?: string): PolicyInput[] {
  received.inputs = []
  const cwd = siteRoot === undefined ? null : vi.spyOn(process, 'cwd').mockReturnValue(siteRoot)
  try {
    RootLayout({ children: null })
  } finally {
    cwd?.mockRestore()
  }
  return received.inputs
}

const filePaths = (inputs: PolicyInput[]) => inputs.flatMap((input) => input.pages.map((page) => page.filePath))

describe('the root layout runs the publishing-policy guard over every file with copy', () => {
  const inputs = guardInputs()
  const guarded = filePaths(inputs)

  it('runs the guard once per layout build', () => {
    expect(inputs).toHaveLength(1)
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

  it('hands the guard every text field of every tournament the site ships, named by entry and field', () => {
    // Worked out from the tournaments' own fields, not from tournamentTextFields(), so a field that
    // function stopped returning would be missing here.
    for (const tournament of loadSchedule().tournaments) {
      const entry = `content/tournaments.yaml, tournament "${tournament.id}" (entry ${tournament.position})`
      const split = tournament.arrangements.length > 1
      const fields = [
        'name',
        ...tournament.arrangements.flatMap((arrangement, index) =>
          arrangement.where === null ? [] : [split ? `byEvent.${index}.where` : 'where'],
        ),
        ...(tournament.condition === null ? [] : ['condition']),
        ...(tournament.notes === null ? [] : ['notes']),
      ]
      for (const field of fields) {
        expect(guarded).toContain(`${entry}, field ${field}`)
      }
    }
  })
})

describe('the guard is handed the schedule and results field by field, counted on the synthetic season', () => {
  const guarded = filePaths(guardInputs(siteRootWith()))

  it('hands the guard each kind of tournament field, named by entry and field', () => {
    expect(guarded).toContain('content/tournaments.yaml, tournament "granite-falls-2026" (entry 3), field notes')
    expect(guarded).toContain('content/tournaments.yaml, tournament "lantern-hill-home-2026" (entry 1), field condition')
    expect(guarded).toContain('content/tournaments.yaml, tournament "pine-hollow-2026" (entry 8), field byEvent.1.where')
    expect(guarded).toContain('content/tournaments.yaml, tournament "harbor-point-online-2026" (entry 2), field name')
  })

  it('hands the guard every one of them: 12 names, 11 places, 1 condition and 5 notes', () => {
    expect(guarded.filter((path) => path.startsWith('content/tournaments.yaml, '))).toHaveLength(29)
  })

  it('hands the guard every result, and the words around them', () => {
    expect(guarded.filter((path) => path.startsWith('content/results.yaml, ')).sort()).toEqual([
      'content/results.yaml, labels',
      'content/results.yaml, result 1 (Birchwood Invitational, 2026-10-17)',
      'content/results.yaml, result 2 (Birchwood Invitational, 2026-10-17)',
      'content/results.yaml, result 3 (lakeshore-2026)',
      'content/results.yaml, result 4 (Ashford, 2026-10-03)',
      'content/results.yaml, result 5 (northwoods-2026)',
    ])
  })
})
