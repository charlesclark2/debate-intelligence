# Session report: v1-e30-t31-openev-camp-word-on-the-manifest-row

| | |
|---|---|
| Task | `v1-e30-t31-openev-camp-word-on-the-manifest-row` — The pull keeps OpenEv's own camp word on a camp file's manifest row |
| Spec | [`plan_specs/v1/e30-caselist-ingestion/t31-openev-camp-word-on-the-manifest-row.yaml`](../../plan_specs/v1/e30-caselist-ingestion/t31-openev-camp-word-on-the-manifest-row.yaml) |
| Epic / release | `v1-e30-caselist-ingestion` / `v1.1` |
| Branch | `task/v1-e30-t31-openev-camp-word-on-the-manifest-row` |
| Session status | COMPLETE |

## Summary

The pull now keeps OpenEv's own camp word on each manifest row it writes for a camp file. The new
field is `openev_camp_word`, beside `openev_id`. It is taken from the listing's `OpenEvFile.camp`
and kept only when it is one address word. The check reuses v1-e39-t28's
`OPENEV_CAMP_WORD_PATTERN`, matched whole, and also refuses `UNKNOWN`. Any other word, and a hand
import, gives `null`. Rows written before this task have no key and still read.

The field is an additive key, which is how v1-e30-t14 added `openev_id`. No reader of a
release-manifest row in either earlier build validates it against a model. So `schema_version`
stays 1 and no companion file is needed. Offline stamped builds of `v1.1.0-dev.251` (the cloud
image) and `v1.1.0-dev.200` (the Mac's) each ran t14's check over rows this branch wrote. Each
merged into them, re-derived them, removed a file from them and published them. Each kept the rows
byte for byte.

The deployed search function is not affected: it reads no release manifest.

The counts:
* The recorded listing (`openev.json`) has a one-word `camp` on both of its rows.
* No record of the Mac's sync keeps a listing camp.
* None of the Mac's 108 manifest rows carries `openev_id`. The cloud store needs a bucket read: an
  optional operator command is below.

Worth looking at first: the cross-build output, and decision 2 (`UNKNOWN` refused).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `openev-camp-word-on-the-manifest-row` (Camp word on the row) | Done | Counts first, then tests red, the code, the stored this-build manifest rewritten by this build's pull, the cross-build check, 17 mutants, `docs/data` |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1**: a file the pull imports has the listing's camp word on its manifest row, a word that is not one address word is not stored, rows written before carry none and still read, by tests shown failing first | PASS | **Red**, at `cbabd6e` (tests only, source unchanged): `hard_stop.py 115 … pytest test_camp_rows_carry_the_openev_camp_word.py test_camp_manifest_is_read_by_every_build.py test_openev_import.py -n 4` → **9 failed, 41 passed**. Every failure was an assertion about the missing word or key, for example `assert (900, None, 17) == (900, 'Juniper', 17)` and `assert None == 'Tamarack'`. **Green**, same command after the code → `50 passed in 4.82s`. The re-derive test was added after the code. Its red is mutants 1a, 1b and 8 below |
| Node: `uv run pytest packages/debate_core/tests -k openev` | PASS | At `ee4355f`, after the sync: `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests -k openev -q` → `241 passed in 36.98s`. Before the sync it was `187 passed in 67.41s`; the sync brought t32's tests |
| The PM's cross-build check (`v1.1.0-dev.251`, `v1.1.0-dev.200`) | PASS | Output under "The cross-build check" |

**Before the report** (working agreement 10), at `ee4355f`:

| Check | Result |
|---|---|
| `uv run scripts/affected_tests.py` | `348 of 637 test files (54.6%) chosen in 17.8 s from 15 changed files`. Most of it is reached through `caselist_sync.py`. That is well past two minutes, so the run is left to the pull request's `ci` check (agreement 10) |
| The test directory of what changed: `pytest packages/debate_core/tests/application/caselist -n auto` | `1848 passed in 84.50s` |
| The pull, the client and the smoke checks: `test_caselist_sync.py`, `tests/integrations/opencaselist`, `tests/smoke/test_caselist_camp_identity_smoke.py`, `tests/smoke/test_caselist_pull.py`, `test_caselist_reimport_openev_metadata.py`, `test_search_index_build.py` | `410 passed in 44.10s` |
| The always-run list: `tests/architecture`, `tests/specs`, `test_app.py`, `test_help_rendering.py`, `test_container_factories.py` | First run: `1 failed, 373 passed`. `test_single_interpreter_source` refused a `python3.12` path in the stored-manifests README. The README now names no version (`ee4355f`). Rerun: `374 passed in 18.27s` |
| `ruff format --check .` / `ruff check .` | `1759 files already formatted` / `All checks passed!` |
| `pyright packages/debate_core` | `0 errors, 0 warnings, 0 informations` |
| `lint-imports` | `Contracts: 20 kept, 0 broken.` |
| `uv run scripts/validate_specs.py` | `OK: 558 files, 41 epics, 495 tasks, 22 releases` |
| `docs_index.py --check-descriptions`, `check_links.py`, `check_command_blocks.py`, `check_thin_handlers.py` | All OK: 62 documents described, 3279 links, no `#` in shell blocks, 70 handlers within 25 statements |

## Counts first

All counts are read-only and are counts only. No value was printed. The script is
`<scratchpad>/count_camp_words.py`, run with `python3 -I` against `~/.debate-research/dev`, and it
took 0.05 s.

| What | Count |
|---|---|
| Recorded listings in the repository's fixtures | One, `packages/debate_core/tests/fixtures/opencaselist/openev.json`: 2 rows. `camp` holds one address word on both rows, and it is also the path's folder (`/openev/2026/<camp>/…`). No other fixture records a `GET /openev` body. The pull's tests build `OpenEvFile`s in code, with no `camp` |
| A listing camp kept in the Mac's sync records | **None.** Checked: `caselist-sync-runs.jsonl` (16 records), `caselist-sync-run-details.jsonl` (3), `caselist-sync-openev-deliveries.json`, `caselist-sync-download-starts.json` and the 17 files of `caselist-sync-runs/`. The only key containing "camp" is `inbox_retention.camp_downloads_would_remove_once_imported` (3), a count. This agrees with v1-e39-t28's count |
| Manifest rows carrying `openev_id` today, on the Mac | `2026-policy`: 106 member rows, `2026-ld`: 2. **0 of 108** carry an `openev_id` key and 0 carry a path digest, since all were written before v1-e30-t14 |
| … in the cloud run's store | **NOT RUN.** It is a read of the dev bucket, so it is the operator's. An optional command is under Operator follow-ups |

So no camp word can be recovered for any row written so far. Every row the pull writes from now on
carries one when the listing gives an address word.

## What was built

* `openev_manifest.py`:
  * `CAMP_FIELDS` gains `openev_camp_word`.
  * `OpenEvUpstream` gains `camp`, the listing's camp as given.
  * `upstream_fields` writes the key on every row: `openev_camp_word(upstream.camp)` from the pull,
    `null` from a hand import.
  * `openev_camp_word()` keeps a string only when `OPENEV_CAMP_WORD_PATTERN` (from
    `debate_core.domain.search_source_links`, compiled as `camp_metadata` compiles it) fullmatches
    it and it is not `UNKNOWN_CAMP`.
  * The module docstring documents the field.
* `caselist_sync.py`: `_import_openev` passes `selection.file.camp`. That is a one-argument change in
  a hub module, which is why the affected set is large.
* The re-derive, removal, publish and status needed no change. They hold rows as mappings and keep
  unknown keys. The new re-derive test and mutant 8 pin that.

## The cross-build check

**Whether manifest rows refuse extras.** They don't, in either earlier build. I listed every reader
of a release-manifest row in `v1.1.0-dev.251`'s source, then `v1.1.0-dev.200`'s:

* `read_recorded_release`, the merge;
* the re-derive;
* the removal plan and its rewrite;
* `sources_in_manifest` and `stored_rows_in_manifest`;
* the pull's already-imported read;
* `parse_sources`;
* the removal sweep.

Each reads a row as a `dict`. Neither build has a model of a manifest row. The `*Manifest*` models
there are the index's (`SearchIndexManifest`), the sidecar's (`FileProvenanceManifest`), the card
manifest's and a removal-log record. None of them holds rows. So t14's mechanism applies: one
additive key on the row, and `schema_version` stays 1.

**How the earlier builds were built.** This is t07's recipe, scripted in
`<scratchpad>/build_earlier.sh`. Each tag took under 3 s:

1. `git archive <tag>` into the scratchpad.
2. `scripts/stamp_build.py stamp --version 1.1.0.devN --tag <tag> --channel dev --commit <sha>`.
3. `uv build --offline --package debate-core --wheel`.
4. `uv venv --offline`, then `uv pip install --offline --no-deps` of the wheel.
5. A plain-path `.pth` to the worktree venv's site-packages, for third-party dependencies only.

`debate_core` then resolved under each venv's site-packages, with no `packages/` path on
`sys.path`. Neither build's `debate_core` contains `openev_camp_word`, and both contain
`upstream_path_sha256` (3 files each). The tags are `a21bb68` for `v1.1.0-dev.251` and `761b571`
for `v1.1.0-dev.200`.

**t14's check, under each earlier build's own code.** The check is
`check_an_older_build_reads_this_builds_camp_manifests.py`. It now measures which of the added keys
the reader's own rows lack, instead of assuming t14's two. The command:

```bash
CHECK_AN_OLDER_BUILD_READS=this-builds-camp-manifests "${VENV}/bin/python" -m pytest packages/debate_core/tests/application/caselist/check_an_older_build_reads_this_builds_camp_manifests.py -p no:cacheprovider -p no:randomly --no-cov -n 0 -q
```

The run at `ee4355f` printed the following under `v1.1.0-dev.251`. `v1.1.0-dev.200` printed the same
lines apart from its path. Both runs ended `2 passed`, in 1.57 s and 1.35 s.

```text
reader: the debate_core source at <scratchpad>/earlier/v1.1.0-dev.251/venv/lib/python3.12/site-packages/debate_core
placed: this build's manifest; the keys this source's rows lack: openev_camp_word; its rows are this source's own but for them: True
publish: succeeded True; status in sync: True
next pull: openev-640 already_imported, openev-700 already_imported, openev-900 download
its merge: this build's rows kept byte for byte (16 row(s)); the new row True, with the keys False
metadata re-import: this build's rows kept the keys as written: True; the same as its re-derive of its own manifest but for the keys: True
removal of 512: completed True; later upload(s) openev-640; rows it kept kept byte for byte (15 row(s)); 512 and 640 gone True
publish again: succeeded True; status in sync: True

reader: the debate_core source at <scratchpad>/earlier/v1.1.0-dev.251/venv/lib/python3.12/site-packages/debate_core
placed, in both places: suppression-list.jsonl, withdrawals.jsonl
list read: 1 whole file(s) and 1 disclosure(s)
next pull: openev-640 already_imported, openev-700 already_imported
the same removal: COMPLETED; removed 2 file(s), withdrew 0
publish: succeeded True; status in sync: True
status with the residue check: completed; in sync True
the withdrawal record read by this source's own model: 1 line(s)
the withdrawal record afterwards: this build's line kept True
```

"With the keys False" means the earlier build writes its own new row without the word, as expected.

**Two readers the check does not reach**, probed with `<scratchpad>/probe_index_and_parse_readers.py`:

| Reader | `v1.1.0-dev.251` | `v1.1.0-dev.200` | This build |
|---|---|---|---|
| The parse source list (`enumerate_sources`): this build's rows against the same rows without the word | 12 sources, the same: True | the same | the same |
| The index build's id join (`openev_ids_by_source`, v1-e39-t16) | Not in this build: its index build reads no release manifest | Not in this build | 4 ids, the same: True |

**Mutant 4 run through the check, t07's way.** For the form 4b below, I planted the mutant, rewrote
the stored this-build file with this build's pull, restored the source (`cmp` equal), and ran the
earlier builds' own merge reader on the planted file:

```text
v1.1.0-dev.251 its merge reader: UnreadableManifest: manifests/openev/2026-policy.jsonl line 1 is not a usable manifest row: schema_version is not 1
v1.1.0-dev.200 its merge reader: UnreadableManifest: manifests/openev/2026-policy.jsonl line 1 is not a usable manifest row: schema_version is not 1
```

The full check under `v1.1.0-dev.251` failed too: its next pull did not succeed. With the source
restored, the in-repo every-build test caught it 3 times, including
`test_the_stored_file_is_what_this_builds_pull_writes_now`. The stored file was then restored with
`git checkout HEAD --`, and the tree was clean.

## The deployed search function

It is not affected. Its role (`infrastructure/modules/evidence_search/main.tf:182`, and the
docstring of `packages/debate_api/src/debate_api/container.py`) grants `s3:GetObject` on four
things:

* `reports/tub/search/` (the index and its manifest, `SearchIndexManifest`);
* `manifests/_suppression/suppression-list.jsonl`;
* current objects under `raw/`;
* `reports/landscape/`.

It grants nothing else under `manifests/`, and `debate_api` imports no release-manifest reader. The
index it reads has no camp-word column: nothing joins the word yet. The index build that does read
these rows (v1-e39-t16's id join) reads them as mappings, and its ids were the same with and without
the word.

## Mutation run

* **The driver** is `<scratchpad>/mutants.py`. It refuses a dirty tree and a target that does not
  occur exactly once. It restores the saved bytes, clears that module's `__pycache__` and checks
  `git status --porcelain` is empty after each mutant.
* **Each run** is 6 files, 82 tests: this task's module, t14's every-build module,
  `test_openev_import.py`, `test_camp_rows_carry_upstream_identity.py`,
  `test_openev_metadata_reimport.py` and `test_openev_ids_by_source.py`. Each ran with
  `-n 4 --no-cov -p no:randomly`, under `hard_stop.py 115`, with a new `HYPOTHESIS_STORAGE_DIRECTORY`
  from `mkdtemp`, checked empty.
* **Hypothesis.** None of these files uses Hypothesis, so the fresh database follows agreement 8 and
  `--hypothesis-show-statistics` does not apply.
* **Timing.** Baseline `82 passed in 8.03s`. Mutant runs took 4 to 10 s of pytest time.
* **What counts as a catch.** Every catch below is an assertion failure. None is a collection error
  or a crash in a test.

| # | Mutant | Result | Caught by (this task's tests first) |
|---|---|---|---|
| 1a | **The word not stored** (the row writer writes `null`) | CAUGHT, 8 failed | `test_each_row_the_pull_writes_carries_the_listings_camp_word…`, `…kept_beside_the_canonical_camp…`, the two older-rows tests, the re-derive test, `test_the_stored_file_is_what_this_builds_pull_writes_now`, both `test_this_builds_pull_reads_it…` |
| 1b | The word not stored (the pull passes `camp=None`) | CAUGHT, 8 failed | The same 8 |
| 2a | **A word with a space stored** (no check at all) | CAUGHT, 4 failed | `test_each_row…` (`'Brightwater/Juniors'` and the rest stored), the two older-rows tests, the re-derive test |
| 2b | A word with a space stored (`match`, not `fullmatch`) | CAUGHT, 4 failed | The same 4 |
| 2c | A word with a space stored (a pattern with a space) | CAUGHT, 4 failed | The same 4 |
| 2d | `UNKNOWN` stored | CAUGHT, 4 failed | The same 4 |
| 2e | A trailing newline kept (`[A-Za-z0-9]+\n?`) | CAUGHT, 4 failed | The same 4 |
| 3 | **An older row fails to read** (the merge refuses a row without the key) | CAUGHT, 12 failed | Both older-rows tests, and both `test_this_builds_pull_reads_it…`, where the pull's run did not succeed. Also both `test_this_builds_re_derive…` and six `test_openev_ids_by_source.py` tests |
| 4 | **An earlier build refuses the new row** (`schema_version` 2 on the rows this import writes) | CAUGHT, 46 failed | This build refuses its own rows too, so this form proves little about earlier builds. Hence 4b |
| 4b | The same with this build's reader accepting 2: a version bump for the field | CAUGHT | Through the cross-build check above: both earlier builds refuse it, `schema_version is not 1`. In-repo: 3 every-build tests with the source restored |
| 5a | **The canonical camp stored instead of the listing's word** (checked) | CAUGHT, 8 failed | The same 8 as 1a. The canonical `UNKNOWN` is refused, so `Tamarack` and `QDI7` go missing |
| 5b | The canonical camp, unchecked | CAUGHT, 8 failed | The same 8. `'UNKNOWN'` stored |
| 6 | The lab passed as the word | CAUGHT, 8 failed | The same 8 |
| 7 | A hand import's row without the key | CAUGHT, 2 failed | `test_every_row_has_the_caselist_row_layout_plus_the_camp_fields`, `test_the_stored_file…` |
| 8 | The re-derive drops the word | CAUGHT, 4 failed | `test_a_re_derive_of_the_release_keeps_each_rows_word…`, plus three re-import byte-for-byte tests |
| 9 | The re-derive gives an older row the key | CAUGHT, 2 failed | Both `test_this_builds_re_derive…`: "no delivery record knows a camp word" |
| 10 | The merge rewrites an unchanged row | CAUGHT, 3 failed | Existing re-import no-op tests only, not this task's: an unchanged path is not in this import, so no test of mine reaches it |

## Files changed

* **`packages/debate_core/src/debate_core/application/`:**
  * `caselist/openev_manifest.py`: the field, `OpenEvUpstream.camp`, `openev_camp_word()`, the
    docstring.
  * `caselist_sync.py`: passes the listing's camp.
* **`packages/debate_core/tests/fixtures/opencaselist/`:**
  * `openev_camp_words.json` (new): a recorded `GET /v1/openev` listing of 11 invented camp files,
    one per form the camp can take.
  * `README.md`: its row.
* **`packages/debate_core/tests/application/caselist/`:**
  * `test_camp_rows_carry_the_openev_camp_word.py` (new, 7 tests).
  * `test_camp_manifest_is_read_by_every_build.py`: the camp word is a third added key; the pulled
    rows' words are written by hand; the next pull's new row carries `Juniper`; the re-derive gives
    older rows none.
  * `test_openev_import.py`: the camp fields include the key, and it is `null` on a hand import.
  * `camp_manifest_scenario.py`: the history's listings carry their paths' camp folders as words.
  * `check_an_older_build_reads_this_builds_camp_manifests.py`: measures the keys a reader lacks;
    names an installed reader by its path.
  * `stored_camp_manifests/written_by_this_build/2026-policy.jsonl`: rewritten by this build's
    pull. The 16 member rows gain the key; the other bytes are unchanged and the suppression
    records are unchanged.
  * `stored_camp_manifests/README.md`: the t31 run and its output.
* **`docs/data/`:**
  * `openev-release-manifest.md` (new): the camp fields of a member row, and the new one in detail.
  * `search-index.md`: one sentence, beside t32's, saying the row now keeps the listing's word and
    the index does not read it yet.
* **`plan_specs/…/t31-….yaml`:** phase `Succeeded`.

## Deviations from the spec

1. **The count of manifest rows carrying `openev_id` covers the Mac only.** The cloud run's store
   would be a bucket read. Under the standing rule that every call on the operator's profiles is
   handed off, that is an operator command, given below. It is not an acceptance criterion.
2. **`docs/data/search-index.md` gained one sentence.** It is inside `docs/data`, which the spec
   lists, and points from the camp-link section to the new field. After the sync it sits after
   t32's sentence on the same line, where the rebase stopped on a conflict.

## Decisions and assumptions

1. **The key is `openev_camp_word`.** It is OpenEv's word, as against the canonical `camp` beside it,
   and it names what v1-e39-t28's table calls an "OpenEv word".
2. **`UNKNOWN` is refused as well as anything that is not one address word.** Both existing checks
   of an OpenEv word refuse it: the loader of the `openev` table and `openev_camp_page_url`. Storing
   it would hand a later reader that prefers the row's word a word the link refuses, instead of
   `null` and the table's fallback. Mutant 2d pins it. If the PM would rather the row record exactly
   what OpenEv lists, this is one `or camp == UNKNOWN_CAMP` to remove.
3. **Every row this build writes carries the key, `null` when no word is kept.** That includes a
   hand import's rows. The rows then have one shape, as t14's two keys do. Rows written before carry
   none, and an absent key reads as no word.
4. **Nothing re-derives a word.** `caselist reimport-openev-metadata` keeps the key as written, and
   gives older rows no key (mutants 8 and 9). The delivery record does not keep the word, so there
   is nothing to derive it from.
5. **A zip release's member rows all carry the zip's word**, as they carry its `openev_id`.
6. **The word is checked where the row is written,** not where the listing is parsed.
   `OpenEvFile.camp` still holds what the API sent; the client test pins that the recorded words
   arrive untouched.
7. **The pattern is reused, not copied.** `OPENEV_CAMP_WORD_PATTERN` is imported from the domain
   module and compiled, as `camp_metadata` does. The domain is not in this task's packages, so I
   did not add a shared function there.
8. **t14's scenario listings now carry camp words.** Builds before this task read `OpenEvFile.camp`
   and store it nowhere, so their stored files did not change. This build's stored file was
   rewritten by its own pull, which the README requires.
9. **The new listing's file 7105 is named `Lighthouse Elections DA.docx`, not `… Politics DA.docx`.**
   The first red run showed the pull taking a listed file as `already_imported` when its file name
   equals a hand-imported row's in another folder (`_match_listed_openev`). That is existing
   behaviour, not this task's, so I gave the fixture a name of its own.

## Operator follow-ups

Optional, read-only, about 10 s. It counts the dev bucket's camp release manifests: how many member
rows carry an `openev_id`, and how many carry the camp word key (0 expected until a build with this
field pulls). It reads the bucket name from the main checkout's initialised `infrastructure/envs/dev`
and prints counts only. Each line names a release manifest and three counts. The member-row count
must be above zero, or the listing found no manifests. Paste the lines back.

**Operator command** (expected runtime ~10 s)
Where: your Mac, in the task worktree

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e30-t31-openev-camp-word-on-the-manifest-row
BUCKET=$(AWS_PROFILE=debate-admin terraform -chdir=/Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence/infrastructure/envs/dev output -raw evidence_bucket_name)
for NAME in $(aws s3 ls "s3://${BUCKET}/manifests/openev/" --profile debate-dev-evidence | awk '{print $4}'); do aws s3 cp "s3://${BUCKET}/manifests/openev/${NAME}" - --profile debate-dev-evidence | python3 -I -c 'import json, sys; m = [r for r in map(json.loads, filter(str.strip, sys.stdin)) if r.get("kind") == "member"]; print(sys.argv[1] + ":", len(m), "member rows,", sum(isinstance(r.get("openev_id"), int) and not isinstance(r.get("openev_id"), bool) for r in m), "with an openev_id,", sum("openev_camp_word" in r for r in m), "with the camp word key")' "${NAME}"; done
```

## Follow-up work

1. **Join the word into the index and prefer it to the table** (the later task the spec names, as
   v1-e39-t16 joins `openev_id`). `openev_ids_by_source` is the model: by `sha256` from stored rows,
   with a deterministic choice when one file has two words.
2. **A listed file whose name equals a hand-imported row's in another folder is never fetched**
   (decision 9). It is decided `already_imported` by `_match_listed_openev`. That may be intended:
   it is how a hand-imported file is not downloaded again. But it also keeps a different camp's file
   of the same name out, together with its camp word. For E34 (the sync), if the PM thinks it worth
   a look.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-01

**Notes:**

The exact source of OpenEv's camp word is now kept for every file the pull imports, with both
builds in use proven unaffected.
1. **ac1 passes.**
   * Red: 9 failed, all assertions on the missing word or key.
   * Green: 50, and the node criterion passes (241 after the sync).
   * All 17 mutants are caught: the PM's five, with 1, 2, 4 and 5 in several forms, plus 6 to 10.
     4b was rightly taken through the earlier builds' own readers, since 4 alone proves nothing
     about them. 10 is caught only by existing tests, and the report says so.
2. **The PM's cross-build requirement is met.** Every reader of a manifest row in both earlier builds
   was listed, and each reads a `dict`, so t14's additive-key mechanism applies and `schema_version`
   stays 1. t14's check under each earlier build's own code keeps this build's rows byte for byte
   through merge, re-derive, removal and publish. The parse and index readers were probed too.
3. **The search function:** unaffected, confirmed from its role's grants and its imports.
4. **Deviations accepted:**
   * **1:** the cloud count is the operator's and optional. The PM doesn't need it, since 0 rows
     carry the key until a build with it pulls.
   * **2:** the sentence in search-index.md.
5. **Decisions accepted:**
   * the name `openev_camp_word`;
   * `UNKNOWN` refused, agreeing with the table's loader and the link;
   * the key on every new row, `null` when no word is kept;
   * no re-derive of a word;
   * a zip's members carrying its word;
   * the check where the row is written;
   * the pattern reused, not copied;
   * t14's scenario listings given words;
   * the fixture renamed around decision 9.
6. **Follow-ups, the PM's rulings:**
   * **Joining the word into the index and preferring it to the table:** one p3 E39 task in the
     PM's next batch, modelled on `openev_ids_by_source`.
   * **A listed file sharing a hand-imported file's name in another folder is never fetched:** one
     p3 E34 task in the next batch, counting first how many listed files are taken as
     `already_imported` by name alone and from another camp.
7. **Closing checks:** the affected set (348 files through `caselist_sync.py`) is left to the PR's
   `ci` under agreement 10. Core caselist (1,848), the pull, client and smoke checks (410), the
   always-run list (374, after the README fix), ruff, pyright, lint-imports, the doc checks and the
   specs are clean.
8. **Merge:** a plain `scripts/task pr` once `ci` is green. No operator step follows. The word starts
   appearing with the first image that carries this task.
