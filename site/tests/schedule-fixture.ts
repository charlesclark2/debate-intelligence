import { cpSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

/**
 * A copy of site/content/ with some files edited, for the schedule tests.
 *
 * Every case starts from the content the site actually ships and changes one thing, so a test
 * that expects a failure fails for the edit it made and not for some unrelated gap in a
 * hand-built fixture. `edits` maps a file under content/ to a function from its text to the new
 * text; each edit must change something, so a replacement whose target has moved fails loudly
 * instead of testing the unedited file.
 */
export function contentWith(edits: Record<string, (source: string) => string>): string {
  const directory = mkdtempSync(join(tmpdir(), 'schedule-content-'))
  cpSync(join(process.cwd(), 'content'), directory, { recursive: true })
  for (const [file, edit] of Object.entries(edits)) {
    const path = join(directory, file)
    const before = readFileSync(path, 'utf8')
    const after = edit(before)
    if (after === before) {
      throw new Error(`contentWith: the edit to ${file} changed nothing`)
    }
    writeFileSync(path, after)
  }
  return directory
}

/** Replaces exactly one occurrence of `target`, failing if there is not exactly one. */
export function replaceOnce(target: string, replacement: string): (source: string) => string {
  return (source) => {
    const count = source.split(target).length - 1
    if (count !== 1) {
      throw new Error(`replaceOnce: expected one "${target}", found ${count}`)
    }
    return source.replace(target, replacement)
  }
}

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

/**
 * Glenbrooks as the 2026-09-30 schedule had it: Lincoln-Douglas and Public Forum online at school,
 * Policy in person in Glenview. Since 2026-10-22 the shipped schedule has no tournament split by
 * event (Glenbrooks is Policy only), so the byEvent tests apply this edit to the shipped content.
 */
export const splitGlenbrooksByEvent = editEntry('glenbrooks-2026', (block) =>
  replaceOnce(
    '    events: [policy]\n    held: in-person\n    where: Glenview, Illinois\n    overnight: yes\n',
    '    byEvent:\n' +
      '      - events: [lincoln-douglas, public-forum]\n' +
      '        held: online-at-school\n' +
      '        overnight: no\n' +
      '      - events: [policy]\n' +
      '        held: in-person\n' +
      '        where: Glenview, Illinois\n' +
      '        overnight: yes\n',
  )(block),
)

/**
 * A copy of the whole site's working directory layout with `content/` edited, for a test that
 * renders a page reading `process.cwd()/content`: point `process.cwd()` at the returned root.
 */
export function siteRootWith(edits: Record<string, (source: string) => string>): string {
  const root = mkdtempSync(join(tmpdir(), 'schedule-site-'))
  cpSync(contentWith(edits), join(root, 'content'), { recursive: true })
  return root
}
