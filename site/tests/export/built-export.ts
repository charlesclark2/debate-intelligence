import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

import { EXPORT_DIRECTORY, assertFreshExport } from '../../scripts/export-fingerprint.mjs'

/**
 * site/out/, for the export checks, and only once it is known to be built from this tree.
 *
 * Every file in tests/export/ reads the export through this module, and importing it throws
 * unless site/out/ holds an export that site/scripts/build-export.mjs made from exactly the
 * sources and settings under test (scripts/export-fingerprint.mjs says how that is decided). So an
 * export check cannot skip when there is no export, and cannot pass against one left over from
 * another commit, whichever command happens to load it.
 */
assertFreshExport()

export const exportDirectory = EXPORT_DIRECTORY

/** The exported HTML for a page slug; home is the root index. */
export function exportedPagePath(slug: string): string {
  return slug === 'home' ? join(exportDirectory, 'index.html') : join(exportDirectory, slug, 'index.html')
}

/** A file in the export, by its path relative to site/out/. */
export function readExported(path: string): string {
  return readFileSync(join(exportDirectory, path), 'utf8')
}

/** Every top-level page in the export, `/` included, as its route and the path to its HTML. */
export function builtPageFiles(): Array<{ location: string; path: string }> {
  return readdirSync(exportDirectory, { withFileTypes: true })
    .filter((entry) => entry.isDirectory() && entry.name !== '_next')
    .map((entry) => ({ location: `/${entry.name}/`, path: join(exportDirectory, entry.name, 'index.html') }))
    .filter((entry) => existsSync(entry.path))
    .concat([{ location: '/', path: join(exportDirectory, 'index.html') }])
}

/**
 * Every file in the export, by its path relative to site/out/: HTML, the React payloads, the
 * bundles, stylesheets, the sitemap, icons. Not filtered by extension, so a file type nobody
 * thought of cannot drop out of a check that claims the whole export.
 */
export function exportedFiles(directory: string = exportDirectory): string[] {
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry)
    return statSync(path).isDirectory() ? exportedFiles(path) : [relative(exportDirectory, path)]
  })
}
