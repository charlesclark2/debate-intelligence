# Session report: v1-e30-t04-openev-importer

| | |
|---|---|
| Task | `v1-e30-t04-openev-importer` — OpenEv camp-file importer |
| Spec | [`plan_specs/v1/e30-caselist-ingestion/t04-openev-importer.yaml`](../../plan_specs/v1/e30-caselist-ingestion/t04-openev-importer.yaml) |
| Epic / release | `v1-e30-caselist-ingestion` / `v1.1` |
| Branch | `task/v1-e30-t04-openev-importer` |
| Session status | COMPLETE |

## Summary

`debate-research caselist import-openev <zip|dir> --year <yyyy> --event <ld|policy|pf>` imports
OpenEv camp files into the same local evidence store as caselist disclosures. The first step was a
refactor, not new code: read, classify, store and count moved out of `CaselistImportService` into
`SourceImportPipeline`, which takes a metadata extractor and a record writer. Both importers now
run on it, and the 39 v1-e30-t03 import tests pass with their file untouched. A camp file
byte-identical to a disclosed caselist file is a `DUPLICATE`: no second blob and no second source
document, and a `CampFile` linked to the existing digest.

Look at these first:

- **The cross-origin fix in the shared path.** The repository refused one digest under two
  origins, so the dedupe the spec asks for would have raised `Conflict`. That happened for a camp
  file after a caselist, and also for a later caselist week after a camp file.
- **The OpenEv manifest accumulates** across downloads rather than being rewritten by each one.
  The scheduled sync (v1-e34-t02) needs this.
- **Lab is parsed but not added to `CampFile`**, because of the data-minimization guard.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `shared-pipeline`: extract the shared source-import pipeline | Done | `pipeline.py`: `SourceImportPipeline`, `Classification`, `STORED_CLASSIFICATIONS`, generic `ImportedEntry`, `file_source`. `import_service` re-exports the moved names, so no importer of them changed. `manifest.py` gained shared row and write helpers, and caselist manifest bytes are unchanged. |
| `camp-metadata`: camp metadata parser and alias table | Done | `camp_metadata.py` and the packaged `camp_aliases.yaml` (DDI, Michigan, Gonzaga, SDI, NHSI, UTNIF with a few spellings each). Matching is by whole words and ignores case and separators. |
| `openev-service-and-cli`: OpenEv import service and command | Done | `openev_import_service.py`, `openev_manifest.py`, the `import-openev` command and container wiring, and the synthetic fixture under `tests/fixtures/openev/`. |
| `smoke-and-gates`: smoke check and quality gates | Done | Three OpenEv checks were added to `tests/smoke/test_caselist_import_smoke.py`. They are unmarked like the rest of that file, so they run in the default suite. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: importing the synthetic OpenEv fixture records a CampFile per file with camp, year, event and title; an unlisted camp gets `UNKNOWN` and a warning, not a failure | PASS | `uv run pytest packages/debate_core/tests/application/caselist/test_openev_import.py` → 26 passed. Covered by `test_every_member_is_read_exactly_as_the_expectations_say`, `test_one_camp_file_is_recorded_per_distinct_file_with_camp_year_event_and_title` and `test_an_unresolved_camp_is_recorded_as_unknown_with_its_warning`. All three assert against the hand-written `tests/fixtures/openev/expected_openev_import.json`. |
| ac2: a camp file byte-identical to a caselist file creates no second blob and is a DUPLICATE referencing the existing SourceDocument | PASS | Same run. The blob count grows by 9 for 11 camp files (10 distinct, 1 already stored). `existing_source` is the caselist record, and that record is unchanged afterwards. One digest is linked from both a disclosure and a camp file. The reverse order (camp files first, then all three caselist weeks) raises no Conflict and reproduces t03's `expected_summary.json` counts. |
| ac3: `manifests/openev/<year>-<event>.jsonl` in the evidence object store uses the caselist schema version and row layout plus camp fields; a re-import is a no-op | PASS | Same run. The key is `manifests/openev/2026-policy.jsonl`. Every row's keys equal a real caselist manifest row's keys plus the hand-listed camp fields, at the same `schema_version`. Re-importing gives identical manifest lines, zero new blobs, and unchanged camp-file and source records, including when the re-import runs on a later date. The smoke check confirms the file lands under `<data_dir>/objects/manifests/openev/` and that the on-disk tree is unchanged after a re-run. |
| ac4: both commands use the shared pipeline, and the t03 test suite passes unchanged | PASS | `uv run pytest packages/debate_core/tests/application/caselist/test_import_service.py` → 39 passed. `git diff --stat origin/dev -- packages/debate_core/tests/application/caselist/test_import_service.py tests/fixtures/caselist` → empty. |
| Node `shared-pipeline`: caselist import tests still pass after the refactor | PASS | `uv run pytest packages/debate_core/tests/application/caselist/test_import_service.py` → 39 passed, before and after the refactor. |
| Node `camp-metadata`: camp metadata tests pass | PASS | `uv run pytest packages/debate_core/tests/application/caselist/test_camp_metadata.py` → 37 passed |
| Node `openev-service-and-cli`: OpenEv import tests pass | PASS | `uv run pytest packages/debate_core/tests/application/caselist/test_openev_import.py` → 26 passed, 0 skipped (`-rs`) |
| Node `openev-service-and-cli`: command is registered | PASS | `uv run debate-research caselist import-openev --help` → exit 0 |
| Node `smoke-and-gates`: import smoke checks pass | PASS | `uv run pytest tests/smoke/test_caselist_import_smoke.py -rs` → 7 passed, 0 skipped (4 existing, 3 new) |
| Node `smoke-and-gates`: type check passes | PASS | `uv run pyright packages/debate_core packages/debate_cli` → 0 errors, 0 warnings, 0 informations |
| Node `smoke-and-gates`: import boundaries hold | PASS | `uv run lint-imports` → Contracts: 5 kept, 0 broken |

