# Session report: v1-e30-t32-michigan-split-into-openevs-three-camps

| | |
|---|---|
| Task | `v1-e30-t32-michigan-split-into-openevs-three-camps` — Michigan's three camps are filed apart, as OpenEv files them, so their cards can link |
| Spec | [`plan_specs/v1/e30-caselist-ingestion/t32-michigan-split-into-openevs-three-camps.yaml`](../../plan_specs/v1/e30-caselist-ingestion/t32-michigan-split-into-openevs-three-camps.yaml) |
| Epic / release | `v1-e30-caselist-ingestion` / `v1.1` |
| Branch | `task/v1-e30-t32-michigan-split-into-openevs-three-camps` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The count came first (ac1). 40 of the Mac's 102 stored `2026-policy` camp files are `Michigan`. 5 name
`Michigan Classic`, 1 names `MNDI`, and 34 name only a bare `Michigan`. None names `Michigan7`,
`Michigan 7`, the long MNDI name, `UM7` or `UMC`. `camp_aliases.yaml` now files `Michigan7`,
`Michigan Classic` and `MNDI` as three camps, with OpenEv's words `UM7`, `UMC` and `MNDI`. A bare
`Michigan` stays `Michigan` with no word, because nothing in the 34 names tells the three camps apart.
Re-deriving the Mac's release with the new table moves 6 files, so 6 of the 40 can link. No spelling
swallows another: the matcher already tried the longest spelling first at each word, and new tests pin
that on an invented family of camps. The refile is the existing `caselist reimport-openev-metadata`.
It reads no file and needs no parser or fingerprint version bump. Tests were shown failing first (31
assertions), and all 6 of the PM's mutants (7 variants) and one more were caught.

