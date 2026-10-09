# Session report: v1-e30-t08-import-metadata-defects

| | |
|---|---|
| Task | `v1-e30-t08-import-metadata-defects` — Importer metadata defects found by the backfill |
| Spec | [`plan_specs/v1/e30-caselist-ingestion/t08-import-metadata-defects.yaml`](../../plan_specs/v1/e30-caselist-ingestion/t08-import-metadata-defects.yaml) |
| Epic / release | `v1-e30-caselist-ingestion` / `v1.1` |
| Branch | `task/v1-e30-t08-import-metadata-defects` |
| Session status | PARTIAL: all three plan nodes done and their criteria pass; ac2's re-import and ac4's dev and prod status are the operator's, and not yet run |

## Summary

This task fixes both defects and leaves the operator's runs open:

* **Camp detection.** Camp detection now finds an alias-table spelling anywhere in an OpenEv
  filename, by whole word and never by substring. A camp folder still wins. A filename that names
  two different camps is `UNKNOWN` with a warning. The title is the stem without its camp block:
  the camp, the year directly after it, and trailing lab initials.
* **The metadata re-import.** The new `caselist reimport-openev-metadata` re-derives camp, lab, title
  and warnings for a release already held, from the paths its manifest records. It downloads
  nothing, writes no blob, and changes no sha256 and no manifest key. An ordinary `caselist publish`
  re-uploads the changed manifest; publish was not loosened. A moto test shows the old manifest
  left behind as one noncurrent version.
* **NEW and first-seen.** NEW is now documented, in the code, the CLI caption, the runbook and the
  data doc, as "not present in the preceding snapshot". Each weekly import also reports
  `first_seen`, counted from the caselist's own earlier manifests. It appears in the report,
  `caselist import`'s JSON and caption, and as an additive key on the manifest summary row.
* **Measured on the real release, read-only and in memory.** 74 of the 105 camp files resolve
  (Michigan 40, DDI 27, UTNIF 3, Gonzaga 2, NHSI 2), 31 stay `UNKNOWN`, and 74 titles change.

**Look first at Deviation 1.** The spec says the alias table already lists every camp involved.
It does not: the 31 that stay `UNKNOWN` name 10 camps the table lacks. I did not add them. That is
your call, and the re-import corrects them whenever they are added.

