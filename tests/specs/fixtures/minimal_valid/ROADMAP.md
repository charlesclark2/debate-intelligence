# Roadmap — the minimal fixture tree

This file is both halves of one expectation. The generated section below is written by hand from
the spec files beside it, so `scripts/spec_index.py --check` passing on this tree is a real check
of the renderer rather than a comparison of the renderer with itself. The prose above and below the
markers is here to prove the generator leaves hand-written text alone.

<!-- BEGIN GENERATED -->

## Release summary

| Release | Theme | Epics | Tasks | Done | Est. hours |
|---|---|---|---|---|---|
| [v1.0](plan_specs/releases/v1.0.yaml) | Minimal foundation | 1 | 2 | 1 | 4 |
| [v1.1](plan_specs/releases/v1.1.yaml) | Minimal follow-up | 1 | 1 | 0 | 6 |

## V1

### v1.0 — Minimal foundation

The first release of the fixture tree.

#### [E01 — Minimal Foundation](plan_specs/v1/e01-minimal-foundation/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [First step](plan_specs/v1/e01-minimal-foundation/t01-first-step.yaml) `v1-e01-t01-first-step` | Succeeded | 0 | 2.0 |
| [Second step](plan_specs/v1/e01-minimal-foundation/t02-second-step.yaml) `v1-e01-t02-second-step` | InProgress | 1 | 2.0 |


### v1.1 — Minimal follow-up

The second release of the fixture tree.

#### [E02 — Minimal Follow-up](plan_specs/v1/e02-minimal-followup/epic.yaml)

| Task | Status | Prereqs | Est. hours |
|---|---|---|---|
| [Later step](plan_specs/v1/e02-minimal-followup/t01-later-step.yaml) `v1-e02-t01-later-step` | Pending | 1 | 6.0 |

<!-- END GENERATED -->

## Not generated

This section is below the END marker and has to survive a regeneration untouched.
