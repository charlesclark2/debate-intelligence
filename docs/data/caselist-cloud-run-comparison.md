<!-- docs-index: The cutover's comparison of a dev cloud run with the Mac's offline reproduction of its parse and index: counts only (v1-e40-t06) -->
# The cutover's comparison: a dev cloud run and the Mac's reproduction of it

Measured 2026-10-26 by `ops/caselist_run/compare_cloud_run.py` (`v1-e40-t06`, ac1; ADR-0020 (4)).
The Mac restored the cloud run's working copy under the dev bucket's run lock, re-parsed every
store the run's index was built from, and rebuilt the index from the re-parse, offline: nothing
was downloaded from OpenCaselist and nothing was published. Counts, store slugs and ids only.

**Verdict: DIFFER.**

## The cloud run

| | |
|---|---|
| Run | `20261026T040426Z` |
| Outcome | `incomplete` |
| Archives downloaded | 1 |
| Files imported | 6097 |
| Objects published | 3 |
| Sources its parse stage parsed | 1 (cards 0) |
| Index | `4a9f6fa7c02391c2` |
| Restored | 51 manifests, 15342 parsed-store objects at `2026.10.20-docx-6`, in 499.1 s |
| The Mac's build | `v1.1.0-dev.155` |

## Parse records, by store

| Store | | Sources | Parsed | Unsupported | Failed | Cards | Occurrence rows | Source records | Occurrence records |
|---|---|---:|---:|---:|---:|---:|---:|---|---|
| hsld26 | cloud | 6122 | 5999 | 123 | 0 | 93377 | 109110 |  |  |
| hsld26 | Mac | 6122 | 5999 | 123 | 0 | 93377 | 109110 | the same | the same |
| hspf26 | cloud | 5234 | 3592 | 1642 | 0 | 59406 | 73632 |  |  |
| hspf26 | Mac | 5234 | 3592 | 1642 | 0 | 59406 | 73632 | the same | the same |
| hspolicy26 | cloud | 3869 | 3825 | 44 | 0 | 126681 | 144841 |  |  |
| hspolicy26 | Mac | 3869 | 3825 | 44 | 0 | 126681 | 144841 | the same | the same |
| openev | cloud | 105 | 102 | 3 | 0 | 8081 | 8081 |  |  |
| openev | Mac | 105 | 102 | 3 | 0 | 8081 | 8081 | the same | the same |

## The index

| | Cloud | Mac |
|---|---:|---:|
| Index id | `4a9f6fa7c02391c2` | `4a9f6fa7c02391c2` |
| documents | 50434 | 50434 |
| occurrences | 331460 | 331460 |
| occurrence_rows_read | 335664 | 335664 |
| suppressed_occurrences | 0 | 0 |
| clusters_left_out | 0 | 0 |
| provenance_rows | 127562 | 127562 |
| documents, hsld26 | 12714 | 12714 |
| documents, hspf26 | 11000 | 11000 |
| documents, hspolicy26 | 20961 | 20961 |
| documents, openev | 5759 | 5759 |
| Suppression list applied | 5 entries | 6 entries, another |

## Where they differ

* index: the suppression lists applied differ

## The PM's reading (2026-10-26)

Added by the PM. The measurement above is unchanged.

**ac1 is accepted.** The one difference is stale metadata, not a suppression the cloud run missed:

* The bucket's suppression list has two versions, 2026-10-01 and 2026-10-23 00:36 UTC (removal
  RM-2026-90, which added the sixth entry), and holds 6 entries now.
* The published index `4a9f6fa7c02391c2` was built by the Mac's run of 2026-10-22, before that
  removal, so its manifest records 5 entries (sha `1958daa1126c`).
* The cloud run rebuilt the index under all 6. The sixth entry suppresses nothing in the corpus, so
  the rebuild had the same id, and the run did not republish it (`v1-e39-t09`'s rule). The
  comparison's "cloud" manifest is therefore the one published on 2026-10-22. The Mac's rebuild
  records 6 entries (sha `5a3a30cbb30a`).
* Documents, occurrences and suppressed occurrences (0) agree on both sides.

An identical rebuild leaving the published suppression line stale is filed as
`v1-e39-t19-identical-rebuild-records-its-suppression-list` (p3). The run's `incomplete` outcome is
a separate false drift in bucket mode, filed as `v1-e40-t13-bucket-mode-report-counts-held-sources`
(p1).
