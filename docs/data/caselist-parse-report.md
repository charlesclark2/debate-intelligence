<!-- docs-index: Counts from the operator-run full-corpus caselist parse, per caselist and environment -->
# Caselist parse report

The first full-corpus run of `debate-research caselist parse` over the caselist and camp sources the
2026-27 backfill imported (`v1-e31-t06-parse-pipeline`, criterion ac5). Counts only: no school, team
code, path, filename or card text appears here (`docs/policies/caselist-data-use.md`). The store
these runs write is described in [parsed-card-store.md](parsed-card-store.md).

**Status: run in dev and prod on 2026-10-10.** The operator ran the parse from the dev data
directory with the merged pipeline (#207), publishing to dev and then to prod. Each table below is
from that run's `--json` summary. The steps are in the task's session report under "Operator
follow-ups, revised". The PM recorded the figures at close-out.

## Versions

| | |
|---|---|
| Parser | `2026.09.20-docx-1` |
| Style profile | `2026.09.20-verbatim-1` |
| Fingerprints | `card-fingerprint-v1` |
| Version directory | `2026.09.20-docx-1` (first generation) |

## The corpus before the run

Distinct stored sources in each caselist's weekly manifests (the OpenEv release's for `openev`), by
format, counted read-only from the dev data directory's manifests on 2026-10-09. The full-archive
namespace is not part of the parse and is not counted.

| Caselist | Manifests | Sources | DOCX | PDF | Legacy DOC | Other | DOCX size |
|---|---|---|---|---|---|---|---|
| hsld26 | 14 | 4,461 | 4,360 | 62 | 0 | 39 | 525.6 MiB |
| hspf26 | 13 | 3,906 | 2,650 | 1,240 | 0 | 16 | 992.2 MiB |
| hspolicy26 | 13 | 2,657 | 2,629 | 18 | 0 | 10 | 687.8 MiB |
| openev | 1 | 102 | 102 | 0 | 0 | 0 | 53.8 MiB |
| **Total** | 41 | 11,126 | 9,741 | 1,320 | 0 | 65 | 2,259.4 MiB |

PDFs, legacy `.doc` files and other formats are recorded as `UNSUPPORTED`: an outcome, not a
failure, and counted on neither side of the failure rate.

## Dev

Run on 2026-10-10 from the dev data directory with `DEBATE_ENV=dev`, publishing to the dev evidence
bucket. Every run exited 0. The failure rate is failed over the sources tried that are not
unsupported, against the 5% default threshold. Wall-clock is the first run's `elapsed_seconds`:
parse, rebuild and publish.

| Caselist | Sources | Parsed | Unsupported | Failed | Failure rate | Cards | Clusters | Occurrences | Wall-clock |
|---|---|---|---|---|---|---|---|---|---|
| hsld26 | 4,461 | 4,354 | 101 | 6 | 0.14% | 67,914 | 12,102 | 77,537 | 518 s |
| hspf26 | 3,906 | 2,649 | 1,256 | 1 | 0.04% | 44,298 | 9,828 | 53,916 | 352 s |
| hspolicy26 | 2,657 | 2,610 | 28 | 19 | 0.72% | 87,556 | 18,366 | 100,314 | 747 s |
| openev | 102 | 98 | 0 | 4 | 3.92% | 7,288 | 5,467 | 7,288 | 106 s |
| **Total** | 11,126 | 9,711 | 1,385 | 30 | | 207,056 | | 239,055 | 1,723 s |

Unsupported by format, and failures by typed reason, per caselist:

| Caselist | PDF | Legacy DOC | Other | `MALFORMED_XML` | `NOT_A_ZIP` | `FORBIDDEN_XML_CONSTRUCT` | `COMPRESSION_RATIO_EXCEEDED` | Macro-enabled, timeout, worker crash, parser error |
|---|---|---|---|---|---|---|---|---|
| hsld26 | 62 | 0 | 39 | 5 | 1 | 0 | 0 | 0 |
| hspf26 | 1,240 | 0 | 16 | 0 | 0 | 1 | 0 | 0 |
| hspolicy26 | 18 | 0 | 10 | 0 | 0 | 19 | 0 | 0 |
| openev | 0 | 0 | 0 | 0 | 0 | 3 | 1 | 0 |

**Occurrences per card**, the check that the occurrence table holds one row per disclosure:
hsld26 1.14, hspf26 1.22, hspolicy26 1.15, openev 1.00. These are close to the disclosures per
DOCX source measured from the manifests before the run (1.15, 1.26, 1.19, 1.00), and under the 1.5
stop line. Cards per parsed DOCX: hsld26 15.6, hspf26 16.7, hspolicy26 33.5, openev 74.4.

The publish to dev, per caselist. Uploaded is one per-source file for every source, unsupported and
failed ones included, plus the three aggregates.

| Caselist | Uploaded | Skipped | Failed | Aggregates |
|---|---|---|---|---|
| hsld26 | 4,464 | 0 | 0 | 3 |
| hspf26 | 3,909 | 0 | 0 | 3 |
| hspolicy26 | 2,660 | 0 | 0 | 3 |
| openev | 105 | 0 | 0 | 3 |

The second run over the unchanged store, which must parse nothing and upload nothing. Its
`elapsed_seconds` is the rebuild and the publish's checksum checks alone. The PM's limit for filing
an incremental rebuild was 900 s per caselist, and none came close.