Wider check, run by the session in about 15 s:
`uv run pytest packages/debate_core/tests/application packages/debate_core/tests/integrations/local packages/debate_core/tests/domain/caselist packages/debate_cli/tests tests/smoke tests/fixtures -q`
→ 1100 passed. That was before the final future-date commit. After it, the caselist, CLI and
smoke subset gave 473 passed. `uv run scripts/validate_specs.py` → OK: 282 files.

The hand-written expectations held against the implementation on the first run with one
exception. For the second copy of a file within one download,
(`Counterplan_v2`), I had written `existing_origin: OPENEV`, and the dry-run test showed that a
dry run and a real run disagreed on that field. I settled the rule deliberately: `existing_origin`
names the record the bytes had *before this import*, so a second copy within one download has
none. I then changed the expectation and the pipeline to match that rule. The expectation was not
copied from output.

## Files changed

- `packages/debate_core/src/debate_core/application/caselist/`
  - `pipeline.py` (new): the shared pipeline.
  - `import_service.py`: now runs on the pipeline.
  - `manifest.py`: shared row, render, read and atomic-write helpers.
  - `camp_metadata.py` and `camp_aliases.yaml` (new).
  - `openev_manifest.py` (new): the `<year>-<event>` key, the camp fields and the merge.
  - `openev_import_service.py` (new).
- `packages/debate_core/tests/application/caselist/`: `test_camp_metadata.py` and
  `test_openev_import.py` (both new).
- `packages/debate_cli/`:
  - The `import-openev` command and its `--json` summary.
  - `ServiceContainer.openev_import` and its name in `SERVICE_NAMES`.
  - `test_app.py`: the `doctor` services list gains `openev_import`, as that test asks later
    tasks to do.
- `tests/fixtures/openev/` (new):
  - `build_synthetic_openev.py`: invented camps. It reuses the caselist fixture's deterministic
    `.docx`/`.pdf` writers and one of its bodies.
  - `camp_aliases.yaml`: the invented camps.
  - `expected_openev_import.json`: hand-written.
