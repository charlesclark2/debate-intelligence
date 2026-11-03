import { cpSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { contentWith } from './content-fixture'

/**
 * Fixture content for the announcement tests: tests/content-fixture.ts's synthetic season with
 * content/announcements/ replaced, either by one of the sets in tests/fixtures/announcements/ or
 * by files written inline.
 *
 * Every name here is invented, as docs/policies/website-publishing.md (Students 11) requires of
 * a test: the real announcements live in site/content/ and nowhere else, and no test reads them for
 * an entry, so the tests do not change when the coach adds, expires or removes one (v1-e37-t10).
 */

export const ANNOUNCEMENT_FIXTURES = join(process.cwd(), 'tests/fixtures/announcements')

/** A fixture set's folder name, or files to write: file name to file text. */
export type AnnouncementFiles = string | Record<string, string>

/** A content directory with these announcements in place of the shipped ones. */
export function announcementsContent(
  files: AnnouncementFiles,
  edits: Record<string, (source: string) => string> = {},
): string {
  const directory = contentWith(edits)
  const target = join(directory, 'announcements')
  rmSync(target, { recursive: true, force: true })
  mkdirSync(target)
  if (typeof files === 'string') {
    cpSync(join(ANNOUNCEMENT_FIXTURES, files), target, { recursive: true })
  } else {
    for (const [name, source] of Object.entries(files)) {
      writeFileSync(join(target, name), source)
    }
  }
  return directory
}

/** The same, as a site root, for a test that renders a page reading process.cwd()/content. */
export function announcementsSiteRoot(files: AnnouncementFiles): string {
  const root = mkdtempSync(join(tmpdir(), 'site-root-'))
  cpSync(announcementsContent(files), join(root, 'content'), { recursive: true })
  return root
}

/** One announcement file: front matter from `fields`, in order, then the body. */
export function announcementFile(
  fields: Record<string, string>,
  body = 'Practice is on as usual this week, in the library after school.',
): string {
  const front = Object.entries(fields).map(([key, value]) => `${key}: ${value}`)
  return ['---', ...front, '---', '', body, ''].join('\n')
}

/** A valid announcement, with any field replaced or added. */
export function validAnnouncement(fields: Record<string, string> = {}, body?: string): string {
  return announcementFile({ title: 'Practice is on as usual', date: '2026-10-20', ...fields }, body)
}