| Caselist | Attempted | Skipped | Uploaded | Elapsed |
|---|---|---|---|---|
| hsld26 | 0 | 4,461 | 0 | 348 s |
| hspf26 | 0 | 3,906 | 0 | 214 s |
| hspolicy26 | 0 | 2,657 | 0 | 460 s |
| openev | 0 | 102 | 0 | 60 s |

Sizes after the run: `occurrences.jsonl` is 50 MB (hsld26), 35 MB (hspf26), 66 MB (hspolicy26) and
4.4 MB (openev). The local `parsed/` directory is 5.8 GB. No run was stopped at the 8 GB memory line.

**Sample check, by eye.** Five randomly drawn parsed hsld26 sources were opened beside the first
five cards the store holds for each. Four looked right. In one, the second and third stored cards
were wrong: two cards with an empty tag, one `ABBREVIATED` and one `CITE_ONLY`, where the document
has none. This is a parser accuracy finding, followed up in `v1-e31-t09`. The tallies are recorded
here; the files and tags are not.

## Prod

Published on 2026-10-10 to the prod evidence bucket from the same dev data directory
(`DEBATE_ENV=prod`, `DEBATE_STORAGE__DATA_DIR` set to the dev directory, `--confirm-prod`). The dry
run showed 4,461 hsld26 sources skipped and 0 to parse. Nothing was parsed again. Every aggregate
was rebuilt to the same counts as dev, and every publish exited 0. The shell's variables were unset
afterwards.

| Caselist | Parsed this run | Store sources | Store cards | Store occurrences | Store clusters | Uploaded | Failed | Elapsed |
|---|---|---|---|---|---|---|---|---|
| hsld26 | 0 | 4,461 | 67,914 | 77,537 | 12,102 | 4,464 | 0 | 279 s |
| hspf26 | 0 | 3,906 | 44,298 | 53,916 | 9,828 | 3,909 | 0 | 202 s |
| hspolicy26 | 0 | 2,657 | 87,556 | 100,314 | 18,366 | 2,660 | 0 | 370 s |
| openev | 0 | 102 | 7,288 | 7,288 | 5,467 | 105 | 0 | 55 s |

`store ls parsed/hsld26/2026.09.20-docx-1/index.jsonl` against prod lists the object (1.6 MB).

## After `card-fingerprint-v2`

Every cluster count above is under `card-fingerprint-v1`. `v1-e31-t08-short-card-recall` changed
which cards share a cluster (`card-fingerprint-v2`; the exact fingerprints are the same), so the
`Clusters` columns change when the aggregates are next rebuilt. Sources, parsed counts, cards and
occurrence rows do not: nothing is parsed again.

**Status: not rebuilt yet.** The by-eye sample of 20 newly joined pairs is that task's operator
follow-up (its criterion ac5), and it waits for `v1-e31-t09`'s re-parse under `2026.10.10-docx-2`,
which rebuilds the aggregates under `card-fingerprint-v2` in the same run. The figures are recorded
here when it has run.

**A provisional preview, 2026-10-10.** Read-only: the stored cards of this report's
`2026.09.20-docx-1` store placed in memory under the new rules, and compared with the occurrence
table. Provisional because `v1-e31-t09` found that most cards this parse marked `ABBREVIATED` are
whole cards, which the re-parse will reclassify and cluster.

| Caselist | Cards | Clusters, `v1` | Clusters, `v2` | Clusters merged into another | Clusters divided | Largest cluster, `v1` | Largest cluster, `v2` | Exact fingerprints changed |
|---|---|---|---|---|---|---|---|---|
| hsld26 | 67,914 | 12,102 | 12,107 | 37 | 17 | 620 | 620 | 0 |
| hspf26 | 44,298 | 9,828 | 9,835 | 18 | 20 | 541 | 541 | 0 |
| hspolicy26 | 87,556 | 18,366 | 18,326 | 49 | 9 | 1,165 | 1,164 | 0 |
| openev | 7,288 | 5,467 | 5,466 | 1 | 0 | 21 | 21 | 0 |

No new cluster is made of more than four earlier ones. What each column means, and what the
figures do and do not show, is in that task's session report under "Corpus-scale check".

## What the run settled, and what it raised

* **No incremental rebuild yet.** The slowest rebuild was 460 s (hspolicy26). This will be
  revisited when `v1-e34-t17` puts the parse inside the weekly run.
* **The failure-rate threshold and small caselists.** openev's four failures out of 102 are just under 4%.
  One more bad file in a release that size crosses 5%. `v1-e34-t17` takes a minimum number of
  sources tried before the rate is judged.
* **23 files refused as `FORBIDDEN_XML_CONSTRUCT`**, mostly in policy, and 5 as `MALFORMED_XML`.
  Which construct, and whether it is safe to accept, is `v1-e31-t09`'s to find out.
* **A third of PF is PDF** (1,240 of 3,906 sources), so PF's parsed store covers two thirds of its
  disclosures. PDF parsing is filed as a post-V1 task.
* **Each parser version is a full copy.** A version bump writes a new 5.8 GB directory beside the
  old one, locally and in both buckets. Retention of superseded version directories is noted for a
  later task.
