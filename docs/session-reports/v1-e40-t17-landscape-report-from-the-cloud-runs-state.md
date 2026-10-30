# Session report: v1-e40-t17-landscape-report-from-the-cloud-runs-state

| | |
|---|---|
| Task | `v1-e40-t17-landscape-report-from-the-cloud-runs-state` — A landscape report counts the weeks the cloud run pulled, from a copy restored from the bucket |
| Spec | [`plan_specs/v1/e40-cloud-caselist-run/t17-landscape-report-from-the-cloud-runs-state.yaml`](../../plan_specs/v1/e40-cloud-caselist-run/t17-landscape-report-from-the-cloud-runs-state.yaml) |
| Epic / release | `v1-e40-cloud-caselist-run` / `v1.8` |
| Branch | `task/v1-e40-t17-landscape-report-from-the-cloud-runs-state` |
| Session status | IN PROGRESS <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

<!-- 3-6 sentences: what was built, how it fits the epic, anything the PM should look at first. -->

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

### Counts: what `landscape report` reads and writes (ac1, 2026-10-30)

Traced in code at `cddb5f0` (`ServiceContainer.landscape_run`, `landscape_model_stage`,
`LandscapeRunService.run`, the stores under `debate_core.integrations.landscape`), with sizes measured
read-only on the operator's dev data directory. Paths are under the data directory unless marked.

| Path | Report (dry run) | Report (`--publish`) | A restored copy holds it? |
|---|---|---|---|
| `objects/manifests/<caselist>/<date>.jsonl` | read: caselists, snapshots, disclosures, staleness | same | **Yes**, every week the cloud ran |
| `parsed/<caselist>/<parser version>/` | read: cards, occurrences; the model stage's card texts | same | **Yes**, this build's version (`2026.10.27-docx-7`); the data dir holds `2026.10.20-docx-6` only |
| `blobs/sha256/…` (raw sources) | read: plan texts and analytic texts parse what their caches lack, and the quoted CP texts, planks, alternatives and roles of the ballot are re-read from raw bytes on every run | same | **Only with `--with-sources`**, for the `--snapshot` weeks named; the data dir holds everything through 2026-10-20 (4.0 GB, all caselists) |
| `suppression/` | read | same | **Yes**, reconciled with the bucket's |
| `caselist-sync-runs.jsonl` (run log) | read: the failed-run line of staleness | same | **Yes**, the cloud's; the data dir's stops on 2026-10-25 |
| `debate.sqlite3` | not read | not read | Yes (unused here) |
| `config/landscape/` (checkout) | read | read | n/a: the checkout |
| `landscape/classifications/<caselist>.jsonl` (47 MB) | read | read, written | **No**: data dir only |
| `landscape/review/<caselist>/<topic>-review-queue.csv` | not written | written | **No** |
| `landscape/plan_texts/<caselist>.jsonl` (0.9 MB) | read | read, written | **No** |
| `landscape/analytic_texts/<caselist>.jsonl` (1.7 MB) | read | read, written | **No** |
| `landscape/scan-acceptances/<caselist>.jsonl` | read | read, written on an accept | **No** |
| `landscape/model-cassettes/<prompt>/` | read under `replay` | read under `replay`; `live` passes through and records nothing | **No** (absent today: no model run yet) |
| `usage/<day>.jsonl` (model usage, the budget) | not written | written per live call | **No** (absent today) |
| `reports/landscape/<caselist>/<snapshot>/` (7 files) | not written | written; read later by removal residue and the annual purge | **No** |
| `landscape/local-classifier/<caselist>/` (47 MB) | not read | not read (`scripts/compare_local_classifier.py` only) | **No** |
| bucket `reports/landscape/<caselist>/<snapshot>/` | `head` per file (with `--publish --dry-run`) | `head`, `put` | n/a |
| bucket run lock | not taken | taken (dev is in bucket mode) | n/a |

Three facts the proposal rests on:

1. **The plan-text and analytic-text caches key on the running build's parser version**, and hold
   `2026.10.20-docx-6` only. A `docx-7` build's next report re-parses every on-topic hspolicy26
   source for both, from raw bytes, whichever store it reads. The analytic texts' first fill took
   551 s on 2026-10-24. The classification cache keys on card fingerprints and taxonomy, not parser
   version.
2. **Raw bytes are read on every run**, not only on a cache miss: the quoted texts are re-read. So a
   copy restored with the newest week's sources alone lacks the bytes of every older quoted source.
3. **`DEBATE_STORAGE__DATA_DIR=<copy>` would move all of the "No" rows into the copy**: the
   classification cache, the review queue, the text caches, the scan acceptances, the bundle, and the
   usage log the model budget is counted from. Each would be lost when the copy is deleted.

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
