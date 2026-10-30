/**
 * Edits to a tournaments.yaml, for the schedule tests. The content directories they apply to are
 * tests/content-fixture.ts's: the synthetic season in tests/fixtures/season/, so an id named here
 * is a fixture entry and never one the coach may take off the shipped schedule.
 */

/** The tournaments.yaml block for one entry, from its `- id:` line to the line before the next. */
export function editEntry(id: string, edit: (block: string) => string): (source: string) => string {
  return (source) => {
    const start = source.indexOf(`  - id: ${id}\n`)
    if (start < 0) {
      throw new Error(`editEntry: no entry "${id}"`)
    }
    const next = source.indexOf('\n  - id: ', start + 1)
    const end = next < 0 ? source.length : next + 1
    return source.slice(0, start) + edit(source.slice(start, end)) + source.slice(end)
  }
}