- `tests/smoke/test_caselist_import_smoke.py` and `tests/smoke/README.md`: the OpenEv checks.
- `plan_specs/.../t04-openev-importer.yaml`: Goal phase `Succeeded`.

## Deviations from the spec

1. **The shared path had to change how a source document is written, not only be extracted.**
   `CaselistRepository.put_source` raises `Conflict` for a digest already filed under another
   origin. So "content identical to a caselist source is stored once and linked from both records"
   could not work through it in either direction. `pipeline.file_source` keeps the existing
   record when the other origin filed the same size and format; a real contradiction still goes to
   `put_source` and raises. `CaselistImportService` now writes sources through it too. That changes
   t03 behaviour only in a case that previously crashed, which needs an OpenEv source to exist, and
   the t03 suite is unchanged and passes. The PM may want the spec's "reuse" wording to say that
   the reuse includes this.
2. **Two CLI flags beyond the spec's `--year`, `--event`, `--dry-run` and `--json`:**
   - `--snapshot YYYY-MM-DD` (default: today, UTC). `CampFile.snapshot` and the
     `SourceDocument` seen dates are required dates, and the spec's command gives no date.
   - `--camp-aliases PATH`. This makes the "editable alias table" usable without editing the
     installed package, and it is how the smoke check points at the invented camps.
3. **Lab is parsed but not added to `CampFile`.** The node says "parse … optional lab", and the
   parser returns it and the manifest carries it. `tests/domain/caselist/test_minimization.py` pins
   every caselist model's exact field set as a data-minimization guard, and OpenEv lab names are
   often instructors' names. So I did not widen the entity. The manifest row already carries the
   same information in its `path`. If the PM wants `lab` on the record, that is a deliberate edit
   to the entity and to that guard.

## Decisions and assumptions

- **The OpenEv manifest accumulates.** Each import is merged into
  `manifests/openev/<year>-<event>.jsonl`, and the existing manifest's `{path: sha256}` is the
  baseline.
  - A path whose outcome is unchanged (`UNCHANGED`, or skipped or suppressed for the same reason)
    keeps its earlier row byte for byte. That is what makes a re-import a no-op whatever date it
    runs.
  - New and `CHANGED` paths get this import's row.
  - Paths absent from this download keep theirs. `REMOVED` never appears for OpenEv, because a
    file missing from a download was not fetched, not withdrawn.
  - Without this, v1-e34-t02's one-file weekly imports would each erase the rest of the release.
- **Camp resolution.**
  - The camp comes from the outermost folder that names a camp, and the folder below it is the
    lab. Otherwise it comes from the filename prefix, longest spelling first.
  - When the folder and the prefix disagree, the folder wins and a warning is recorded.
  - The title is the filename minus its extension and the camp prefix, and nothing else.
  - The sync's `openev-<id>-` inbox prefix is taken off first.
  - Warnings never quote the path.
- **Duplicates within one release.** One `CampFile` per (digest, year, event), the repository's
  key. It is the first in path order, and each copy still gets its own manifest row.
- **An `UNCHANGED` camp file writes nothing**, not even a widened seen range. This keeps
  re-imports record-for-record identical.
- **A future `--snapshot` is refused before anything is read** (`UnrecordableImportDate`, exit 1).
  Before this fix it surfaced as `INTERNAL_ERROR` after the first blob had been stored. I found
  this by running the command, not through a test.
- **Where the files go.** The manifest's event is lowercase (`2026-policy`), which matches the
  `<year>-<event>` shape `publish_plan` already validates. A test builds a publish plan from the
  manifest, and its source keys fall under `raw/openev/2026/sha256/…`, as settled in the
  v1-e30-t05 review.

## Operator follow-ups

The full test suite was not run by the session (working agreements §2). The neighbouring suites
above passed.

