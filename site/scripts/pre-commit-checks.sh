#!/usr/bin/env bash
#
# Lint, type-check, test and build the public team site.
#
# Run by the `site-checks` pre-commit hook whenever anything under site/ changes, and safe to run
# by hand from anywhere in the repository:
#
#     site/scripts/pre-commit-checks.sh
#
# Everything it runs is offline. Next telemetry is disabled by the package scripts, the test suite
# fails any call to fetch, and the build reads only files in this directory. It needs no AWS
# credentials and no network, but it does need site/node_modules: run `pnpm --dir site install`
# once per clone.
#
# Node and pnpm are not uv dependencies; they come from the developer's machine and from the CI
# runner's setup steps, so this script says what is missing rather than failing obscurely.

set -euo pipefail

site_directory="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! command -v pnpm > /dev/null 2>&1; then
  echo "site checks: pnpm is not on PATH." >&2
  echo "  Install it with: npm install -g pnpm@10.15.0" >&2
  echo "  (corepack 0.30.0 cannot fetch pnpm: its npm signing key has expired.)" >&2
  exit 1
fi

if [ ! -d "${site_directory}/node_modules" ]; then
  echo "site checks: site/node_modules is missing. Run: pnpm --dir site install" >&2
  exit 1
fi

# The build runs as a dev build on purpose: it is the environment that must emit the
# disallow-everything robots.txt, and a developer's machine is never producing production files.
export SITE_ENV="${SITE_ENV:-dev}"

for task in lint typecheck test build; do
  echo "site checks: pnpm --dir site ${task}"
  pnpm --dir "${site_directory}" "${task}"
done
