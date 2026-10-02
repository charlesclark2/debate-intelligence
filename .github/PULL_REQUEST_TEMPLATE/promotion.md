<!--
Promotion: dev into main. main is production; this pull request is how validated work gets there.
The rule and what "validated in dev" means:
https://github.com/charlesclark2/debate-intelligence/blob/dev/docs/process/branching-and-environments.md

The promotion-source check fails while the "Dev build:" line below is blank, and runs again
whenever this description is edited. Guidance sits in comments like this one, so a line holding
only its comment still counts as blank.

There is no line for the validate-dev run. protect-main requires the `validate-dev` commit status
on this pull request's head commit, and that status links its run, so the checks list below is the
record. If dev moves while this is open, the new head has no status until it validates, and the
merge button stays blocked until it does.
-->

## Included

Release: <!-- e.g. v1.1 (plan_specs/releases/v1.1.yaml), or "none: interim promotion" -->

Tasks:
<!-- Every task merged into dev since the last promotion, one per line with its spec path.
     `git log --first-parent --oneline origin/main..origin/dev` lists the merges. -->

## Validation in dev

Dev build: <!-- pre-release tag vX.Y.Z-dev.N (V1) or dev deploy id (V2+) built from the dev head commit this merges -->

The `validate-dev` status on the head commit is the validation: it names the pre-release it
installed and links the run. GitHub blocks the merge until it is green for the current head.

## Evaluations

<!-- From v1.3: promotion eval results for every prompt or model change included. Before v1.3,
     "not required before v1.3". -->

## Manual checks

<!-- What automation does not cover yet, what was checked by hand, and the result. -->

## Rollback

<!-- How to back this out if production misbehaves: the previous release tag to reinstall (V1) or
     redeploy (V2+), and anything that does not roll back with it (data, migrations). -->

## Checklist

- [ ] `ci`, `promotion-source`, `back-merge` and `validate-dev` are green
- [ ] The dev build above is the pre-release the `validate-dev` status names
- [ ] The release review Gate is approved here, if this promotion completes a release
- [ ] Charlie has signed off this promotion
- [ ] Merge with **Create a merge commit**, never squash or rebase, so dev and main share history
