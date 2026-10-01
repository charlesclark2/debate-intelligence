#!/usr/bin/env bash
#
# Build the static export, then run the export checks against it.
#
#     site/scripts/export-checks.sh
#
# The export checks (site/tests/export/) read site/out/, the files CloudFront serves: that the
# contact page carries its mailto and collects nothing, that the export publishes no address
# outside the allowlist, loads nothing from another origin and embeds no iframe, that every
# answer's full text is in the exported FAQ, and the rest of what only the built site can show.
#
# They are run here, straight after a build of the tree under test, because before v1-e36-t10
# they ran inside `pnpm test`, ahead of the build, and skipped whenever there was no export: on
# every CI runner, for as long as they had existed. Now the build records what it was built from
# (build-export.mjs) and the suite refuses to start unless site/out/ matches the tree, so a
# missing export or one left over from another commit is a failure, not a pass.
#
# site/scripts/pre-commit-checks.sh runs this after lint, typecheck and the source tests, and CI
# runs pre-commit-checks.sh. To re-run only the checks against an export this script built:
#
#     pnpm --dir site exec vitest run --config tests/export/vitest.config.ts
#
# with the same SITE_* settings the build had (this script defaults SITE_ENV to dev).

set -euo pipefail

site_directory="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# A dev build, as in pre-commit-checks.sh: the environment that must emit the disallow-everything
# robots.txt. The build records this setting and the checks compare it, so both see the same one.
export SITE_ENV="${SITE_ENV:-dev}"

echo "site checks: build the export (node site/scripts/build-export.mjs)"
node "${site_directory}/scripts/build-export.mjs"

echo "site checks: export checks against site/out/"
pnpm --dir "${site_directory}" exec vitest run --config tests/export/vitest.config.ts
