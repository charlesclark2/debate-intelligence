# Session report: v1-e39-t18-backfiles-in-the-pilot-index

| | |
|---|---|
| Task | `v1-e39-t18-backfiles-in-the-pilot-index` — Backfile seasons searchable on the pilot, without slowing its cold start |
| Spec | [`plan_specs/v1/e39-evidence-search-pilot/t18-backfiles-in-the-pilot-index.yaml`](../../plan_specs/v1/e39-evidence-search-pilot/t18-backfiles-in-the-pilot-index.yaml) |
| Epic / release | `v1-e39-evidence-search-pilot` / `v1.7` |
| Branch | `task/v1-e39-t18-backfiles-in-the-pilot-index` |
| Session status | IN PROGRESS <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

In progress: ac1 (the counts before building). Nothing has been restored, built, published or
deployed. The first bucket check found hspolicy25 still at `2026.10.27-docx-7`, so measuring was held.
The hold was lifted on 2026-11-12 after hspolicy25's cloud rebuild to `2026.11.03-docx-9` finished
([The measurement so far](#the-measurement-so-far)); the second bucket check is next.

## Plan nodes

<!-- One row per Plan graph node, in the order they were completed. -->

| Node | Status | Notes |
|---|---|---|
| | | |

## Acceptance criteria

<!-- Goal criteria (ac1…) and every node criterion. Status: PASS / FAIL / NOT RUN. -->

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| | | |

## Files changed

<!-- Group by package or directory; one line on why each group changed. -->

## Deviations from the spec

None.

## Decisions and assumptions

**The PM's rulings of 2026-11-12, on the hold** (relayed by the operator):

1. hspolicy25 is rebuilt in the cloud by caselist-cloud-run.md's "Backfile imports" (dry run first),
   after the landscape republish then under way has published and deleted its copy. The index is
   measured once, with all four backfiles at `2026.11.03-docx-9`.
2. The brief's "hspolicy25 rebuilt to docx-9 on 2026-11-12" was a plan, not a record: no rebuild had
   run, so there is no failed task to look into.
3. The restore and every timing wait until the operator says the landscape work and the rebuild have
   both finished and the lock is free. Then: the bucket check again (all four backfiles docx-9 only,
   hspolicy25 about 14,343 objects), the restore, the measurements, one block at a time, then the copy
   and every scratch index are deleted (policy 1.18). Every block starts with `cd "${HOME}"`.

**The PM's relay of 2026-11-12, lifting the hold:**

* hspolicy25's rebuild has finished: ECS task `8e203907c93940a99ce84ea6dba01d9a`, started 00:53
  Chicago on task-definition revision 15 (parser `2026.11.03-docx-9`), run by caselist-cloud-run.md's
  "Backfile imports" after a clean dry run. Its result line: status ok, applied true,
  downloaded_bytes 0, sources_skipped 14,340, parsed 14,163, unsupported 176, failed 1, cards
  408,335, parsed_uploaded 14,343, no code; restore 7.2 s, parse 4,080.9 s, publish 69.6 s,
  publish_parsed 388.0 s.
* The landscape republish finished on 2026-11-10.
* hspolicy25's `2026.10.27-docx-7` directory is still in the bucket; the PM retires it in the next
  batch. So for hspolicy25 the check reads "docx-9 present and complete", not "docx-9 only".
* The restore size is recomputed from the second check's real docx-9 bytes (all eight stores), with
  25% headroom, against the Mac's free space; if it does not fit, measuring stops. The restore takes
  docx-9 directories only, never a docx-7 one. After measuring, the copy and every scratch index are
  deleted, and the deletion is recorded with what was removed.
* Unchanged: no index holding backfile cards is published to dev or prod, and no function is
  deployed with one, before the PM rules; nothing runs on a Wednesday; no AWS write of any kind; no
  pull request.

## The measurement so far

**The bucket check** (read-only: the run lock and a listing of each store's
`parsed/<store>/2026.11.03-docx-9/`), run by the operator on 2026-11-12 just after midnight, with the
lock free. Two earlier attempts stopped with `aws: [ERROR]: [Errno 2] No such file or directory`: the
terminal sat in a worktree deleted after its merge, and the AWS CLI stops on a missing working
directory before any request. Every block now starts with `cd "${HOME}"`.

| Store | docx-9 objects | docx-9 bytes | `occurrences.jsonl` | Version directories |
|---|---|---|---|---|
| hspolicy25 | 0 | 0 | 0 | `2026.10.27-docx-7` only |
| hsld25 | 23,660 | 10,986,908,792 | 1 | docx-9 only |
| hspolicy24 | 12,312 | 10,791,735,497 | 1 | docx-9 only |
| hsld24 | 23,976 | 11,104,528,527 | 1 | docx-9 only |
| hsld26 | 8,258 | 4,128,943,216 | 1 | docx-7 and docx-9 |
| hspolicy26 | 5,691 | 6,220,607,735 | 1 | docx-7 and docx-9 |
| hspf26 | 6,700 | 1,956,072,676 | 1 | docx-7 and docx-9 |
| openev | 110 | 201,266,870 | 1 | docx-7 and docx-9 |

The three backfiles at docx-9 hold 32,883,172,816 bytes, and the current four stores 12,506,890,497.
With hspolicy25 at its docx-7 size (13,510,680,041, from the backfile runbook), a restore of all eight
is about 58.9 GB, 73.6 GB with 25% headroom, against 112,754,421,760 bytes free on the Mac (memory
19,327,352,832 bytes; Docker VM 8,221,937,664 bytes, 11 CPUs, aarch64).

## Operator follow-ups

<!-- Commands the operator must run (anything over ~2 minutes), with where to run them, the exact
command, expected runtime and what success looks like. Also GitHub/AWS settings to change. -->

None.

## Follow-up work

<!-- Bugs, gaps or ideas outside this task's scope, each with the task or epic it belongs to.
The PM decides whether they become spec changes or new tasks. -->

None.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
