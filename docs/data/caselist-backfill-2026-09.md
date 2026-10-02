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
  archive, which this backfill does not import (ADR-0017, revision of 2026-09-26), so it is
  **deferred to `v1-e34-t04-full-archive-refresh`**. It is not zero; it is not measured here.

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
| hsld26 | 2026-09-01 | 2026-08-25 | 64 | 58 | 0 | 0 | 6 | 7 | 0 | 0 | 59 | 55 | 0 | 8 | 1 | 1 |
| hsld26 | 2026-09-08 | 2026-09-01 | 745 | 666 | 5 | 0 | 74 | 59 | 0 | 0 | 678 | 722 | 0 | 6 | 17 | 29 |
| hsld26 | 2026-09-15 | 2026-09-08 | 1597 | 1387 | 58 | 2 | 148 | 685 | 0 | 2 | 1487 | 1565 | 0 | 18 | 12 | 74 |
| hsld26 | 2026-09-22 | 2026-09-15 | 941 | 698 | 129 | 4 | 110 | 1462 | 0 | 0 | 883 | 925 | 0 | 12 | 4 | 14 |
| hsld26 | 2026-09-29 | 2026-09-22 | 827 | 676 | 75 | 6 | 70 | 860 | 0 | 0 | 776 | 818 | 0 | 8 | 1 | 8 |
| hspolicy26 | 2026-07-07 | none | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 2 | 0 | 0 | 0 | 0 |
| hspolicy26 | 2026-07-14 | 2026-07-07 | 1 | 0 | 0 | 0 | 1 | 2 | 0 | 0 | 1 | 1 | 0 | 0 | 0 | 0 |
| hspolicy26 | 2026-07-28 | 2026-07-14 | 1 | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 1 | 1 | 0 | 0 | 0 | 1 |
| hspolicy26 | 2026-08-04 | 2026-07-28 | 3 | 2 | 0 | 0 | 1 | 1 | 0 | 0 | 2 | 3 | 0 | 0 | 0 | 2 |
| hspolicy26 | 2026-08-11 | 2026-08-04 | 1 | 0 | 0 | 1 | 0 | 2 | 0 | 0 | 1 | 1 | 0 | 0 | 0 | 0 |
| hspolicy26 | 2026-08-18 | 2026-08-11 | 3 | 2 | 1 | 0 | 0 | 0 | 0 | 0 | 3 | 2 | 0 | 0 | 1 | 0 |
| hspolicy26 | 2026-08-25 | 2026-08-18 | 4 | 3 | 1 | 0 | 0 | 2 | 0 | 0 | 4 | 3 | 0 | 0 | 1 | 1 |
| hspolicy26 | 2026-09-01 | 2026-08-25 | 115 | 100 | 1 | 0 | 14 | 3 | 0 | 0 | 101 | 114 | 0 | 0 | 1 | 1 |
| hspolicy26 | 2026-09-08 | 2026-09-01 | 74 | 40 | 10 | 1 | 23 | 104 | 0 | 0 | 65 | 74 | 0 | 0 | 0 | 2 |
| hspolicy26 | 2026-09-15 | 2026-09-08 | 631 | 568 | 7 | 0 | 56 | 67 | 0 | 0 | 579 | 621 | 0 | 6 | 4 | 11 |
| hspolicy26 | 2026-09-22 | 2026-09-15 | 1018 | 838 | 42 | 0 | 138 | 589 | 0 | 0 | 932 | 1010 | 0 | 6 | 2 | 20 |
| hspolicy26 | 2026-09-29 | 2026-09-22 | 497 | 344 | 67 | 8 | 78 | 943 | 0 | 0 | 452 | 491 | 0 | 3 | 3 | 15 |
| hspf26 | 2026-07-07 | none | 9 | 8 | 0 | 0 | 1 | 0 | 0 | 0 | 8 | 7 | 0 | 1 | 1 | 0 |
| hspf26 | 2026-07-14 | 2026-07-07 | 42 | 34 | 0 | 0 | 8 | 9 | 0 | 0 | 34 | 18 | 0 | 23 | 1 | 0 |
| hspf26 | 2026-07-21 | 2026-07-14 | 2 | 2 | 0 | 0 | 0 | 42 | 0 | 0 | 2 | 0 | 0 | 2 | 0 | 0 |
| hspf26 | 2026-07-28 | 2026-07-21 | 357 | 300 | 0 | 0 | 57 | 2 | 0 | 0 | 300 | 156 | 0 | 201 | 0 | 17 |
| hspf26 | 2026-08-04 | 2026-07-28 | 3 | 3 | 0 | 0 | 0 | 357 | 0 | 0 | 3 | 1 | 0 | 2 | 0 | 0 |
| hspf26 | 2026-08-11 | 2026-08-04 | 16 | 13 | 0 | 0 | 3 | 3 | 0 | 0 | 13 | 8 | 0 | 8 | 0 | 0 |
| hspf26 | 2026-08-18 | 2026-08-11 | 3 | 3 | 0 | 0 | 0 | 16 | 0 | 0 | 3 | 2 | 0 | 0 | 1 | 1 |
| hspf26 | 2026-09-01 | 2026-08-18 | 28 | 27 | 0 | 0 | 1 | 3 | 0 | 0 | 27 | 13 | 0 | 15 | 0 | 1 |

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