**Operator command** (expected runtime about 1–3 min)
Where: your Mac, in the task worktree `debate-intelligence-worktrees/v1-e30-t04-openev-importer`
```bash
uv run pytest
```
Success looks like: no failures. Paste the last 5 lines back.

For v1-e30-t06 (not this task): run the 106 real Policy files with `--dry-run` first and look at
`unknown_camps` in the `--json` output. Any camp it reports belongs in `camp_aliases.yaml`, or in a
table passed with `--camp-aliases`, before the real import.

## Follow-up work

- **`docs/architecture/evidence-store-layout.md` line 104** shows
  `manifests/openev/2026-ndi.jsonl — one camp's files`. The spec, `publish_plan` and this importer
  file by `<year>-<event>` (`2026-policy.jsonl`, one year's camp files for one event). The example
  should be corrected. That doc is outside this task's packages.
- **v1-e34-t02.** The service takes `recorded_manifest` lines and returns `manifest_lines`, so the
  sync can compose it exactly as the CLI does (`read_manifest_lines` → `import_release` →
  `write_manifest_lines`). `OpenEvFile` from the API also carries `camp` and `lab`, which the sync
  could prefer over path parsing. That would be a change to that task, not this one.
- **v1-e30-t07.** `import_release` takes `suppressed_hashes` (default empty), as `import_archive`
  does. Neither command has a flag for it yet. The suppression list port is t07's.
- **`caselist import`** probably has the same future-`--snapshot` behaviour, since
  `ArchiveSnapshot` uses the same `SnapshotDate`. I did not check that, and changing it is outside
  this task.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-09-22

**Notes:**

All three deviations upheld; amendments are `24a44c1` on `specs/openev-rulings`.

**The cross-origin fix was required, not a liberty.** t04's own description asks for content identical
to a caselist source to be stored once and linked from both records, and `put_source` would have
raised `Conflict` on the second origin instead - so the spec asked for a thing the port refused to
do. Changing the caller rather than the port is the right half to change, and updating
`SourceDocument.origin` to "which import **first** stored these bytes" and `.caselist` to "first seen
in" is the part that matters most: it makes the order-dependence visible in the model instead of
leaving it as a surprise for whoever builds on it. `v1-e30-t02` now records the consequence - which
origin a shared hash carries depends on import order, so the authoritative cross-origin picture is
the set of disclosure and camp-file records sharing a sha256, never the origin field alone, and E31
and E32 read it that way.

**The lab decision was verified rather than taken on trust**, because "kept in the manifest, kept out
of the model" could easily have been a distinction without a difference. It is not:
`common_member_fields` already writes `path`, and an OpenEv path is `<year>/<camp>/<lab>/<file>`, so
the manifest's `lab` restates something the row carries anyway, while `CampFile` - which E31 and E32
query and report on - stays free of a field that is sometimes an instructor's name. Redundant where
it is already exposed, absent where it would be newly queryable, is exactly the right shape.

**Both new flags are right.** `--snapshot` defaulting to today is the correct answer for a release
that has no weekly date of its own, and because neither flag is required, `v1-e34-t02` calls this
command without either. Both are now in the spec's signature.

**Hand-written expectations earning their keep again**, per working agreement 6: they matched the
implementation except in one field, and that one mismatch was a real inconsistency the dry-run path
exposed. An expectation generated from the implementation would have agreed with the bug. Same for
refusing a future `--snapshot` before the first blob is written rather than after - found by running
the command, which unit tests would not have surfaced.

**One correction wanted before the PR**, and it is a docstring rather than behaviour. `put_source`
still says it raises `Conflict` on a differing origin "which would mean two different files are being
filed under one hash". That rationale is now false, and it is the sentence a future adapter author or
caller will read: identical bytes under two origins are the same file, which is the premise of this
whole task. Keep the defensive refusal, correct the reason - it should say no caller should reach it
because the importer links to the existing record, and point at v1-e30-t04.

Full-suite run is the operator's, as filed.
