/**
 * What an export in site/out/ was built from, and whether that is still the tree in front of us.
 *
 * The export checks in tests/export/ read site/out/, the files CloudFront serves. Until
 * v1-e36-t10 they were written `runIf(hasExport)`, and site/out/ is gitignored, so they had two
 * ways to say something false. On a clean CI runner there was no export, all of them skipped and
 * the suite reported green having checked nothing. On a developer's machine there was whatever
 * export the last build happened to leave, and they checked those bytes: on 2026-09-30 that meant
 * four failures against a correct tree, and it would as readily have meant passes against a wrong
 * one.
 *
 * So a build made through build-export.mjs records two fingerprints beside it:
 *
 *   source  every file under site/ that git sees (tracked, or untracked and not ignored), minus
 *           tests/, which the build never reads, plus any site/.env* file, which Next does read
 *           although the repository ignores it; and every SITE_* and NEXT_PUBLIC_* variable in
 *           the build's environment;
 *   export  every file the build wrote into site/out/.
 *
 * assertFreshExport() recomputes both and refuses to let the export checks run unless they match:
 * no export, an export nobody recorded, an export from other sources or another environment, and
 * an export changed after it was built are all failures, each saying which. Nothing here can make
 * a check skip.
 *
 * The record lives in site/node_modules/.cache/, not in site/out/, so it can never be synced to
 * the bucket with the site.
 */

import { spawnSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, join, relative, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

export const SITE_DIRECTORY = join(dirname(fileURLToPath(import.meta.url)), '..')
export const EXPORT_DIRECTORY = join(SITE_DIRECTORY, 'out')
export const BUILD_RECORD_PATH = join(SITE_DIRECTORY, 'node_modules', '.cache', 'site-export-build.json')

/** The command that builds an export the checks will accept, as a developer would type it. */
export const BUILD_COMMAND = 'node site/scripts/build-export.mjs'

/** Directories under site/ the build never reads, so editing them does not stale the export. */
const NOT_BUILD_INPUTS = ['tests/']

/** Build-time settings: the four SITE_* variables in site/README.md and anything Next inlines. */
const BUILD_VARIABLE = /^(?:SITE_|NEXT_PUBLIC_)/

/** The reason the export checks cannot run against what is in site/out/. */
export class ExportFreshnessError extends Error {
  constructor(message) {
    super(message)
    this.name = 'ExportFreshnessError'
  }
}

function sha256(content) {
  return createHash('sha256').update(content).digest('hex')
}

function digestOf(entries) {
  return sha256(
    Object.entries(entries)
      .map(([key, value]) => `${key}\0${value}\n`)
      .join(''),
  )
}

/** Paths relative to site/, '/'-separated, sorted. */
function buildInputPaths(siteDirectory) {
  const listing = spawnSync('git', ['ls-files', '-z', '--cached', '--others', '--exclude-standard'], {
    cwd: siteDirectory,
    encoding: 'utf8',
  })
  if (listing.status !== 0) {
    throw new ExportFreshnessError(
      `could not list the site sources with git, so there is no way to tell what an export was built from.\n${listing.stderr ?? listing.error}`,
    )
  }
  const environmentFiles = readdirSync(siteDirectory).filter((entry) => entry.startsWith('.env'))
  return [...new Set([...listing.stdout.split('\0').filter(Boolean), ...environmentFiles])]
    .filter((path) => !NOT_BUILD_INPUTS.some((excluded) => path.startsWith(excluded)))
    // A tracked file deleted from the working tree is still listed; its absence is the change.
    .filter((path) => existsSync(join(siteDirectory, path)))
    .sort()
}

/** The sources and build settings an export made now would come from. */
export function sourceFingerprint(environment = process.env, siteDirectory = SITE_DIRECTORY) {
  const files = Object.fromEntries(
    buildInputPaths(siteDirectory).map((path) => [path, sha256(readFileSync(join(siteDirectory, path)))]),
  )
  const variables = Object.fromEntries(
    Object.keys(environment)
      .filter((name) => BUILD_VARIABLE.test(name))
      .sort()
      .map((name) => [name, environment[name] ?? '']),
  )
  return { digest: digestOf({ ...files, ...variables }), files, variables }
}

function filesUnder(directory) {
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry)
    return statSync(path).isDirectory() ? filesUnder(path) : [path]
  })
}

/** Every file in an export, by content. */
export function exportFingerprint(exportDirectory = EXPORT_DIRECTORY) {
  const files = Object.fromEntries(
    filesUnder(exportDirectory)
      .map((path) => relative(exportDirectory, path).split(sep).join('/'))
      .sort()
      .map((path) => [path, sha256(readFileSync(join(exportDirectory, path)))]),
  )
  return { digest: digestOf(files), fileCount: Object.keys(files).length }
}

/** Added, removed and changed keys between two maps, for an error a person can act on. */
export function differences(before, after) {
  const names = [...new Set([...Object.keys(before), ...Object.keys(after)])].sort()
  return names.flatMap((name) => {
    if (!(name in before)) return [`added    ${name}`]
    if (!(name in after)) return [`removed  ${name}`]
    return before[name] === after[name] ? [] : [`changed  ${name}`]
  })
}

function listed(lines, limit = 12) {
  const shown = lines.slice(0, limit).map((line) => `    ${line}`)
  if (lines.length > limit) shown.push(`    ...and ${lines.length - limit} more`)
  return shown.join('\n')
}

/**
 * Throws ExportFreshnessError unless site/out/ holds an export that build-export.mjs made from
 * exactly the sources and settings in front of us, and nothing has touched it since.
 */
export function assertFreshExport({
  environment = process.env,
  siteDirectory = SITE_DIRECTORY,
  exportDirectory = join(siteDirectory, 'out'),
  recordPath = join(siteDirectory, 'node_modules', '.cache', 'site-export-build.json'),
} = {}) {
  const rebuild = `Build one with: ${BUILD_COMMAND}\n(site/scripts/pre-commit-checks.sh does this before it runs the export checks.)`

  if (!existsSync(join(exportDirectory, 'index.html'))) {
    throw new ExportFreshnessError(
      `There is no export in site/out/, so the export checks have nothing to check.\n` +
        `They fail rather than skip, because a skipped check reports green while checking nothing.\n${rebuild}`,
    )
  }
  if (!existsSync(recordPath)) {
    throw new ExportFreshnessError(
      `site/out/ was not built by site/scripts/build-export.mjs, so nothing records which sources it came from ` +
        `and it may be left over from another commit.\n${rebuild}`,
    )
  }

  const record = JSON.parse(readFileSync(recordPath, 'utf8'))
  const now = sourceFingerprint(environment, siteDirectory)
  if (record.source?.digest !== now.digest) {
    const changes = [
      ...differences(record.source?.files ?? {}, now.files),
      ...differences(record.source?.variables ?? {}, now.variables).map((line) => `${line} (environment)`),
    ]
    throw new ExportFreshnessError(
      `site/out/ is stale: it was built from different sources or settings than the tree under test.\n` +
        `Since it was built:\n${listed(changes)}\n${rebuild}`,
    )
  }

  const built = exportFingerprint(exportDirectory)
  if (record.export?.digest !== built.digest) {
    throw new ExportFreshnessError(
      `site/out/ has changed since build-export.mjs built it (another build, or an edit by hand), ` +
        `so it is not known to come from this tree.\n${rebuild}`,
    )
  }

  return { builtAt: record.builtAt, fileCount: built.fileCount }
}