The 09-01, 09-08 and 09-15 rows are the weeklies already on the operator's Mac, imported by hand
on day 1, step 3. Each `previous_snapshot` is the week before it, and each import's `--json`
output agrees with its manifest (members 64 / 745 / 1,597; NEW 58 / 666 / 1,387). The two skipped
members in 09-15 are `.DS_Store` files, as `v1-e30-t03` found. The 09-22 hsld26 and 07-07
hspolicy26 rows are day 1, step 5 (run `20260926T213709Z`): 943 imported (941 + 2), 110 duplicate,
683 new blobs.

The 09-15 row's 685 paths no longer present is the same figure `v1-e30-t03` measured, and 09-22's
1,462 is larger still. Neither is a takedown count.

Day 2 of the backfill ran late, at 04:44 UTC on 2026-09-29 (run `20260929T044458Z`, 11:44 pm
Central on the 28th). It imported hsld26 09-29, the week the site published that Tuesday, which
makes HS LD complete through the newest listing. It also imported hspolicy26 07-14 and 07-28, and
hspf26 07-07 and 07-14: 880 members (827 + 1 + 1 + 9 + 42), 80 duplicate, 619 new blobs. hspolicy26
has no 07-21 row because the site lists no 07-21 weekly for it. `pull` took the oldest week it did
not hold, 07-28.

Run 3 ran at 01:18 UTC on 2026-09-30 (run `20260930T011818Z`, 8:18 pm Central on the 29th). It
imported hspolicy26 08-04, 08-11 and 08-18, and hspf26 07-21 and 07-28: 366 members, 58 duplicate,
306 new blobs, in 123.6 s. The hspf26 07-28 weekly is **201 PDFs out of 357 members**. PF discloses
far more PDF than LD does, and PDFs are stored but not parsed in V1.

Run 4 ran at 01:07 UTC on 2026-10-01 (run `20261001T010726Z`, 8:07 pm Central on 30 September).
It imported hspolicy26 08-25, 09-01 and 09-08, and hspf26 08-04 and 08-11: 212 members, 40
duplicate, 158 new blobs, in 32.0 s. The hspf26 08-04 weekly reports 357 paths no longer present
against a week of 3 members: every path of the 07-28 window, the path-level figure behaving
exactly as described at the top of this document.

Run 5 ran at 01:17 UTC on 2026-10-02 (run `20261002T011748Z`, 8:17 pm Central on 1 October). It
imported hspolicy26 09-15, 09-22 and 09-29, which makes **Policy complete through the newest
listing**, and hspf26 08-18 and 09-01: 2,177 members, 273 duplicate, 1,721 new blobs, 1,723
objects published, in 161.5 s. The two extra objects are Policy disclosures byte-identical to
camp files already in the store: no new blob, but a new key under `raw/caselist/hspolicy26/`.
hspf26 has no 08-25 row because the site lists no 08-25 weekly for it.

**The site's cap is per date, not a rolling 24 hours.** Run 3 started 20 h 34 min after day 2's
five downloads and was granted all five. A rolling-24-hour limiter would have refused them. The withdrawal figure is deferred to `v1-e34-t04` (below).

