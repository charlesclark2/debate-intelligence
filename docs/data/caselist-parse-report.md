<!-- docs-index: Counts from the operator-run full-corpus caselist parse, per caselist and environment -->
# Caselist parse report

The first full-corpus run of `debate-research caselist parse` over the caselist and camp sources the
2026-27 backfill imported (`v1-e31-t06-parse-pipeline`, criterion ac5). Counts only: no school, team
code, path, filename or card text appears here (`docs/policies/caselist-data-use.md`). The store
these runs write is described in [parsed-card-store.md](parsed-card-store.md).

**Status: not run yet.** The operator runs the parse from the dev data directory, publishing to dev
first. The steps are in the task's session report under Operator follow-ups. Each table below is
filled in from that run's `--json` summary, and the section for the second environment is added
when that publish happens.

## Versions

| | |
|---|---|
| Parser | `2026.09.20-docx-1` |
| Style profile | `2026.09.20-verbatim-1` |
| Fingerprints | `card-fingerprint-v1` |
| Version directory | _from the run_ |

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

Run from the dev data directory with `DEBATE_ENV=dev`, publishing to the dev evidence bucket.

| Caselist | Sources | Parsed | Unsupported | Failed (by reason) | Failure rate | Cards | Clusters | Occurrences | Wall-clock |
|---|---|---|---|---|---|---|---|---|---|
| hsld26 | | | | | | | | | |
| hspf26 | | | | | | | | | |
| hspolicy26 | | | | | | | | | |
| openev | | | | | | | | | |

Unsupported by format, and failures by reason, per caselist:

| Caselist | PDF | Legacy DOC | Other | Malformed | Oversized | Macro-enabled | Timeout | Other failures |
|---|---|---|---|---|---|---|---|---|
| hsld26 | | | | | | | | |
| hspf26 | | | | | | | | |
| hspolicy26 | | | | | | | | |
| openev | | | | | | | | |

The publish to dev, per caselist: objects uploaded, skipped, failed.

| Caselist | Uploaded | Skipped | Failed | Aggregates |
|---|---|---|---|---|
| hsld26 | | | | |
| hspf26 | | | | |
| hspolicy26 | | | | |
| openev | | | | |

The second run over the unchanged store, which must parse nothing and upload nothing:

| Caselist | Attempted | Skipped | Uploaded |
|---|---|---|---|
| hsld26 | | | |
| hspf26 | | | |
| hspolicy26 | | | |
| openev | | | |

Local store size after the run (`du -sh` of the data directory's `parsed/`): _from the run_.
