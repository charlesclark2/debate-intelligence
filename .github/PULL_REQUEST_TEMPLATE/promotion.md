<!--
Promotion: dev into main. main is production; this pull request is how validated work gets there.
The rule and what "validated in dev" means:
https://github.com/charlesclark2/debate-intelligence/blob/dev/docs/process/branching-and-environments.md

The promotion-source check fails while the "Dev build:" or "validate-dev run:" line below is
blank, and runs again whenever this description is edited. Guidance sits in comments like this
one, so a line holding only its comment still counts as blank.

Before v1-e01-t09 (dev pre-releases) and v1-e01-t10 (validate-dev) have merged, neither a build
nor a run exists yet. Say so on the line and say what was checked instead; the check refuses a
blank line, not an honest one.
-->

## Included

Release: <!-- e.g. v1.1 (plan_specs/releases/v1.1.yaml), or "none: interim promotion" -->

Tasks:
<!-- Every task merged into dev since the last promotion, one per line with its spec path.
     `git log --first-parent --oneline origin/main..origin/dev` lists the merges. -->

## Validation in dev

Dev build: <!-- pre-release tag vX.Y.Z-dev.N (V1) or dev deploy id (V2+) built from the dev head commit this merges -->
validate-dev run: <!-- link to the green validate-dev run for that same commit -->

## Evaluations

<!-- From v1.3: promotion eval results for every prompt or model change included. Before v1.3,
     "not required before v1.3". -->

## Manual checks

<!-- What automation does not cover yet, what was checked by hand, and the result. -->

## Rollback

<!-- How to back this out if production misbehaves: the previous release tag to reinstall (V1) or
     redeploy (V2+), and anything that does not roll back with it (data, migrations). -->

## Checklist

- [ ] `ci`, `promotion-source` and `back-merge` are green
- [ ] The dev build and the validate-dev run are for the dev head commit this pull request merges
- [ ] The release review Gate is approved here, if this promotion completes a release
- [ ] Charlie has signed off this promotion
- [ ] Merge with **Create a merge commit**, never squash or rebase, so dev and main share history
