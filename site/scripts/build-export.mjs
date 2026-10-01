#!/usr/bin/env node
/**
 * Build the static export and record what it was built from, so the export checks in tests/export/
 * can tell that site/out/ belongs to the tree under test (see export-fingerprint.mjs).
 *
 *     node site/scripts/build-export.mjs
 *
 * It runs `pnpm build` with this process's environment, so SITE_ENV and the other settings in
 * site/README.md apply exactly as they do to a plain build, and it can be run from anywhere in the
 * repository. site/scripts/pre-commit-checks.sh, and so CI, builds through this.
 *
 * The previous record is deleted before the build starts, so a failed or interrupted build leaves
 * no record vouching for whatever is in site/out/. The sources are fingerprinted before and after
 * the build, and if they differ (an edit saved mid-build, or the build rewriting one of its own
 * inputs) no record is written either: nobody could say which of the two trees the export is from.
 */

import { spawnSync } from 'node:child_process'
import { mkdirSync, rmSync, writeFileSync } from 'node:fs'
import { dirname } from 'node:path'

import {
  BUILD_RECORD_PATH,
  SITE_DIRECTORY,
  differences,
  exportFingerprint,
  sourceFingerprint,
} from './export-fingerprint.mjs'

rmSync(BUILD_RECORD_PATH, { force: true })

const before = sourceFingerprint()

const build = spawnSync('pnpm', ['build'], { cwd: SITE_DIRECTORY, stdio: 'inherit' })
if (build.status !== 0) {
  console.error(`site export: pnpm build failed${build.error ? ` (${build.error.message})` : ''}.`)
  process.exit(build.status ?? 1)
}

const after = sourceFingerprint()
if (after.digest !== before.digest) {
  console.error('site export: the sources changed while the build ran, so no record was written:')
  for (const line of differences(before.files, after.files)) console.error(`    ${line}`)
  console.error('Run the build again once nothing is being edited.')
  process.exit(1)
}

const exported = exportFingerprint()
mkdirSync(dirname(BUILD_RECORD_PATH), { recursive: true })
writeFileSync(
  BUILD_RECORD_PATH,
  `${JSON.stringify({ builtAt: new Date().toISOString(), source: before, export: exported }, null, 2)}\n`,
)
console.log(`site export: recorded ${exported.fileCount} exported files against source ${before.digest.slice(0, 12)}.`)
