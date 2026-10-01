import { spawnSync } from 'node:child_process'
import { mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, relative } from 'node:path'

import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import {
  BUILD_RECORD_PATH,
  EXPORT_DIRECTORY,
  ExportFreshnessError,
  assertFreshExport,
  exportFingerprint,
  sourceFingerprint,
} from '../scripts/export-fingerprint.mjs'

/**
 * The export checks run, against an export of this tree, or the run fails (v1-e36-t10).
 *
 * Until v1-e36-t10 the tests that read site/out/ were written `runIf(hasExport)` and ran inside
 * `pnpm test`, which CI runs before the build. On a clean runner there was never an export, so
 * every one of them skipped and the suite reported green: the allowlist check on published
 * addresses and the third-party-script check had never run in CI. On a developer's machine they
 * read whatever export was lying around, and on 2026-09-30 failed four times against a correct
 * tree because it predated the change.
 *
 * Those tests are now the export suite in tests/export/, run by site/scripts/export-checks.sh
 * straight after a build. This file is the part of the fix that runs on every `pnpm test`, with
 * no build: it pins the freshness check that suite depends on, and it fails if the arrangement
 * that makes the suite run is taken apart, so the next person to reorder a script finds out on
 * their next test run rather than a year later.
 */

const SITE = process.cwd()

describe('the freshness check the export suite depends on', () => {
  let site: string

  /** A throwaway site/: a git repository with one source file, a build record and an export. */
  function writeSite() {
    site = mkdtempSync(join(tmpdir(), 'site-export-'))
    spawnSync('git', ['init', '--quiet'], { cwd: site })
    writeFileSync(join(site, '.gitignore'), 'out/\nnode_modules/\n')
    mkdirSync(join(site, 'content'))
    writeFileSync(join(site, 'content', 'contact.md'), 'Write to charles.clark@wfbschools.com.\n')
    mkdirSync(join(site, 'tests'))
    writeFileSync(join(site, 'tests', 'a.test.ts'), '// not a build input\n')
    mkdirSync(join(site, 'out'))
    writeFileSync(join(site, 'out', 'index.html'), '<p>charles.clark@wfbschools.com</p>')
  }

  const environment = { SITE_ENV: 'dev', HOME: '/home/someone' }
  const recordPath = () => join(site, 'node_modules', '.cache', 'site-export-build.json')

  /** What build-export.mjs writes after a build. */
  function recordBuild() {
    mkdirSync(join(site, 'node_modules', '.cache'), { recursive: true })
    writeFileSync(
      recordPath(),
      JSON.stringify({
        builtAt: '2026-09-30T12:00:00.000Z',
        source: sourceFingerprint(environment, site),
        export: exportFingerprint(join(site, 'out')),
      }),
    )
  }

  const check = (env: Record<string, string | undefined> = environment) =>
    assertFreshExport({ environment: env, siteDirectory: site, recordPath: recordPath() })

  beforeEach(() => {
    writeSite()
  })

  afterEach(() => {
    rmSync(site, { recursive: true, force: true })
  })

  it('accepts an export recorded against exactly this tree and these settings', () => {
    recordBuild()
    expect(check()).toMatchObject({ fileCount: 1 })
  })

  it('accepts it again on a second run: the same bytes from the same tree are still right', () => {
    recordBuild()
    check()
    expect(check()).toMatchObject({ fileCount: 1 })
  })

  it('fails, rather than skips, when there is no export at all', () => {
    rmSync(join(site, 'out'), { recursive: true })
    expect(check).toThrowError(ExportFreshnessError)
    expect(check).toThrowError(/no export in site\/out\/.*\n.*fail rather than skip/)
  })

  it('fails on an export nothing recorded, which may be from any commit', () => {
    expect(check).toThrowError(/was not built by site\/scripts\/build-export\.mjs/)
  })

  it('fails on an export built before a source changed, naming the file', () => {
    recordBuild()
    writeFileSync(join(site, 'content', 'contact.md'), 'Write to debate@wfbschools.com.\n')
    expect(check).toThrowError(/stale[\s\S]*changed {2}content\/contact\.md/)
  })

  it('fails when a source file is added or deleted after the build', () => {
    recordBuild()
    writeFileSync(join(site, 'content', 'faq.md'), 'New.\n')
    expect(check).toThrowError(/added {4}content\/faq\.md/)
    rmSync(join(site, 'content', 'faq.md'))
    rmSync(join(site, 'content', 'contact.md'))
    expect(check).toThrowError(/removed {2}content\/contact\.md/)
  })

  it('fails when the export was built with other settings, naming the variable', () => {
    recordBuild()
    expect(() => check({ ...environment, SITE_DEBATER_LOGIN: 'on' })).toThrowError(
      /added {4}SITE_DEBATER_LOGIN \(environment\)/,
    )
    expect(() => check({ ...environment, SITE_ENV: 'prod' })).toThrowError(
      /changed {2}SITE_ENV \(environment\)/,
    )
  })

  it('ignores variables the build does not read', () => {
    recordBuild()
    expect(() => check({ ...environment, HOME: '/somewhere/else' })).not.toThrow()
  })

  it('reads a site/.env file as a build input even though git ignores it', () => {
    writeFileSync(join(site, '.gitignore'), 'out/\nnode_modules/\n.env*\n')
    recordBuild()
    writeFileSync(join(site, '.env.local'), 'SITE_DEBATER_LOGIN=on\n')
    expect(check).toThrowError(/added {4}\.env\.local/)
  })

  it('does not count the tests as build inputs, so editing an export check needs no rebuild', () => {
    recordBuild()
    writeFileSync(join(site, 'tests', 'a.test.ts'), '// edited\n')
    expect(check).not.toThrow()
  })

  it('fails when the export itself changed after it was recorded', () => {
    recordBuild()
    writeFileSync(join(site, 'out', 'index.html'), '<p>debate@wfbschools.com</p>')
    expect(check).toThrowError(/site\/out\/ has changed since build-export\.mjs built it/)
  })
})

