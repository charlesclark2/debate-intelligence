# Session report: v1-e34-t37-listed-camp-file-with-a-hand-imported-name

| | |
|---|---|
| Task | `v1-e34-t37-listed-camp-file-with-a-hand-imported-name` — A listed camp file is not taken as already imported because a file of another camp shares its name |
| Spec | [`plan_specs/v1/e34-caselist-sync/t37-listed-camp-file-with-a-hand-imported-name.yaml`](../../plan_specs/v1/e34-caselist-sync/t37-listed-camp-file-with-a-hand-imported-name.yaml) |
| Epic / release | `v1-e34-caselist-sync` / `v1.1` |
| Branch | `task/v1-e34-t37-listed-camp-file-with-a-hand-imported-name` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The count comes first (PM ruling 1). Over every sync run record on the Mac, 17 runs from
2026-09-24 to 2026-10-22, **no listed OpenEv file was decided `already_imported` by name**. Two were
decided `already_imported`, both matched by their own id (a row named `openev-<id>-…`), so **none
matched a row in another camp folder**. The zero is structural, not luck: no run configures
`caselist.openev_event`, so 498 of the 500 listed files stop at `no_event_configured` before the
matcher, and the two that carry an event tag (LD) meet a release manifest holding only the sync's
own rows. The 105 hand-imported rows are all in the Policy release, which no listed file reached.
The weekly run moved to the cloud on 2026-10-25. Its runs keep their per-file decisions only in
the run's CloudWatch log, so I wrote a counts-only operator block for them and am waiting for its
result. If it also shows none, the task stops here under ruling 2 with no rule change.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `listed-camp-file-with-a-hand-imported-na` (Same name, other camp) | IN PROGRESS | Mac count recorded; cloud count with the operator |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the count is recorded before any rule; if it finds any, tests shown failing first | IN PROGRESS | Mac count below; cloud count pending |
| Node: `uv run pytest packages/debate_core/tests -k openev` | NOT RUN yet | |

### The count, on the Mac

Read-only, from a scratch script that prints counts only (no path, file name or camp name),
about 0.1 s. It reads every record that can carry per-file decisions:

* `~/.debate-research/dev/caselist-sync-runs/*.json`: 17 run summaries, the only records with
  `openev_selections`. The first is 2026-09-24T04:23Z and the last 2026-10-22T05:20Z.
* `~/.debate-research/dev/caselist-sync-runs.jsonl` (16 lines) and
  `caselist-sync-run-details.jsonl` (3 lines): read, and neither carries per-file decisions.
* `~/.debate-research/reimport-working-copy/`: 21 records, none with per-file decisions.

For each listed file decided `already_imported`, it asks the release manifest
(`objects/manifests/openev/<year>-<event>.jsonl`) for a classified row whose file name starts
`openev-<that id>-`. A file with such a row was held by id (`_match_listed_openev`'s first rule).
One without it went by name, by an inbox digest or by the delivery record, and only those could be
a match across folders.

| | Count |
|---|---|
| Run records with per-file OpenEv decisions | 17 |
| Listed-file decisions in them | 7,972 |
| `no_event_configured` | 7,968 (498 in each of 16 runs) |
| `download` | 2 (2026-10-14T11:00Z; both tagged LD) |
| `already_imported` | 2 (2026-10-22T05:20Z; the same two LD files) |
| `already_imported` by id | 2 |
| **`already_imported` by name (not by id)** | **0** |
| **of those, matching a row in another camp folder** | **0** |

What the release manifests hold, counted the same way. `2026-ld`: 2 rows, both the sync's own
(`openev-<id>-…`). `2026-policy`: 105 hand-imported rows, each one folder deep (`<camp>/<file>`),
and no sync row.

## Files changed

* `docs/session-reports/v1-e34-t37-listed-camp-file-with-a-hand-imported-name.md`: this report.

## Deviations from the spec

None.

## Decisions and assumptions

1. **"By name alone" is counted as "not by id".** The run records keep no listed path (policy rule
   4), so a by-name match cannot be seen directly. A listed file decided `already_imported` with no
   row named after its id is the most it can be. On the Mac that set is empty, so the folder
   question never arises. Had it not been empty, the folder comparison would have needed the
   listing's paths, which only the API has.

## Operator follow-ups

The cloud count is pending (see the session's hand-off).

## Follow-up work

None yet.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
