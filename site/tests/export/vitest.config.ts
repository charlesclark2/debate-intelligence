import { fileURLToPath } from 'node:url'

import { defineConfig } from 'vitest/config'

import siteConfig from '../../vitest.config'

/**
 * The export checks: the tests that read site/out/, the files CloudFront actually serves, rather
 * than the sources they are built from.
 *
 * They are a suite of their own, run after the build, because the alternative costs the inner
 * loop: `pnpm --dir site test` has to work straight after an edit, and if it read the export it
 * would need a rebuild first on every run. So `pnpm test` reads only sources, and this suite runs
 * second, from site/scripts/export-checks.sh, which builds first. site/scripts/pre-commit-checks.sh
 * calls that, and CI calls pre-commit-checks.sh.
 *
 * Their files are named *.export-test.ts(x) so the source suite's tests/**\/*.test.ts pattern
 * never picks them up. Each reads the export through built-export.ts, which throws on import
 * unless site/out/ is an export of the tree under test, so a missing or stale export fails every
 * file with the reason and nothing here can skip. (A vitest globalSetup could say it once, but
 * vitest then also reports "No test files found", which points the reader at the wrong problem.)
 */
export default defineConfig({
  ...siteConfig,
  root: fileURLToPath(new URL('../..', import.meta.url)),
  test: {
    ...siteConfig.test,
    include: ['tests/export/**/*.export-test.ts', 'tests/export/**/*.export-test.tsx'],
  },
})