Rows for the remaining snapshots are appended in date order, per caselist, as the operator
records them.

### New to the caselist, per snapshot

**NEW does not mean new evidence.** The weekly importer classifies each archive against the week
before only, so a file stored in July, absent for a few windows, and back in August counts as NEW
again. The column that means never stored before is *First seen here*: distinct files in the
snapshot that no earlier snapshot of the same caselist held. It comes from the runbook's
`first_seen_rows`. Per run it equals the run's `blobs_stored` (242 for the five July-August
weeks, and 16 for 08-11 to 08-25, against 25 NEW), except where the bytes were already stored
under another caselist or as a camp file. Run 5 is the one case so far: 1,723 first seen, 1,721
new blobs, because 2 Policy disclosures are byte-identical to camp files. For the three hand imports it equals each
import's own `newly_stored_blobs` (58, 659, 1,380).

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
| hsld26 | 2026-09-01 | 59 | 58 |
| hsld26 | 2026-09-08 | 678 | 659 |
| hsld26 | 2026-09-15 | 1487 | 1380 |
| hsld26 | 2026-09-22 | 883 | 681 |
| hsld26 | 2026-09-29 | 776 | 576 |
| hspolicy26 | 2026-07-07 | 2 | 2 |
| hspolicy26 | 2026-07-14 | 1 | 0 |
| hspolicy26 | 2026-07-28 | 1 | 1 |
| hspolicy26 | 2026-08-04 | 2 | 1 |
| hspolicy26 | 2026-08-11 | 1 | 1 |
| hspolicy26 | 2026-08-18 | 3 | 2 |
| hspolicy26 | 2026-08-25 | 4 | 3 |
| hspolicy26 | 2026-09-01 | 101 | 99 |
| hspolicy26 | 2026-09-08 | 65 | 41 |
| hspolicy26 | 2026-09-15 | 579 | 567 |
| hspolicy26 | 2026-09-22 | 932 | 823 |
| hspolicy26 | 2026-09-29 | 452 | 303 |
| hspf26 | 2026-07-07 | 8 | 8 |
| hspf26 | 2026-07-14 | 34 | 34 |
| hspf26 | 2026-07-21 | 2 | 2 |
| hspf26 | 2026-07-28 | 300 | 300 |
| hspf26 | 2026-08-04 | 3 | 3 |
| hspf26 | 2026-08-11 | 13 | 12 |
| hspf26 | 2026-08-18 | 3 | 3 |
| hspf26 | 2026-09-01 | 27 | 27 |

## OpenEv camp files

| Release | Members | NEW | DUPLICATE | Skipped | Distinct sha256 | Unknown camp | Already disclosed on a caselist | New blobs |
|---|---|---|---|---|---|---|---|---|
| `2026-policy` | 106 | 102 | 3 | 1 (`.DS_Store`) | 102 | **105 of 105** | 0 | 102 |

From `import-openev --json` (`members`, `counts`, `skipped_total`, `distinct_sha256`,
`unknown_camps`, `caselist_duplicates`, `newly_stored_blobs`). 105 `.docx` and one `.DS_Store` are on
hand; the `.DS_Store` was skipped. Imported 2026-09-26, day 1, step 6.

**Every camp file is recorded with camp `UNKNOWN`.** This is not a gap in the alias table. The
table has the camps these files name. The files name their camp at the *end* of the filename,
after the title and before the year, and sit in folders named for argument type. The importer
reads a camp only from the folder name or from the *start* of the filename, so it never looks
where the camp is. The bytes are stored and published correctly; the camp label is what is
missing. This is recorded as a follow-up for the OpenEv importer (session report) and not
patched here. The three DUPLICATEs are identical files present under two names within the
release; none duplicates a caselist disclosure.

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
| hsld26 (07-07 to 09-22, after day 1) | 12 | 3,629 | 3,036 | 16.3% | 408,918,566 |
| hsld26 (all, 07-07 to 09-29, complete as of the 09-29 listing) | 13 | 4,456 | 3,612 | 18.9% | 486,608,876 |
| hspolicy26 (all, 07-07 to 09-29, complete as of the 09-29 listing) | 11 | 2,350 | 1,843 | 21.6% | 479,442,733 |
| hspf26 | _not yet run_ | | | | |

