<!--
Hotfix: hotfix/<slug> into main, for an urgent production fix. A hotfix gets no exception to
"validated in dev": the hotfix head is deployed to dev by a manual workflow_dispatch and needs a
green validate-dev run and Charlie's approval before it merges, like any promotion.
https://github.com/charlesclark2/debate-intelligence/blob/dev/docs/process/branching-and-environments.md

The promotion-source check fails while the "Dev build:" or "validate-dev run:" line below is
blank, and runs again whenever this description is edited. Guidance sits in comments like this
one, so a line holding only its comment still counts as blank.

Before v1-e01-t09 (dev pre-releases) and v1-e01-t10 (validate-dev) have merged, neither a build
nor a run exists yet. Say so on the line and say what was checked instead; the check refuses a
blank line, not an honest one.
-->

## Incident

Incident: <!-- link to the issue, or what broke, since when, and who is affected -->

## Fix

<!-- What this changes and why it is the smallest safe fix. -->

## Validation in dev

Dev build: <!-- id of the workflow_dispatch dev pre-release (V1) or dev deploy (V2+) of this hotfix head -->
validate-dev run: <!-- link to the green validate-dev run for this hotfix head -->

## Back-merge

When this merges, the back-merge workflow opens a "Back-merge main → dev" pull request. Merge it
into `dev` the same day with **Create a merge commit** (a squash leaves main's commits unreachable
from dev). Until it merges, the `back-merge` check fails on every promotion from dev. It does not
block another hotfix.

## Checklist

- [ ] `ci`, `promotion-source` and `back-merge` are green (`back-merge` passes for hotfix heads by design)
- [ ] The dev build and the validate-dev run are for the hotfix head commit this pull request merges
- [ ] Charlie has approved this hotfix
- [ ] Merge with **Create a merge commit**, never squash or rebase
- [ ] The back-merge pull request is merged into `dev` with a merge commit the same day
- [ ] **Every promotion pull request already open against `main` has had its checks re-run.** A
      promotion PR opened before this hotfix keeps a stale green `back-merge`: merging into `main`
      does not re-run checks on PRs already open against it, GitHub has no "base branch moved"
      event, and strict mode is deliberately off. Until something re-runs it, that promotion can
      merge and put a combination on prod that dev never validated. Re-run the job, or edit the
      PR description to retrigger. Reproduced in the sandbox during `v1-e01-t08`; the mechanical
      fix is `v1-e01-t12`.