describe('the export suite is wired in, and nothing in the site tests can skip', () => {
  function filesUnder(directory: string): string[] {
    return readdirSync(directory).flatMap((entry) => {
      const path = join(directory, entry)
      if (statSync(path).isDirectory()) return entry === 'fixtures' ? [] : filesUnder(path)
      return /\.tsx?$/.test(entry) ? [path] : []
    })
  }

  const testFiles = filesUnder(join(SITE, 'tests')).filter((path) => path !== join(SITE, 'tests', 'export-checks-run.test.ts'))
  const exportChecks = testFiles.filter((path) => /\.export-test\.tsx?$/.test(path))

  /**
   * A conditional or unconditional skip is how the export checks went silent, and it is the same
   * failure wherever it is written. An early `return` inside a test is the same thing again; it
   * is harder to spot mechanically and is left to review.
   */
  it('has no runIf, skipIf, skip, todo or only in any site test', () => {
    const skipping = /\.(?:runIf|skipIf|skip|todo|only)\s*\(/
    for (const path of testFiles) {
      expect(readFileSync(path, 'utf8'), relative(SITE, path)).not.toMatch(skipping)
    }
  })

  /**
   * A test elsewhere that reads site/out/ without skipping simply fails on a clean runner, which
   * is loud; the rule that matters is that each export check goes through the freshness check.
   */
  it('reads the export only through built-export.ts in every export check', () => {
    expect(exportChecks.length).toBeGreaterThanOrEqual(10)
    for (const path of exportChecks) {
      expect(readFileSync(path, 'utf8'), relative(SITE, path)).toMatch(/from '\.\/built-export'/)
    }
  })

  it('runs the export suite from pre-commit-checks.sh, after the source tests', () => {
    const script = readFileSync(join(SITE, 'scripts/pre-commit-checks.sh'), 'utf8')
    const commands = script.split('\n').filter((line) => !line.trimStart().startsWith('#'))
    const sourceTests = commands.findIndex((line) => /for task in lint typecheck test; do/.test(line))
    const exportChecksLine = commands.findIndex((line) => /scripts\/export-checks\.sh"?\s*$/.test(line))
    expect(sourceTests, 'pre-commit-checks.sh no longer runs lint, typecheck and test').toBeGreaterThanOrEqual(0)
    expect(exportChecksLine, 'pre-commit-checks.sh no longer runs export-checks.sh').toBeGreaterThan(sourceTests)
  })

  it('builds before it checks in export-checks.sh, and checks with the export suite config', () => {
    const commands = readFileSync(join(SITE, 'scripts/export-checks.sh'), 'utf8')
      .split('\n')
      .filter((line) => !line.trimStart().startsWith('#'))
    const build = commands.findIndex((line) => line.includes('scripts/build-export.mjs'))
    const checks = commands.findIndex((line) => line.includes('--config tests/export/vitest.config.ts'))
    expect(build).toBeGreaterThanOrEqual(0)
    expect(checks).toBeGreaterThan(build)
  })

  it('is what CI runs for the site', () => {
    const workflow = readFileSync(join(SITE, '../.github/workflows/ci.yml'), 'utf8')
    expect(workflow).toMatch(/run: site\/scripts\/pre-commit-checks\.sh/)
  })
})

describe('the build record never ships', () => {
  it('lives outside site/out/, so syncing the export to the bucket cannot publish it', () => {
    expect(relative(EXPORT_DIRECTORY, BUILD_RECORD_PATH)).toMatch(/^\.\.\//)
  })
})
