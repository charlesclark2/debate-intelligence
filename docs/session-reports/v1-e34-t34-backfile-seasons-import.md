# Session report: v1-e34-t34-backfile-seasons-import

| | |
|---|---|
| Task | `v1-e34-t34-backfile-seasons-import` — Earlier seasons' complete archives, from 2021-22 on, imported and parsed as backfiles |
| Spec | [`plan_specs/v1/e34-caselist-sync/t34-backfile-seasons-import.yaml`](../../plan_specs/v1/e34-caselist-sync/t34-backfile-seasons-import.yaml) |
| Epic / release | `v1-e34-caselist-sync` / `v1.1` |
| Branch | `task/v1-e34-t34-backfile-seasons-import` |
| Session status | IN PROGRESS <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

**Stopped after the counts, waiting for the PM's ruling** (the PM's instruction of 2026-10-26). The
read-only `caselist backfile-survey` command is built and was run twice by the operator. Through the
documented API, **four complete archives exist in the backfile range**: LD and Policy of 2024-25 and
2025-26, 14.86 GB in all. PF has no complete archive in any season, and 2021-22 to 2023-24 answer
HTTP 500 for every caselist's downloads listing. Two findings the PM should read first. **This Mac
has 12 GiB free**, against an estimated 70 GB that the four imports would keep locally. And **PF
backfiles would need weeklies**, which Permitted use 8's wording ("from OpenCaselist's complete
archives") does not cover. The build has not started.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `backfile-import` | In progress | Counts done (ac1). Marker, import command and tests wait for the PM's ruling |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: counts before any import, sent to the PM with a proposed order | PASS, pending the PM's ruling | `DEBATE_ENV=dev uv run debate-research --json caselist backfile-survey` (operator, 2026-10-25) → exit 0: 65 caselists listed, 15 surveyed, 17 listing requests, 4 size requests. The re-run with `--first-season 2021-22 --last-season 2023-24 --no-sizes` → exit 0: 9 × `PROVIDER_UNAVAILABLE (HTTP 500)`. Counts in [`docs/data/caselist-backfile-seasons.md`](../data/caselist-backfile-seasons.md). Estimates and proposals under Decisions; sent as a relay prompt |
| ac2: with stand-in API and bucket, a backfile imports, parses and publishes; the weekly run and the landscape never include it; removal and a hold reach it; red first | NOT RUN | Not started: waits for the PM's ruling on the marker |
| ac3: the operator imports the first backfile caselist in dev and records its counts (operator) | NOT RUN | After the build, the seed (2026-10-29 or 30) and disk space |
| Node: `uv run pytest packages/debate_core/tests/application -k caselist` | NOT RUN | At the end of the build |

Tests so far: `test_caselist_backfile_survey.py` (core, 12 tests; CLI, 7 tests) and four `archive_size`
tests in `test_client.py` → all pass. A mutant that took the `HEAD` out of the download window
(`download=False`) failed `test_archive_sizes_are_paced_in_the_download_window_with_downloads`.

## Files changed

* `debate_core.integrations.opencaselist`: `declared_size`, a `HEAD` paced as a download, and
  `OpenCaselistClient.archive_size`.
* `debate_core.application.caselist.backfile_survey`: the survey.
* `debate_cli`: `caselist backfile-survey`, its container seam, and its row in the bucket-mode
  command classification (`NEVER_WRITE_A_BUCKET`).
* `docs/data/caselist-backfile-seasons.md`: the survey's counts.

## Deviations from the spec

None so far. Two will need the PM: PF has no complete archive, and seasons 2021-22 to 2023-24 serve
no archive at all.

## Decisions and assumptions

* **The size comes from a `HEAD`**, because the downloads listing carries no sizes. Each `HEAD` is
  paced as a download (8 a minute) and none is counted against the day's five bulk downloads, since
  no file is sent.
* **Parse time per source**: a sample of 100 DOCX sources each from this Mac's hsld26 and hspolicy26
  complete archives, parsed in one process with nothing written (2026-10-25, load average about 5):
  **LD 0.087 s, Policy 0.257 s**, 0 failures. The full pipeline's recorded wall-clock, with rebuild
  and publish (`docs/data/caselist-parse-report.md`, dev, 2026-10-12): LD 0.109 s, Policy 0.295 s.
  The estimates use the pipeline's figures.
* **Sources per archive, estimated**: a complete archive's zip is 1.043 × its members (hsld26:
  571,706,321 bytes against 548,239,217). This Mac's manifests give a mean of 129,935 bytes per LD
  source and 284,623 per Policy source. The parsed store is 3.96 × (LD) and 3.88 × (Policy) its
  sources' bytes.

| Caselist | Archive | Sources (est.) | Parse, rebuild, publish (est.) | Parsed store (est.) | Kept locally (est.) |
|---|---|---|---|---|---|
| `hspolicy25` | 3.96 GB | 13,300 | 66 min | 14.7 GB | 18.5 GB |
| `hsld25` | 4.37 GB | 32,200 | 59 min | 16.6 GB | 20.8 GB |
| `hspolicy24` | 2.56 GB | 8,600 | 42 min | 9.5 GB | 12.0 GB |
| `hsld24` | 3.97 GB | 29,300 | 53 min | 15.1 GB | 18.9 GB |
| **All four** | 14.86 GB | 83,500 | 3.7 h | 55.9 GB | 70.2 GB, plus one archive (up to 4.4 GB) in the inbox while it imports |

  Download time is not measured here (the run summaries keep sizes, not times): 2 to 12 minutes per
  archive at 50 to 200 Mbit/s. Import and publish of the sources at run 5's rate (2,177 members in
  161.5 s): about 40 minutes for an LD season. So 1.5 to 2.5 hours per caselist end to end. The
  bucket holds the same again: about 70 GB in dev, and in prod at the promotion.

## Operator follow-ups

The two survey runs above, done 2026-10-25.

## Follow-up work

None yet.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