**The Goal stays `InProgress`.** ac2 (the operator's re-import of the dev store) and ac4 (`caselist
status` clean against dev, and prod) can only close after the operator's runs. The exact commands
and expected counts are under Operator follow-ups. Merge with `scripts/task pr --partial` if those
runs are all that is left.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `camp-detection` — Camp detection by alias, not by position | Done | Shown red first on the original code (17 of 27 new tests failed, and the tie case returned `DDI`, a guess). Fixture set built from the real naming shapes with invented titles and initials. `Michigan Classic` added as a spelling of the listed camp Michigan (Deviation 2). |
| `reimport-command` — Metadata re-import for files already held | Done (code); the operator's run is open | `caselist reimport-openev-metadata`. The pure re-derivation is in `openev_metadata_reimport.py`, and the record writes are in `OpenEvImportService.reimport_metadata` (Deviation 5). Command, expected counts and procedure are in the runbook and under Operator follow-ups. |
| `new-versus-first-seen` — NEW means week-over-week; first-seen is its own count | Done | Shown red first on the original code: `first_seen` is absent from output and manifest, the caption doesn't say what NEW is measured against, and the docstring calls NEW "not seen before, under this path or any other". The three-snapshot test reproduces 25 NEW against 16 first seen. |

## Acceptance criteria

The session ran every command from the task worktree on 2026-10-08. The real-data measurements
were read-only and ran in memory over the operator's dev store, and they print counts only
(Decisions, "What I read of the real files").

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1** — camp found wherever it appears, against the alias table, UNKNOWN only when no alias matches; fixtures for camp at the start, at the end, in the folder, and absent | PASS | `packages/debate_core/tests/integrations/opencaselist/test_camp_names_in_openev_files.py`: one row per real shape (the end-of-name shapes, start, folder, three absent shapes, all invented), each also run through the sync's `openev_inbox_name`, plus the substring and tie cases. All 27 pass. On the original code 17 failed and 10 passed (red output below). Absent shapes stay `UNKNOWN` with a warning: `test_an_absent_camp_is_unknown_with_a_warning_and_never_a_guess`. |
| **ac2** — re-importing the 105 camp files in the dev store corrects camp and title in place, changes no sha256 and no manifest key, downloads nothing; the operator runs it; this task supplies the command and before/after counts | NOT RUN (operator) | The code and its tests pass: 15 service tests, 3 publish-and-status tests on moto, 6 CLI tests and 1 smoke check. Expected counts are measured read-only from the real manifest: before `UNKNOWN` 105, after the table under Operator follow-ups, 74 titles changed, 105 rows changed, 102 camp-file records updated, 0 missing, 0 blobs missing. The in-memory re-derivation keeps the same key and 107 lines. No non-derived field changes on any member row; only the summary's `warnings` changes (105 → 31). The re-import itself is the operator's (PM decision). Recording in the data doc follows it (PM decision, superseding "v1-e30-t06 records them"). |
| **ac3** — NEW documented and reported as "not present in the preceding snapshot" by the docstring and every consumer; a distinct first-seen count beside it; a three-snapshot test asserting the 25-versus-16 shape | PASS | Consumers corrected: the `import_service` docstring, `ImportReport`, the manifest docstring and summary row, `caselist import`'s JSON (`first_seen`) and caption (`NEW: not present in the <date> snapshot; N first seen in <caselist>`), the runbook and the data doc. `test_new_count_and_first_seen.py`: NEW `[9, 3, 13]` = 25 against first-seen `[9, 3, 4]` = 16; the CLI test asserts the same through `caselist import`. |
| **ac4** — both defects have a regression test that fails against the current code and passes after; neither fix alters a stored byte, sha256 or manifest key, proved by `caselist status` against the dev bucket finding no drift | Regression tests: PASS. Status proof: NOT RUN (operator) | Red on the original code: below. Green now: the node criteria and the full suite. Byte, sha256 and key: `test_reimport_touches_no_blob`, `test_reimport_changes_no_sha256`, `test_reimport_keeps_the_release_manifest_key` and `test_reimport_command_rewrites_only_the_release_manifest_at_its_own_key`. On moto, status reports one mismatch (the manifest key) after the re-import and is clean after publish. The dev and prod `caselist status` runs are the operator's. |
| Node `camp-detection`: `uv run pytest packages/debate_core/tests/integrations/opencaselist/ -k camp` | PASS | `27 passed in 8.39s` |
| Node `reimport-command`: `uv run pytest packages/debate_core/tests/application/ -k reimport` | PASS | `20 passed in 6.93s` (the 15 service and 3 republish tests, plus two existing removal tests whose names contain "reimported") |
| Node `new-versus-first-seen`: `uv run pytest packages/debate_core/tests/application/ -k "first_seen or new_count"` | PASS | `11 passed in 5.79s` |

**Shown failing first.** I ran each regression test against the original code: commit `86842bc`,
in a temporary worktree for the first-seen tests, which was removed afterwards.

* **Camp detection**, `pytest packages/debate_core/tests/integrations/opencaselist/ -k camp` →
  `17 failed, 10 passed`. Every camp-at-the-end shape came back `UNKNOWN`, for example
  `assert ('UNKNOWN', '...an 2026 QRSV') == ('Michigan', ... Shipping DA')` and
  `assert ('UNKNOWN', '...- UTNIF 2026') == ('UTNIF', 'Saltmarsh T')`. The tie case returned a
  guess: `assert 'DDI' == 'UNKNOWN'`. The ten that passed were the start, folder and absent shapes,
  which the old code already handled.
* **NEW against first-seen**, `pytest packages/debate_cli/tests/test_caselist_import_first_seen.py`
  → `3 failed`. NEW was already `[9, 3, 13]`; then `assert [None, None, None] == [9, 3, 4]` for
  `first_seen`, and `assert (13, None) == (13, 4)` for the summary row. The caption assertion
  failed too: the old caption says only `against 2026-08-18`.
* **The docstring**, read from the original module: "not present in the preceding snapshot"
  `False`, "have not been seen before, under this path or any other" `True`.

**Mutation testing.** Each run used a new, empty `HYPOTHESIS_STORAGE_DIRECTORY` (created with
`mktemp -d` per run, empty before it) and ran in two batches of under two minutes. These tests use
no Hypothesis properties, so database isolation is set as required but cannot affect them. Each
mutant was applied by exact replacement, and the script refused if its anchor was not found
exactly once. The file was then restored with `git checkout`, and the tree checked clean. Every run
executed its tests; none errored at collection.

| Mutant | Tests run | Result | Time |
|---|---|---|---|
| Position-based detection restored (only a match at the start of the name counts) | camp tests | caught: 36 failed, 55 passed | 5 s |
| Substring instead of whole-word matching | camp tests | caught: 7 failed (`Michiganders`, `QDIX`, `Quillfeathers`, the longest-spelling and whole-word tests) | 3 s |
| The multiple-camp tie returns the first camp (a guess) | camp tests | caught: 2 failed, both tie tests | 3 s |
| The re-import writes the manifest to another key | re-import tests | caught: 4 failed (the key tests in the service and the CLI) | 3 s |
| The re-import reads and re-stores each blob | re-import tests | caught: 12 failed, by the blob store that refuses `get` and `put` | 4 s |
| First-seen computed against the blob store (`newly_stored_blobs`), not the caselist's manifests | first-seen tests | caught: 4 failed (another caselist's bytes, a camp file disclosed, re-import, the CLI caption) | 3 s |

The last row is why the cross-caselist and camp-file tests exist. The 25-versus-16 test alone does
**not** catch that mutant: in its three weeks, every file first seen is also a new blob.

**Whole suite and checks.** `uv run pytest -n auto -m "not slow and not live"` → `4672 passed,
1 skipped in 68.18s`. `ruff check .`, `ruff format --check .`, `pyright` (0 errors), `lint-imports`
(11 contracts kept), `scripts/check_thin_handlers.py`, `scripts/check_links.py`,
`scripts/docs_index.py --check-descriptions` and `scripts/check_command_blocks.py --base origin/dev`
all pass. `uv run scripts/validate_specs.py` → `OK: 319 files, 38 epics, 261 tasks, 20 releases`.

## Files changed

* **`packages/debate_core/src/debate_core/application/caselist/`**
  * `camp_metadata.py`: whole-word detection anywhere in the filename, the tie rule, the camp-block
    title rule, and reworded warnings.
  * `camp_aliases.yaml`: the `Michigan Classic` spelling, and comments for the new matching.
  * `openev_metadata_reimport.py` (new): the pure re-derivation and its report.
  * `openev_import_service.py`: `reimport_metadata`, which writes the corrected camp-file records.
  * `import_service.py`: NEW's docstring, a first-seen section, `ImportReport.first_seen`, and the
    optional reader of earlier manifests.
  * `evidence_listing.py`: `digests_in_earlier_manifests`.
  * `manifest.py`: the summary row's `first_seen`, and the docstring on what NEW and `first_seen`
    mean.
  * `openev_manifest.py`: the docstring on why a release summary has no `first_seen`.
* **`packages/debate_core/src/debate_core/domain/caselist/entities.py`**: `CampFile.file_title`'s
  description no longer says "without camp prefix" (Deviation 4).
* **`packages/debate_cli/`**: the `caselist reimport-openev-metadata` command and table, `first_seen`
  in `caselist import`'s JSON and caption, and the container wiring for both the CLI import and
  the scheduled sync's importer (Deviation 4).
* **Tests**
  * New: the camp-name fixture set under `tests/integrations/opencaselist/`; the re-import service,
    publish-and-status (moto) and CLI tests; and the first-seen service and CLI tests.
  * Updated, by hand, where they encoded the old rules: `test_camp_metadata.py`, one warning text
    in `test_openev_import.py`, and its layout test (Deviation 6).
* **`tests/smoke/`**: a smoke check that the new command runs through the installed build and, with
  the same table, changes nothing. Its README row is updated.
* **`docs/runbooks/caselist-backfill.md`**: NEW's wording, the camp-metadata correction section with
  the operator commands and expected counts, and a recovery row for the expected one-manifest
  mismatch.
* **`docs/data/caselist-backfill-2026-09.md`**: NEW's and first-seen's wording only. The dated
  results section follows the operator's run.

## Deviations from the spec

1. **The alias table does not list every camp the real files name.** The spec says "the alias
   table already lists every camp involved", and the t06 report said the same. Measured
   read-only, 31 of the 105 files name, at the camp position, one of **10 camps the table does not
   list**. They stay `UNKNOWN` with a warning, as ac1 and the forbidden list require. I added none
   of them. Which camps the table holds is a decision about the table, and some of the ten names
   identify schools, so they are not named in this report (policy rule 5). The operator can list
   them locally from the release manifest. Once they are added to `camp_aliases.yaml`, running the
   same re-import corrects those 31 files with no other change. **PM decision needed:** add them
   in a follow-up task, or accept 31 `UNKNOWN`.
2. **One spelling added to the table.** `Michigan Classic` is now a spelling of the listed camp
   `Michigan`. Five real files use it. Without it the camp still resolves on the word `Michigan`,
   but `Classic` stays in the title, and the year and initials after it do not come off. It is a
   spelling of a camp the table lists, so detection still matches nothing outside the table.
   Measured both ways, read-only: the camp counts and the 74 titles changed are the same with or
   without it. Without it, 5 resolved titles keep `Classic`, the year and the initials.
3. **The camp-detection node's `outputs` names `integrations/opencaselist/openev.py`.** Detection
   lives in `application/caselist/camp_metadata.py`, the OpenEv importer's metadata extractor, and
   `openev.py` is unchanged. The node's test path, `tests/integrations/opencaselist/`, holds the new
   fixture set. It runs each shape both as downloaded by hand and as the sync's
   `openev_inbox_name` saves it, which is the integration's part in this.
4. **Files outside `constraints.packages`.** The PM's instructions name the CLI table and the
   runbook, and an operator command needs a CLI surface. Outside the listed packages, this task
   changed:
   * `debate_cli`: the command, the output and the container wiring;
   * `tests/smoke/` and its README: the smoke check working agreement 5 asks for;
   * `docs/runbooks/caselist-backfill.md`;
   * the one-line field description in `debate_core.domain`.
5. **The re-import's record writes are in `OpenEvImportService`, not a service of its own.** The
   guard in `test_import_paths_consult_suppression.py` fails any module outside the importers that
   writes caselist records. I did not widen it. The write moved to the OpenEv importer, which
   holds the suppression list and now checks it at the write (`SuppressedWriteRefused`), as the
   pipeline does. The pure re-derivation stays in its own module.
6. **The OpenEv release summary has no `first_seen`.** `test_openev_import.py`'s layout test
   required the release summary to carry every caselist summary key. It now excludes this one
   weekly key, and asserts it is absent. A release has no earlier snapshots to count against.
   Adding even a `null` key would change the bytes of every release manifest already written on
   its next `import-openev`.
7. **Recording in the data doc.** ac2 says v1-e30-t06 records the results. Per the PM, this task
   appends its own dated section to `docs/data/caselist-backfill-2026-09.md` after the operator's
   run. This session changed only that file's wording on NEW and first-seen, plus one pointer.

## Decisions and assumptions

* **What I read of the real files.** I read the camp files' names from the release manifest in
  `~/.debate-research/dev/objects/manifests/openev/2026-policy.jsonl`, read-only. To learn the
  shapes, I printed an abstracted token shape rather than the names: alias hits, years, runs of
  capitals, other words. I ran the new detection and the re-derivation over the names in memory,
  with counts printed only. Camp-file records were counted from `debate.sqlite3`, opened
  `mode=ro`, and the blob tree was checked for presence. Each run took about 0.01 s. No real file
  name, title, school, team code or person's name is in a fixture, this report or a commit.
* **What the real names look like (shapes only).** All 105 sit one folder deep, in folders named
  for the kind of argument, never for a camp. The camp comes after the title and a ` - `, then the
  year, then one to four capital letters for the lab, with a `(1)` copy marker on one file. No
  file names two camps, and no folder names one.
* **The title rule.** The title is the stem without the camp block: the camp's words, the year
  directly after them, and one to four capitals directly after that year, if they end the name
  apart from a copy marker. What is left either side is joined with one space. Anything else stays:
  * a year that is not directly after the camp;
  * five or more capitals, or a word such as `Aff`;
  * capitals that do not end the name.

  Each case has a test. An `UNKNOWN` file keeps its whole stem, as before. The four resolved
  titles that end in capitals end in an argument abbreviation (`CP`, `DA` or `K`) that comes before
  the camp, so it is part of the title. This changes one existing expectation:
  `QDI 2026 Harbor Tariffs Aff` is now `Harbor Tariffs Aff`, since the year after the camp goes too.
* **Folders.** A folder is still matched on its whole name. Two folders naming different camps are
  `UNKNOWN`, the same tie rule as the filename. When the filename names a different camp from the
  folder, the folder wins with a warning, and the filename's camp block still comes off the title,
  as the prefix did before.
* **Warnings were reworded.** "no folder and no filename prefix names a camp" had become untrue,
  so it now reads "no folder and no word of the filename names a camp". That is why all 105 rows
  change on the re-import, the 31 still `UNKNOWN` included.
* **What the re-import corrects.** One camp-file record per digest, from that digest's first row
  in path order: the record the importer made. Its digest, year, event and import date stay. A
  record is never created; a missing one is counted. The blob store is only asked whether each
  digest is held. The summary row is recounted the way the importer counts it, which changes only
  its `warnings`.
* **Publish was not changed.** A manifest is not content-addressed: the publisher uploads a listed
  manifest whose recorded digest differs from the local one (`_publish_manifest`), so a corrected
  manifest is republished by the ordinary command. That is by design, not drift protection; the
  drift check is `caselist status`. Between the re-import and the publish, `status` exits `1` with
  one checksum mismatch, on the manifest's own key, and every source present. The runbook says so,
  because the CLI's hint ("a checksum mismatch needs a person") does not fit this case. Versioning
  keeps the superseded manifest as a noncurrent version for the retention window: 30 days in dev,
  365 in prod (`infrastructure/envs/*/terraform.tfvars`).
* **First-seen.** First-seen counts the distinct stored digests (NEW, UNCHANGED, CHANGED,
  DUPLICATE) that no stored row of the caselist's local manifests for strictly earlier snapshots
  names. "Strictly earlier" matches `_previous_snapshot`, so a re-import reports the same count. A
  malformed earlier manifest fails the import (`UnreadableManifest`) rather than being counted
  around. The importer takes the reader as an optional constructor argument, which the composition
  root passes to both `caselist import` and the sync's importer. A service built without one
  reports `first_seen` as `None` and writes `null`.
* **The manifest key is additive.** Under v1-e34-t07's rule `schema_version` stays `1`. No existing
  weekly manifest is rewritten to add it. Two side effects:
  * re-running `caselist import` on an archive imported before this change writes the key into
    that manifest, which then differs from the bucket until it is published (the sync never
    re-imports an imported week);
  * a later removal's manifest rewrite keeps `first_seen` as the import recorded it, as it keeps
    `members`.

## Operator follow-ups

All in the dev store, `~/.debate-research/dev`, as the backfill's prod publish was. From this task
worktree before the merge, or from the repository root of any checkout of `dev` that includes
`v1-e30-t08`. These are the runbook's section "After the backfill: correct the camp files' camp
and title".

Expected counts, measured read-only from the release manifest on 2026-10-08:

| Camp | Files before | Files after |
|---|---|---|
| DDI | 0 | 27 |
| Gonzaga | 0 | 2 |
| Michigan | 0 | 40 |
| NHSI | 0 | 2 |
| UTNIF | 0 | 3 |
| UNKNOWN | 105 | 31 |

Also expected: 74 titles changed, 105 rows changed, 102 camp-file records updated, 0 missing, 0 not
held locally.

**1. Dry run** (seconds). Read the table it prints against the one above.

```bash
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e30-t08-import-metadata-defects
export DEBATE_ENV=dev DEBATE_STORAGE__DATA_DIR="$HOME/.debate-research/dev"
uv run debate-research caselist reimport-openev-metadata --year 2026 --event policy --dry-run
```

Success looks like the table above and the caption `105 file(s), 74 title(s) changed, 0 not held
locally. Planned only; nothing was written.`

**2. Re-import, dev publish, dev status** (seconds, about a minute, then a few minutes).

```bash
aws sso login --profile debate-dev-evidence
uv run debate-research --json caselist reimport-openev-metadata --year 2026 --event policy
uv run debate-research caselist publish --caselist openev --snapshot 2026-policy
uv run debate-research caselist status
unset DEBATE_ENV DEBATE_STORAGE__DATA_DIR
```

Success looks like this:

* the JSON shows `"camps_after"` as above, `"titles_changed": 74`, `"camp_files_updated": 102` and
  `"blobs_missing": 0`, with `"manifest"` naming `objects/manifests/openev/2026-policy.jsonl`;
* the publish shows 0 uploaded, 102 skipped and the manifest `uploaded`;
* `status` exits `0`, **Every snapshot agrees**, all 41 snapshots.

Paste the JSON's counts and the status caption back.

**3. Prod publish and prod status** (about a minute, then a few minutes). Only after step 2 is
clean.

```bash
aws sso login --profile debate-prod-evidence
export DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR="$HOME/.debate-research/dev"
uv run debate-research caselist publish --caselist openev --snapshot 2026-policy --dry-run
uv run debate-research caselist publish --caselist openev --snapshot 2026-policy --confirm-prod
uv run debate-research caselist status
unset DEBATE_ENV DEBATE_STORAGE__DATA_DIR
```

Success looks like this:

* the dry run plans 0 uploads;
* the real run uploads the manifest and no source;
* `status` exits `0` with all 41 snapshots in sync.

**4. Record it.** Append a dated section to `docs/data/caselist-backfill-2026-09.md`: the before
and after camp counts, the titles changed, and both status results (`dev status: in sync`,
`prod status: in sync`). Send the results back to this session and it will write the section.
Then ac2 and ac4 can be marked PASS and the Goal set to `Succeeded`.

## Follow-up work

* **E30, the alias table: 10 camps named by 31 real camp files are not listed** (Deviation 1).
  Adding them is a table change plus the same re-import. Whoever adds them should read the names
  from the release manifest locally, not from any document.
* **E30 / E34, `caselist status`'s hint for a mismatched manifest.** The CLI says "a checksum
  mismatch needs a person" for every mismatch. A manifest key that differs only because it was
  legitimately rewritten (by this re-import, or by a removal before its republish) needs a
  publish, not a person. The status report could tell a manifest mismatch from a source mismatch.
* **E30, `first_seen` after a removal.** A removal's manifest rewrite drops suppressed rows but
  keeps the summary's `first_seen` as recorded, so it can count a file the removal took out. That
  matches how `members` is kept. If reports come to rely on `first_seen`, the removal could recount
  it from the earlier manifests.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
