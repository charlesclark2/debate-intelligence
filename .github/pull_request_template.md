<!--
Task pull request: task/<task-name> into dev. `scripts/task pr` writes this description from the
session report, so this template is for a task pull request opened by hand.

A pull request into main is not a task pull request. Use the promotion template (dev into main)
or the hotfix template (hotfix/<slug> into main) by adding ?template=promotion.md or
?template=hotfix.md to the compare URL. The promotion-source check fails without them.
-->

Implements **<!-- task name, e.g. v1-e04-t02-http-fetcher -->** — <!-- the spec's debate/title -->

Spec: <!-- plan_specs/v1/<epic>/<tNN-slug>.yaml -->
Session report: <!-- docs/session-reports/<task-name>.md -->

## Summary

<!-- What was built and anything the reviewer should look at first. -->

## Acceptance criteria

<!-- Every Goal criterion and plan-node criterion: PASS / FAIL / NOT RUN, with the command and result. -->

## Operator follow-ups

<!-- Commands or GitHub/AWS settings the operator still has to run or change, or "None". -->

## Checklist

- [ ] Every acceptance criterion in the spec is accounted for above
- [ ] The Goal's `status.phase` is updated in this pull request
- [ ] Smoke checks in `tests/smoke/` added or updated, or this changes no user-facing surface
- [ ] CI (`ci`) is green
- [ ] Squash-merge into `dev`