**The PM should look at one thing first:** the Goal stays **InProgress**. ac2's "existing files are
refiled" holds on a data directory, but it cannot reach dev's real records. Since the cutover those
records are the cloud run's run-state bundle. Only a pull, a backfile import and a removal save that
bundle, and the metadata re-import is none of them
([Deviations](#deviations-from-the-spec), [the PM question](#questions-for-the-pm)).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `michigan-split-into-openevs-three-camps` (Michigan split) | Done in the repository; dev's refile open | Count, table split, tests red then green, mutants, the route for each place the camp is kept, docs. Synced onto `origin/dev` at `a971550`, which includes v1-e33-t07 |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1, "Counts first: the stored Michigan camp files, by the spelling each names, recorded before any rule" | PASS | [The count](#the-count-first), taken before any test or table edit (the first commit after the start is `cb9b626`, the tests). Two read-only scripts, 0.05 s and 0.32 s |
| ac2, "The table files Michigan7, Michigan Classic and MNDI as three camps with their OpenEv words, a bare Michigan as the count rules, and no spelling swallowing another; existing files are refiled without a download; by tests shown failing first" | PASS for the table, the matching, the refile mechanism and red-first. **NOT RUN for dev's own records** | Table: `a3508a6`. Red: [30 + 1 failed, every one an assertion](#red-first). Green: [below](#tests-run). Refile: `test_refiling_*` and `test_reimport_command_with_the_packaged_table_files_michigans_three_camps_apart` re-derive a release stored under the merged table, through a blob store that refuses to read or fetch bytes. On the Mac's manifest, read-only: 40 Michigan become 34 / 5 / 1. **Not run:** the refile of dev's 40 files. No command today writes a re-derive into the cloud run's run-state bundle, so this needs the PM's ruling on a route ([question 1](#questions-for-the-pm)) and then an operator run |
| Node: "Michigan split tests pass" (`uv run pytest packages/debate_core/tests -k camp`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -n auto -q --tb=short packages/debate_core/tests -k camp` → `521 passed in 44.32s` |

## The count first

Taken 2026-11-01 on the operator's Mac, read-only, counts only, before any rule. SQLite was opened with
`mode=ro`. Its `-shm` file's mtime moves on any open, and the database file itself is not written. The
manifests were read as text, and their SHA-256 was checked unchanged after the re-derive. No school,
student, lab, title or path was printed: only camp names (public), spelling classes and counts. The
sources were `~/.debate-research/dev/debate.sqlite3` (`caselist_camp_files`) and
`objects/manifests/openev/*.jsonl` (each member row's `path`, joined by `sha256`).

| Question | Count |
|---|---|
| Stored camp files | 104 (`caselist_camp_files`): 102 `2026-policy`, 2 `2026-ld` |
| Of them `Michigan` | **40**, all year 2026, event `POLICY` |
| Manifest paths per Michigan file | 1 each (40 of 40). No path has a camp folder (no folder names any Michigan spelling) |
| Spelling each Michigan file's name gives, by whole words | `Michigan Classic`: **5**. `MNDI`: **1**. A bare `Michigan` and nothing else: **34**. `Michigan7`, `Michigan 7`, `Michigan National Debate Institute`, `UM7`, `UMC`: **0** each. No file names two of these |
| What follows the camp's words | All 40 are in the release's `<title> - <camp> <year> <initials>` shape: the camp words then a year end the name, with 1-4 capital initials after it in 36 (30 of the 34 bare) and none in 4 (all bare). No name has a bracket |
| Any other stored file naming a Michigan spelling, `UM7` or `UMC` | 0, in the stored files and in all 108 member rows of both manifests |
| Re-derived with this task's table (`rederive_release`, pure, on the manifest's lines) | `2026-policy`: 105 rows, **6 change camp**, 0 titles, 0 warnings. Camps after: `Michigan` 34, `Michigan Classic` 5, `MNDI` 1, every other camp as before. With the start commit's table: 0 rows change |

**What the count rules for a bare Michigan.** Nothing in the 34 names separates the three camps. Each is
`<title> - Michigan <year> [<initials>]`, the same shape the 5 Classic and the 1 MNDI files use with
their own spelling. The spec's default stands: a bare `Michigan` stays `Michigan`, with no word and no
link. One reading suggests otherwise. The same release spells out `Michigan Classic` and `MNDI` where it
means those camps, and OpenEv's own label for UM7 is just "Michigan". That is an inference about how one
person named files, not something the store shows, so it is not the rule here
([question 2](#questions-for-the-pm)).

**The Mac's store, not the cloud's.** These are the Mac's records, as the PM asked. Since the cutover
the cloud run may have pulled more OpenEv files into dev's records. The count's question needs only the
Michigan files already filed, and the Mac's 104 match v1-e39-t28's count of 2026-10-31.

## The table

`packages/debate_core/src/debate_core/application/caselist/camp_aliases.yaml`:

| Canonical camp | Spellings (besides itself) | OpenEv word |
|---|---|---|
| `Michigan7` | `Michigan 7`, `UM7` | `UM7` |
| `Michigan Classic` | `UMC` (OpenEv's label "Michigan (Classic)" has the same words) | `UMC` |
| `MNDI` | `Michigan National Debate Institute`, `Michigan MNDI` (OpenEv's label "Michigan (MNDI)") | `MNDI` |
| `Michigan` | none | none |

**Why these canonical names.** The canonical name is what a camp card's link label shows ("Find on
OpenEv: Michigan Classic 2026 camp page"), and its provenance line too. So each name is the spelling the
camp's own files use: `Michigan Classic` and `MNDI` are the stored files' own words. `Michigan7` was the
table's existing spelling and reads clearly beside a year ("Michigan7 2026", where "Michigan 7 2026"
runs two numbers together). None of them is a bare `Michigan`, which by itself names none of the three.
OpenEv's words and labels are spellings too, so a file under an OpenEv camp folder (`2026/UM7/…`) or
named with OpenEv's label reads.

**How the loader orders or refuses overlapping spellings.** It refuses only a spelling, or an OpenEv
word, given to two camps (unchanged). Overlap is allowed and settled by the matcher. At each word of a
file name it tries the longest spelling first, so `Michigan Classic 2026`, `Michigan7` and `Michigan 7`
never fall to the bare `Michigan` camp, whatever order the table lists them in. A folder must be a
spelling as a whole. A name with a bare `Michigan` in its title and `Michigan Classic` at the camp's
place names two camps, so it is `UNKNOWN` with a warning, never a guess. No stored file has that shape.
The new tests pin each case on an invented family (`Ridgeline`, `Ridgeline7`, `Ridgeline Classic`,
`RNDI`), with the table listed in both orders. The table's and the module's comments say so, and the
`openev:` comment no longer says Michigan has no word.

## Where else the camp is kept, and how each learns the new one

None needs a parser or fingerprint version bump. The camp is in no fingerprint and in no parse's skip
key (`skip_key(sha256, parser_version, profile_version)`), so no file is parsed again for it.

| Where | How it learns | Shown by |
|---|---|---|
| `caselist_camp_files` and the release manifest's rows | **A metadata re-import:** `caselist reimport-openev-metadata --year 2026 --event policy`. It reads the recorded paths, asks the blob store only whether each digest is held, and reads, fetches and writes no bytes | `test_refiling_*` (four tests, through `AnswersOnlyWhetherHeld`) and `test_reimport_command_with_the_packaged_table_files_michigans_three_camps_apart` (the command with the packaged table; the blob tree is byte-identical) |
| The parsed occurrence rows' `camp` | **The next parse:** any `caselist parse --caselist openev`, even with nothing to parse. Every run rebuilds the occurrence rows, taking each camp from the manifest row (`parse_sources._stored_rows`) | `test_a_camp_refiled_in_its_manifest_reaches_the_occurrence_rows_at_the_next_run_unparsed`: 0 sources to parse, the parser never called, both rows carry the new camp |
| The search index's `camp` column | **A rebuild:** the next index build. It takes an occurrence's camp from the row (`row.camp or camp_file.camp`), and the rebuilt rows change the store's digest that the index stage compares | Read in `search_index_build.py`, not tested here |
| A built file's sidecar | **A rebuild of the file:** a file built after the occurrence rebuild. One built before keeps its camp | Read in `docx_file_writer/writer.py` (`occurrence.camp or camp_file.camp`), not tested here |
| (and) the per-source parsed documents | They keep the parse-time camp in each card's provenance until a `caselist parse --reparse`. Nothing that shows a camp card's camp reads them | Read, not tested |

**v1-e33-t07**, merged as `a971550` and synced in, adds camp path digests to camp occurrence rows. They
are digests of each camp file's path, which a refile does not change, so they are unaffected. My tests
pass on top of it.

## Red first

At `cb9b626` the new and updated tests were run against the unchanged table:
`.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -p no:randomly -n 0 -q --tb=line`
over the new module, `test_camp_openev_words.py` and `test_camp_names_in_openev_files.py` →
**30 failed, 90 passed**, all 30 `AssertionError`. 27 of them are in the new module. Its 26 passes are
the invented-family matcher tests and invariants, which the old code already keeps and which mutant 2
targets. The other 3 are the two updated pins. The command test, `dd796fc`, was run with the start
commit's table put back → **1 failed** (`assert {'Michigan': 4} == {…}`), then the table was restored
from `HEAD`.

The occurrence-row test pins behaviour that already existed, so it passed when written. Its red is a
mutant: the occurrence camp taken from the parsed card's provenance instead of the manifest → 1 failed
(`['Ridgeline', 'Ridgeline'] == ['Ridgeline Classic', …]`).

## Mutants

Each was applied by exact replacement (a scratch script) and run with a new, empty
`HYPOTHESIS_STORAGE_DIRECTORY` (agreement 8; these tests use no Hypothesis). Each covered set was the new
module, `test_camp_openev_words.py`, `test_camp_metadata.py`, `test_camp_names_in_openev_files.py` and
the CLI's `test_caselist_reimport_openev_metadata.py` (191 tests), with `-n 0 -p no:randomly`. Each was
restored with `git checkout HEAD --`. Every failure was at an assertion or a `pytest.raises`; none
errored before running.

| Mutant | Caught | By |
|---|---|---|
| 1, the merged Michigan left as one camp (the start commit's table) | 31 failed | the packaged-spelling, file-shape, link and refile tests, and the updated pins |
| 2, `Michigan` swallowing `Michigan Classic` (the matcher tries the shortest spelling first) | 22 failed | `test_a_bare_spelling_never_swallows_a_longer_one_whatever_the_tables_order` (8, both orders), the packaged file shapes, the refile |
| 3a, a bare Michigan filed under UM7 (`Michigan` a spelling of `Michigan7`) | 14 failed | the packaged spellings, the shapes, the refile and the command test |
| 3b, a bare Michigan given the word (`Michigan: UM7` in place of `Michigan7: UM7`) | 4 failed | `test_the_three_camps_have_openevs_words_and_a_bare_michigan_has_none`, the link test, the packaged-words pin |
| 4, a refiled file downloaded (the re-import reads each blob's bytes instead of asking whether it is held) | 5 failed | the refile tests, each at `AssertionError: refiling read or fetched a file's bytes` |
| 5, two camps given one word (the loader's shared-word refusal disabled) | 2 failed | `DID NOT RAISE InvalidCampAliases`, in the new family test and the existing one |
| 6, a word not on OpenEv's list (`Michigan Classic: UMCL`) | 3 failed | the packaged-words pin (hand-written from the PM's list), the three-words test, the link test |
| The occurrence camp taken from the parsed document, not the manifest | 1 failed | the occurrence-row test |

## Tests run

| Command | Result |
|---|---|
| The touched files after the sync (new module, `test_camp_openev_words.py`, `test_camp_metadata.py`, `test_camp_names_in_openev_files.py`, the CLI re-import tests, `test_caselist_parse.py`, `test_openev_metadata_reimport.py`) | 259 passed in 6.61s |
| Within two minutes, `-n auto -m "not slow and not live"`: every test that loads the packaged table (`test_search_pages_find_on_openev.py`, `test_entities.py`, `test_search_source_links.py`, the re-import and republish tests), the changed files, `tests/docs`, the camp smoke tests, and the always-run list (`tests/architecture`, `tests/specs`, `test_app.py`, `test_help_rendering.py`, `test_container_factories.py`) | 993 passed in 27.84s |
| `packages/debate_core/tests/application/caselist` whole (the changed module's directory, 103 files) | 1833 passed in 73.80s |
| `uv run scripts/affected_tests.py` | **352 of 635 files** (55.4%), from 11 changed files. **Not run as a whole**: over the two-minute line (agreement 10), so it is left to the pull request's `ci`, which runs the same set. The table alone reaches 321 (`a3508a6`, measured with `--diff`), as it is a packaged resource the importer, the API and the index all load |
| `uv run --frozen ruff format --check .` / `ruff check .` | 1754 files already formatted / All checks passed |
| `uv run --frozen pyright packages/debate_core packages/debate_cli` | 0 errors, 0 warnings |
| `uv run --frozen lint-imports` / `check_thin_handlers.py` | 20 kept, 0 broken / 70 handlers within 25 statements |
| `check_command_blocks.py`, `check_links.py`, `docs_index.py --check-descriptions`, `pre-commit run check-merge-conflict` | all OK |
| `uv run scripts/validate_specs.py` | OK: 558 files, 41 epics, 495 tasks, 22 releases |

## Files changed

* `packages/debate_core/src/debate_core/application/caselist/camp_aliases.yaml`: the split, the four
  Michigan camps, three OpenEv words, the overlap rule and the reworded `openev:` comments.
* `packages/debate_core/src/debate_core/application/caselist/camp_metadata.py`: docstring only (the
  overlap rule; a bare name gets no word).
* `packages/debate_core/tests/application/caselist/test_camp_split_into_openevs_three_camps.py` (new),
  and the packaged pins in `test_camp_openev_words.py` and
  `packages/debate_core/tests/integrations/opencaselist/test_camp_names_in_openev_files.py`
  (`Michigan Classic` is its own camp now).
* `packages/debate_core/tests/application/test_caselist_parse.py`: the occurrence-row test.
* `packages/debate_cli/tests/test_caselist_reimport_openev_metadata.py`: the command test.
* `docs/data/search-index.md`: the Michigan count, the route table, the merged-camp bullet.
* `docs/runbooks/caselist-backfill.md`: what a re-derive with this table changes, and that it is not yet
  a dev step.

## Deviations from the spec

1. **"Refile the existing camp files" is done as a tested mechanism, not on dev's records.** The spec
   names the routes: a re-import of metadata, then the next parse and a rebuild. That holds for a data
   directory, and the tests prove it. But since the cutover dev's records live in the cloud run's
   run-state bundle (`manifests/_run-state/run-state.tar.gz`). Only `caselist pull`
   (`bucket_run.py`), `backfile-import` and `caselist remove` save it (`save_bundle()` callers). A
   re-import on the Mac changes only the Mac's stale copy, and the next of those three commands to run
   replaces that copy from the bundle. A Mac publish of the re-derived manifest would leave the bundle's
   database and manifest disagreeing with the bucket's. So I did not hand the operator a dev refile, and
   I did not build a bucket-mode re-import: that is scope the spec does not name. The runbook says to
   wait. ac2's dev part is **NOT RUN**, and the Goal stays **InProgress**.
2. **The operator-run count was run by the session** (read-only, under a second, files the operator
   already has; agreement 2).

## Decisions and assumptions

* **Canonical names** `Michigan7`, `Michigan Classic` and `MNDI`, for the label, as [above](#the-table).
* **OpenEv's words and labels added as spellings** (`UM7`, `UMC`, `Michigan MNDI`). There were no
  stored hits for any of them (counted), so no stored file moves because of them. They let a file under
  an OpenEv camp folder, or named with OpenEv's label, read. `Michigan (Classic)` already reads as
  `Michigan Classic`.
* **A bare Michigan beside a specific Michigan camp in one name is `UNKNOWN`**, by the existing
  two-camps rule, rather than a "family" rule giving it the specific camp. No stored name has that
  shape, so no such rule was added.
* **`Michigan: []`** rather than `Michigan:` (null) in the YAML, so the empty spelling list is plainly
  intended.
* **The refile test uses the real camp names** (public) with invented titles and initials. It imports
  under the pre-task table, copied by hand, and re-derives with the packaged one, so it tests the real
  transition. The overlap tests use an invented family, as v1-e39-t28's do.

## Questions for the PM

Paste-ready:

> **v1-e30-t32: two rulings, after the count.**
>
> **1. How dev's 40 Michigan files get refiled.** The table split is done and tested, and
> `caselist reimport-openev-metadata` refiles a data directory with no download. Dev's records are the
> cloud run's run-state bundle, which only a pull, a backfile import and a removal save. A re-import on
> the Mac reaches none of them. Options:
> (a) **A follow-up task: the re-import in bucket mode.** It takes the dev lock, restores the bundle,
> re-derives, publishes the release manifest and saves the bundle, as `caselist remove` does. Then come a
> dry run and a real run as two operator blocks, and the next cloud run's parse and index stages carry
> the camp to the cards.
> (b) **The weekly pull re-derives every OpenEv release with its build's table** before its parse stage,
> so any table change reaches dev at the next cloud run with no hand step. The cost: a camp can change in
> a run nobody asked to change it, and the change lands in `caselist_sync.py`, a hub module.
> (c) **Leave it** until another route rewrites the bundle. The 6 files stay unlinked.
> **Recommendation: (a).** It is one explicit, dry-runnable operator step that reuses the removal's
> pattern, and the next alias-table change needs it too. This task's Goal stays InProgress until the
> refile runs, or until you rule that it closes without it.
>
> **2. The 34 bare-Michigan files.** The count finds nothing in their names that tells MNDI, UM7 and UMC
> apart, so they stay `Michigan` with no link (the spec's default). One reading points to UM7: the same
> release writes `Michigan Classic` and `MNDI` where it means those camps, and OpenEv's own label for
> UM7 is just "Michigan". Options:
> (a) **Keep the default** (recommended).
> (b) The operator opens OpenEv's 2026 UM7 page signed in and checks, privately, whether the 34 titles
> are among its files, reporting only a count. If all 34 are, a one-line table change files a bare
> `Michigan` under `Michigan7`, in a task.
> **Recommendation: (a)**, unless the cards' links matter enough to spend the operator's check on (b).

## Operator follow-ups

None now. The dev refile waits for ruling 1.

## Follow-up work

* **The re-import in bucket mode**, if ruling 1 is (a): E30 or E40 (the run-state owner).
* **The `2026-ld` release's 2 rows would change their warnings** under any table, the start commit's
  included. That comes from a warning reworded since they were imported, not from this task. A re-import
  after ruling 1 would rewrite them too; worth knowing before reading that dry run.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