**Bytes stored**, all sources on disk (`du -sk` of the store's `blobs/`): _not yet run_ for the
finished backfill. It was 48,428 KiB for the five held weeks before the backfill began, and
460,988 KiB after day 1 (HS LD complete, one Policy week, the camp files), 554,628 KiB after
day 2, 694,108 KiB after run 3, 736,460 KiB after run 4, and 1,186,508 KiB after run 5.

## Withdrawals against the complete archive

**Deferred to `v1-e34-t04-full-archive-refresh`; not measured by this backfill.** A withdrawal is
a sha256 present in an earlier snapshot and absent from the complete archive. This task imports no
complete archive (ADR-0017, revision of 2026-09-26; spec ac2 as amended the same day), because one
would share a snapshot key with that week's weekly. `v1-e34-t04` designs the separate snapshot
namespace that makes one importable, and reports this count there, per caselist and apart from the
path-level figure above. The blank here is not a zero.

## Pull runs

One row per `caselist pull` in the backfill, from `caselist runs --last N` or the run summaries.
The 2026-09-24 validation runs are in `docs/data/caselist-sync-runs.md` and not repeated here.

| Day | Run id | Caselists | Allowance | Downloaded | Deferred by the cap | Files imported | New blobs | Objects published | Duration |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `20260926T213447Z` | hsld26 | 3 (lowered for this run) | 3 (08-11, 08-18, 08-25) | 4 | 29 | 16 | 16 | 9.1 s |
| 1 | `20260926T213709Z` | all three | 2 left | 2 (hsld26 09-22, hspolicy26 07-07) | 21 | 943 | 683 | 683 | 65.0 s |
| 2 (run Mon 28 Sep, 11:44 pm Central) | `20260929T044458Z` | all three | 5 | 5 (hsld26 09-29; hspolicy26 07-14, 07-28; hspf26 07-07, 07-14) | 19 | 880 | 619 | 619 | 51.4 s |
| 3 (Tue 29 Sep, 8:18 pm Central) | `20260930T011818Z` | all three | 5 | 5 (hspolicy26 08-04, 08-11, 08-18; hspf26 07-21, 07-28) | 14 | 366 | 306 | 306 | 123.6 s |
| 4 (Wed 30 Sep, 8:07 pm Central) | `20261001T010726Z` | all three | 5 | 5 (hspolicy26 08-25, 09-01, 09-08; hspf26 08-04, 08-11) | 9 | 212 | 158 | 158 | 32.0 s |
| 5 (Thu 1 Oct, 8:17 pm Central) | `20261002T011748Z` | all three | 5 | 5 (hspolicy26 09-15, 09-22, 09-29; hspf26 08-18, 09-01) | 4 | 2,177 | 1,721 | 1,723 | 161.5 s |

## Dev publish

**Starting point, 2026-09-26, before the backfill.** `DEBATE_ENV=dev caselist status` exited `0`:
all five held hsld26 snapshots agree between the local store and the dev bucket. Per snapshot, the
sources and published sources are 4/4, 35/35, 3/3, 1/1 and 200/200, with no missing sources and
no checksum mismatches. `store ls manifests/` lists those five manifests and nothing else, so the
bucket holds no hspolicy26, hspf26 or OpenEv manifest yet. This is a baseline reading, not the
post-backfill check this section records below.

| Date | Caselist | Snapshots | Uploaded | Skipped | Failed | Bytes |
|---|---|---|---|---|---|---|
| 2026-09-26 | hsld26 (step 4, hand imports) | 11 complete of 11 | 2,097 (58 + 659 + 1,380) | 392 already present | 0 | not recorded (table output only) |
| 2026-09-26 | openev `2026-policy` (step 6) | 1 of 1 | 102 | 0 | 0 | not recorded |

The pull runs published their own imports (the pull runs table: 16, then 683 objects).

**Check after day 1, 2026-09-26.** `caselist status` exited `0`, **Every snapshot agrees**:
14 snapshots (hsld26 07-07 to 09-22, hspolicy26 07-07, openev 2026-policy), every one with local
files equal to published, 0 missing, 0 mismatches. This is a mid-backfill reading. The status
line below is recorded when the backfill is finished.

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
