# Caselist and camp-file backfill, September 2026

The recorded results of `v1-e30-t06-initial-backfill`, run by the operator from
[`docs/runbooks/caselist-backfill.md`](../runbooks/caselist-backfill.md). **Aggregates only**: no
school, no team code, no debater's name or initials, no disclosure path, no file name from inside
an archive, and no source file (`docs/policies/caselist-data-use.md` rules 4 and 5, prohibition 9).
Caselist slugs and snapshot dates are not identifying; they are what the object keys and run
summaries carry already.

Every number here was recorded from a run that happened. A figure that has not been measured
yet is left as _not yet run_, never estimated (working agreements §6).

## What `REMOVED` means here

Two different numbers answer "what was removed", and they must not be confused.

* **Paths no longer present** (the importer's `REMOVED`). Between two weekly archives it counts
  paths the earlier week had and this week does not. It is **not** a takedown count, for two
  reasons. A weekly archive is a seven-day window of editing activity, so a file nobody touched
  this week is simply absent from it. And a filename carries a per-team sequence number that
  increments, so a re-uploaded file changes path. `v1-e30-t03` measured 685 for one week of HS LD
  when almost nothing had been taken down. The held weeks show the same effect: the 07-21 weekly
  reports 36 of them, which is every path in the week before.
* **Withdrawals.** A sha256 present in an earlier snapshot and absent from the complete archive
  (`<slug>-all-<date>.zip`). This one does mean withdrawn from the caselist. It needs the complete
  archive, which this backfill cannot import yet (runbook, *The complete archive*), so it is
  **not yet measured**.

This document never reports the first number as removals or takedowns.

## Backlog at the start

From the 2026-09-25 dry run (`docs/data/caselist-sync-runs.md`, the cap measurement) and the
day 1 rehearsal. All three caselists list exactly one complete archive, which confirms
ADR-0017's assumption for hspolicy26 and hspf26.

| Caselist | Listed | Held already | Weeklies wanted | On this Mac | Downloads needed | Complete archive |
|---|---|---|---|---|---|---|
| `hsld26` | 13 | 5 | 7 | 3 | 4 | 1 listed, not fetched |
| `hspolicy26` | 12 | 0 | 11 | 0 | 11 | 1 listed, not fetched |
| `hspf26` | 12 | 0 | 11 | 0 | 11 | 1 listed, not fetched |
| **Day 1 rehearsal, 2026-09-26** (all three) | 37 | 5 | 29 | | 5 of 29 allowed today, 24 deferred by the cap | 0 OpenEv of 498 selected |

## Per snapshot

One row per imported weekly, from the runbook's `snapshot_rows`. *Against* is the snapshot each
one was compared with. *Paths no longer present* is the importer's `REMOVED` (above). *Not fully
read* counts filenames the path parser could not fully read (`warnings`). *Skipped* is archive
junk: macOS metadata, `.DS_Store`, Word lock files, unsafe paths.

| Caselist | Snapshot | Against | Members | NEW | UNCHANGED | CHANGED | DUPLICATE | Paths no longer present | SUPPRESSED | Skipped | Distinct sha256 | DOCX | DOC | PDF | Other | Not fully read |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| hsld26 | 2026-07-07 | none | 4 | 4 | 0 | 0 | 0 | 0 | 0 | 0 | 4 | 2 | 0 | 1 | 1 | 3 |
| hsld26 | 2026-07-14 | 2026-07-07 | 36 | 35 | 0 | 0 | 1 | 4 | 0 | 0 | 35 | 30 | 0 | 5 | 1 | 2 |
| hsld26 | 2026-07-21 | 2026-07-14 | 3 | 3 | 0 | 0 | 0 | 36 | 0 | 0 | 3 | 3 | 0 | 0 | 0 | 0 |
| hsld26 | 2026-07-28 | 2026-07-21 | 1 | 1 | 0 | 0 | 0 | 3 | 0 | 0 | 1 | 0 | 0 | 0 | 1 | 0 |
| hsld26 | 2026-08-04 | 2026-07-28 | 211 | 200 | 0 | 0 | 11 | 1 | 0 | 0 | 200 | 203 | 0 | 1 | 7 | 5 |
| hsld26 | 2026-08-11 | 2026-08-04 | 6 | 4 | 1 | 0 | 1 | 210 | 0 | 0 | 5 | 6 | 0 | 0 | 0 | 0 |
| hsld26 | 2026-08-18 | 2026-08-11 | 16 | 15 | 1 | 0 | 0 | 5 | 0 | 0 | 16 | 16 | 0 | 0 | 0 | 0 |
| hsld26 | 2026-08-25 | 2026-08-18 | 7 | 6 | 0 | 0 | 1 | 16 | 0 | 0 | 6 | 5 | 0 | 2 | 0 | 0 |

The five rows above are the weeklies the `v1-e34-t02` validation run pulled on 2026-09-24 (run
`20260924T042300Z`, dev). A re-import would be a no-op that writes nothing new, so the counts were
taken from the manifest each import wrote: the trailing `summary` row, plus format counts from the
member rows. They were read by the implementation session on 2026-09-26 with the runbook's
`snapshot_rows`. Cross-check against the run summary: 255 members imported (4 + 36 + 3 + 1 + 211),
12 duplicate (1 + 11), and 242 distinct files across the five. The per-week distinct counts add up
to 243, so exactly one file appears in two different weeks. All three agree with the run's
`files_imported`, `files_duplicate` and `blobs_stored`.

The 08-11 to 08-25 rows are backfill day 1, step 2 (run `20260926T213447Z`), read the same way
from their manifests. Cross-check against the run summary: 29 members imported (6 + 16 + 7),
2 duplicate (1 + 0 + 1), 0 skipped.

Rows for the remaining snapshots are appended in date order, per caselist, as the operator
records them.

### New to the caselist, per snapshot

**NEW does not mean new evidence.** The weekly importer classifies each archive against the week
before only, so a file stored in July, absent for a few windows, and back in August counts as NEW
again. The column that means never stored before is *First seen here*: distinct files in the
snapshot that no earlier snapshot of the same caselist held. It comes from the runbook's
`first_seen_rows`, and per run it equals the run's `blobs_stored`: 242 for the five July-August
weeks, and 16 for 08-11 to 08-25, against 25 NEW.

| Caselist | Snapshot | Distinct files | First seen here |
|---|---|---|---|
| hsld26 | 2026-07-07 | 4 | 4 |
| hsld26 | 2026-07-14 | 35 | 35 |
| hsld26 | 2026-07-21 | 3 | 3 |
| hsld26 | 2026-07-28 | 1 | 1 |
| hsld26 | 2026-08-04 | 200 | 199 |
| hsld26 | 2026-08-11 | 5 | 4 |
| hsld26 | 2026-08-18 | 16 | 10 |
| hsld26 | 2026-08-25 | 6 | 2 |

## OpenEv camp files

| Release | Members | NEW | DUPLICATE | Skipped | Distinct sha256 | Unknown camp | Already disclosed on a caselist | New blobs |
|---|---|---|---|---|---|---|---|---|
| `2026-policy` | _not yet run_ | | | | | | | |

From `import-openev --json` (`members`, `counts`, `skipped_total`, `distinct_sha256`,
`unknown_camps`, `caselist_duplicates`, `newly_stored_blobs`). 105 `.docx` and one `.DS_Store` are on
hand; the `.DS_Store` should show as skipped.

## Dedupe rate

Across each caselist's weeklies: stored members (NEW + UNCHANGED + CHANGED + DUPLICATE) against
the distinct files they hold. The saving is `1 − distinct / members`. From the runbook's
`dedupe_row`.

**The measured rate is small, and this document states it as measured rather than assuming a large
one.** Weekly archives are adjacent windows, not cumulative copies, so they overlap little. The
three HS LD weeklies on hand (09-01, 09-08, 09-15) collapsed 2,374 members to 2,107 distinct files
when `v1-e30-t03` measured them (its session report): an **11% saving**. The five held weeks below save 5.1%.

| Caselist | Weeklies | Stored members | Distinct files | Saving | Bytes of distinct files |
|---|---|---|---|---|---|
| hsld26 (the five held weeks only, 07-07 to 08-04) | 5 | 255 | 242 | 5.1% | 49,107,328 |
| hsld26 (all) | _not yet run_ | | | | |
| hspolicy26 | _not yet run_ | | | | |
| hspf26 | _not yet run_ | | | | |

**Bytes stored**, all sources on disk (`du -sk` of the store's `blobs/`): _not yet run_. It was
48,428 KiB for the five held weeks before the backfill began.

## Withdrawals against the complete archive

_Not yet measured._ Needs the complete archive imported as its own kind of snapshot, which the
PM has to decide how to schedule (session report, Deviations). Reported per caselist as a count
only, beside the path-level figure above, never merged with it.

## Pull runs

One row per `caselist pull` in the backfill, from `caselist runs --last N` or the run summaries.
The 2026-09-24 validation runs are in `docs/data/caselist-sync-runs.md` and not repeated here.

| Day | Run id | Caselists | Allowance | Downloaded | Deferred by the cap | Files imported | New blobs | Objects published | Duration |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `20260926T213447Z` | hsld26 | 3 (lowered for this run) | 3 (08-11, 08-18, 08-25) | 4 | 29 | 16 | 16 | 9.1 s |

## Dev publish

**Starting point, 2026-09-26, before the backfill.** `DEBATE_ENV=dev caselist status` exited `0`:
all five held hsld26 snapshots agree between the local store and the dev bucket. Per snapshot, the
sources and published sources are 4/4, 35/35, 3/3, 1/1 and 200/200, with no missing sources and
no checksum mismatches. `store ls manifests/` lists those five manifests and nothing else, so the
bucket holds no hspolicy26, hspf26 or OpenEv manifest yet. This is a baseline reading, not the
post-backfill check this section records below.

| Date | Caselist | Snapshots | Uploaded | Skipped | Failed | Bytes |
|---|---|---|---|---|---|---|
| | | | | | | |

dev status: _not yet run_

## Spot check in dev

At least 20 disclosures sampled at random from the dev manifests and compared by the coach against
their own filenames. Tallies only.

| Date | Sampled | Parsed correctly | Flagged by a warning | Wrong | Issues filed |
|---|---|---|---|---|---|
| | | | | | |

Coach's decision: _not yet run_

## Prod publish

The same local store (`~/.debate-research/dev`), published with `DEBATE_ENV=prod` and
`DEBATE_STORAGE__DATA_DIR` naming it, after dev was in sync and the spot check was accepted.

| Date | Caselist | Snapshots | Uploaded | Skipped | Failed | Bytes |
|---|---|---|---|---|---|---|
| | | | | | | |

prod status: _not yet run_
