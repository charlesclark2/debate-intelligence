# Session report: v1-e33-t09-style-profile-version-refusal

| | |
|---|---|
| Task | `v1-e33-t09-style-profile-version-refusal` — files build refuses a store written under another style profile, as it refuses another parser version |
| Spec | [`plan_specs/v1/e33-file-builder/t09-style-profile-version-refusal.yaml`](../../plan_specs/v1/e33-file-builder/t09-style-profile-version-refusal.yaml) |
| Epic / release | `v1-e33-file-builder` / `v1.2` |
| Branch | `task/v1-e33-t09-style-profile-version-refusal` |
| Session status | COMPLETE |

## Summary

`files build` now refuses, before it resolves any card, a caselist whose newest generation was read
through another style profile. It does this in the same `STORE_PARSED_BY_ANOTHER_VERSION` refusal
it already gave for another parser or fingerprint version, in the same code (`_store_refusal`). For
each caselist the refusal names every version that differs, gives both values of each, and names
the re-parse once. The store's profile is read from every row of the occurrence table, which is the
table the resolver reads, through a new port method `read_occurrence_profiles`. It reads each row's
JSON without the model, as `read_occurrence_stamps` already reads the fingerprint version. The
build's own profile comes from the parser the container already wires (`parser.profile_version`).
`files publish` does not meet this mismatch: its re-check reads no occurrence, so no refusal was
added there (below).

**Look first at Deviation 1.** The new port method needed one method each in the local adapter and
the in-memory fake, and neither is in `constraints.packages`.

## Counted first: how the store records its style profile, and how the build knows its own

Counted read-only, before any change.

* **The store, per generation.** Every record carries `profile_version` (`StoreRecord`,
  `application/ports/parsed_store.py`). That means each source entry (per-source file and
  `index.jsonl`), each document record, and each row of `occurrences.jsonl`. The directory name
  holds only the parser version and the generation (`<parser>_reparse-<n>`), never the profile.
  * A source entry carries the profile it was parsed through.
  * An occurrence row carries `plan.profile_version`, the profile of the run that last rebuilt the
    table (`caselist_parse.py`, the `OccurrenceRecord(...)` in the aggregate rebuild).
  * A generation holds one profile: `_choose_version` reuses the newest generation only when every
    entry's skip key `(sha256, parser, profile)` matches the run's. Otherwise it starts
    `_reparse-<n+1>`. So within a generation the entries and the occurrence rows agree.
* **The running build.** `DebateDocxParser().profile_version`, from the packaged
  `style_profiles/verbatim.yaml` (`load_style_profile()`), today `2026.09.20-verbatim-1`. The
  container's `_docx_parser()` is the parser `files build` already writes and checks with. Before
  this task `FileBuildService` was given only `parser_version`.
* **This machine's stores** (`~/.debate-research/dev/parsed`), read raw:

  | Caselist | Directory | Occurrence rows | Row profiles | Index entries | Entry profiles |
  |---|---|---|---|---|---|
  | hsld26 | `2026.10.20-docx-6` | 109,110 | all `2026.09.20-verbatim-1` | 6,122 | all `2026.09.20-verbatim-1` |
  | hspf26 | `2026.10.20-docx-6` | 73,632 | all `2026.09.20-verbatim-1` | 5,234 | all `2026.09.20-verbatim-1` |
  | hspolicy26 | `2026.10.20-docx-6` | 144,841 | all `2026.09.20-verbatim-1` | 3,869 | all `2026.09.20-verbatim-1` |
  | openev | `2026.10.20-docx-6` | 8,081 | all `2026.09.20-verbatim-1` | 104 | all `2026.09.20-verbatim-1` |
  | testcl26 | `2026.10.20-docx-6` | 0 | none | 0 | none |

  One generation per caselist and one profile everywhere, equal to the running build's, so no local
  store is refused by this change. Reading the raw stamps of the largest table (hspolicy26, 95 MB)
  took 0.36 s with `fingerprint_stamps_of_file`, which the profile read mirrors.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `style-profile-refusal` | Done | Red `d2c4735`, implementation `75eafa1` |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: a store written under another style profile is refused once, before any card is resolved, in the same refusal as a parser or fingerprint version, naming both profiles and the re-parse; tests shown failing first | PASS | `test_a_store_written_under_another_style_profile_is_refused_once_before_resolving`: generation 1 of this parser version under this build's profile, `_reparse-2` written by a `DebateDocxParser` reading through a profile versioned `2026.11.02-verbatim-2`. The refusal is `STORE_PARSED_BY_ANOTHER_VERSION`, both profiles are in the message and neither the parser nor the fingerprint version is, `caselist parse --caselist hspolicy26` appears exactly once in the hint, `read_occurrences` is never called, no event (unattributed or writer) fires, and nothing is written. One refusal for all three: `test_every_version_that_differs_is_named_with_both_values_in_one_refusal` (all six values in one message, one re-parse). CLI through the container and `LocalParsedStore`: `test_files_build_refuses_a_store_another_style_profile_made_naming_both_profiles`. Red first: see "Red run" |
| Node `style-profile-refusal`: `uv run pytest packages/debate_core/tests/application/test_file_build_service.py` | PASS | `26 passed in 18.29s` |

The refusal as a person reads it (from the synthetic world, printed by loading the test module):

> this machine's parsed store was not built by this build: hspolicy26's occurrence table was read
> through style profile 2026.11.02-verbatim-2, and this build's style profile is
> 2026.09.20-verbatim-1
>
> Re-parse with this build: `debate-research caselist parse --caselist hspolicy26`, then build again.

With all three different:

> this machine's parsed store was not built by this build: hspolicy26 was parsed by parser
> 2026.10.18-docx-4, and this build's parser is 2026.10.20-docx-6; hspolicy26's occurrence table is
> stamped card-fingerprint-v3, and this build's fingerprint version is card-fingerprint-v4;
> hspolicy26's occurrence table was read through style profile 2026.11.02-verbatim-2, and this
> build's style profile is 2026.09.20-verbatim-1

## Red run

The skeleton (`d2c4735`) adds the port method, its two implementations, and the `profile_version`
argument, which the service stores and does not use. The tests were run against it and committed
red:

* `.venv/bin/python -m pytest -p no:randomly -q --tb=line packages/debate_core/tests/application/test_file_build_service.py packages/debate_core/tests/application/caselist/test_occurrence_table_guard.py`
  → `3 failed, 48 passed`:
  * `…another_style_profile_is_refused_once_before_resolving`: `assert BUILT is REFUSED`. The store
    built: in the synthetic world the two profiles differ only in version, so the cards are where
    the rows say. A real profile change moves them, which is the `OCCURRENCE_MISMATCH` the follow-up
    describes.
  * `…a_table_holding_rows_of_this_profile_and_another_is_refused`: `refusal is None` (built).
  * `…every_version_that_differs_is_named…`: `'card-fingerprint-v3' in "…hspolicy26 was parsed by
    parser 2026.10.18-docx-4, and this build's parser is 2026.10.20-docx-6"`. The old code stopped
    at the parser.
  * Passing, as it should: `…an_occurrence_table_with_no_rows_names_no_profile_and_is_not_refused_for_one`
    (a must-not-refuse case) and the raw-read test of `profile_stamps_of_file`. That function is
    plumbing the skeleton added; on the start commit the test is a collection error, not a red.
* `.venv/bin/python -m pytest -p no:randomly -n 0 -q --tb=line packages/debate_cli/tests/commands/test_files.py -k refuses_a_store`
  → `1 failed, 1 passed`: the other-profile store exits 0 with `"status": "BUILT"`. The existing
  parser case passes.

The existing parser and fingerprint tests are unchanged:
`git diff ce5560e -- test_file_build_service.py test_files.py` removes two lines, one docstring
bullet and one import line, and no test line.

## Mutants

Agreement 8: each run used a new, empty `HYPOTHESIS_STORAGE_DIRECTORY`. None of these tests uses
Hypothesis. A script applied each mutant and ran
`.venv/bin/python -m pytest -q -p no:randomly --tb=no -rfE` over `test_file_build_service.py`,
`test_occurrence_table_guard.py` and the CLI's `test_files.py` (77 tests, about 5 s each). It then
restored the file and checked it byte for byte; `git status --porcelain` was empty after each batch.
A kill means pytest exited 1 with no collection error.

| Mutant | Result | Caught by |
|---|---|---|
| P1 compare the store's profiles with the parser version | KILLED (33 failed) | every test that builds |
| P2 no profile comparison | KILLED (4) | the four profile tests (service and CLI) |
| P3 read the profiles of generation 1, not the newest | KILLED (1) | `…another_style_profile_is_refused_once_before_resolving` |
| P4 `read_through = sorted(profiles) if profiles != {build} else []` | SURVIVED: equivalent | On an empty table it still gives `[]`, and on a mixed table it still refuses. I built this mutant badly, so P4b replaces it |
| P4b refuse a table whose profiles are not exactly `{build}`, an empty one too | KILLED (1) | `…an_occurrence_table_with_no_rows_names_no_profile…` |
| P5 judge the table by one row's profile (`min`) | KILLED (1) | `…a_table_holding_rows_of_this_profile_and_another…` |
| P6 stop at the parser when it differs | KILLED (1) | `…every_version_that_differs_is_named…` |
| P7 stop at the fingerprint when it differs | KILLED (1) | `…every_version_that_differs_is_named…` |
| P8 message leaves out the build's profile | KILLED (3) | service, all-differ, CLI |
| P9 message leaves out the store's profile | KILLED (4) | service, mixed, all-differ, CLI |
| P10 a profile-only difference adds no re-parse (so no refusal) | KILLED (3) | service, mixed, CLI |
| O1 store refusal after resolving | KILLED (8) | every `…before_resolving` test, both CLI refusals, the git-tree ordering test |
| O2 resolve once before the store refusal, then refuse as before | KILLED (10) | the `occurrence_reads == 0` assertions |
| O3 store refusal after the source lookup | KILLED (9) | as O1, plus the two-caselist test |
| O4 store refusal after the git working tree refusal | KILLED (1) | `test_the_version_refusal_comes_before_the_git_working_tree_refusal` (the existing parser case; the profile refusal shares its call) |
| R1 local adapter reads fingerprint stamps as profiles | KILLED (19) | every CLI build |
| R2 `profile_stamps` reads `parser_version` | KILLED (20) | the raw-read test and every CLI build |
| R3 the fake returns fingerprint versions as profiles | KILLED (18) | every service build |

18 runs: 17 killed and 1 equivalent survivor, replaced by P4b. O4 is caught only by the existing
parser-version ordering test. The profile refusal comes from the same call, so a profile-specific
copy would test nothing more.

## Files publish

`files publish`'s gate re-checks the file with `FileQualityService.check_file`. That service is
wired with a parser, the blob store and the suppression list, and has no `ParsedStore`
(`file_quality_service.py`, constructor and `check_file`). It re-parses each source from the blob
store and reads the card at the sidecar's element indices. It never resolves an occurrence, so it
does not meet the store mismatch. **No refusal was added there.** It meets a related one, written
up as follow-up 1.

## Files changed

* `debate_core/application/file_build_service.py`: takes `profile_version`. `_store_refusal` now
  asks `_versions_that_differ`, which compares parser, fingerprint and profile and names each that
  differs. Docstrings updated.
* `debate_core/application/ports/parsed_store.py`: `ParsedStore.read_occurrence_profiles`.
* `debate_core/application/caselist/occurrence_table_guard.py`: `profile_stamps` and
  `profile_stamps_of_file`, sharing one private `_stamps` reader with `fingerprint_stamps`, whose
  behaviour is unchanged.
* `debate_core/integrations/local/parsed_store.py`, `debate_core/testing/fakes/parsed_store.py`:
  the port method (Deviation 1).
* `debate_cli/container.py`: passes `parser.profile_version` to `FileBuildService`.
* Tests: `test_file_build_service.py` (four tests and the other-profile parser),
  `test_occurrence_table_guard.py` (one raw-read test), `test_files.py` (one CLI test),
  `test_file_publish_service.py` (passes the new argument).

## Deviations from the spec

1. **Two files outside `constraints.packages`.** The spec lists `debate_core.application`,
   `debate_cli` and their tests. The port's two implementations, `debate_core.integrations.local`
   (`LocalParsedStore`) and `debate_core.testing.fakes` (`InMemoryParsedStore`), each gained the one
   method the port gained (11 and 4 added lines, the adapter's including its import). Without them the port cannot grow, and the in-scope
   alternative (`read_index`, already on the port) is worse for the reason in Decision 1. I did not
   edit the spec's package list; the PM may want to add the two packages.

## Decisions and assumptions

1. **The occurrence table's rows, not the index, say the store's profile.** The resolver reads the
   rows and the writer finds cards at their element indices, so the rows' profile is the one that
   decides `OCCURRENCE_MISMATCH`. They are read from raw JSON. `read_index` would validate every
   entry through this build's model. The refusal now also reads another parser version's directory
   (Decision 2), whose records a newer build may have written in a shape this build rejects, and
   then the build would crash with `UnreadableParsedStore` instead of refusing. That is the reason
   `v1-e34-t29` read fingerprint stamps raw.
2. **Every version that differs is named, even when the parser differs.** Before, a directory of
   another parser version stopped the comparison at the parser. The PM asked for one refusal naming
   every version that differs, so the fingerprint and profile of that directory are now compared
   too. A directory of this parser version with no occurrence table is still `STORE_NOT_PARSED`. One
   of another parser version with no table names only the parser.
3. **An empty table names no profile and is not refused for one.** It has nothing to resolve, and
   refusing it would refuse every caselist a recipe pins before its first parse has rows (`testcl26`
   here). Pinned by a test and P4b.
4. **A mixed table is refused, naming each profile that is not the build's.** This cannot happen
   through the parse pipeline (Counted first), but it is checked the way the fingerprint stamps are
   (`stamps - {build}`), so a hand-edited or half-copied table does not pass on its first row (P5).
5. **The table is read twice** (fingerprint, then profile), 0.36 s each on hspolicy26. One combined
   read would have changed `read_occurrence_stamps`, whose other callers (the parse guard and the
   publish-only path) need only the fingerprint.
6. **The hint is unchanged.** A plain `caselist parse` re-parses a profile change: `_choose_version`
   starts a new generation when any entry's skip key has another profile. `--reparse` is not needed.

## Testing

Run once before the report, after the last change:

* `uv run scripts/affected_tests.py` → `318 of 521 test files (61.0%) chosen in 8.1 s from 12
  changed files`. The selection is large because `ports/parsed_store.py`, the guard module and the
  fake are imported widely. The whole selection takes about six minutes, so this set is over two.
  Under agreement 10 I did not run it or hand it to the operator; the PR's `ci` runs everything.
* What agreement 10 asks instead, the test directories of what changed and the always-run list:
  `.venv/bin/python -m pytest -n auto -q --tb=short -m "not slow and not live"` over
  `application/caselist/`, `test_file_build_service.py`, `test_file_publish_service.py`,
  `test_file_suggest_service.py`, `test_caselist_parse.py`, `integrations/test_local_parsed_store.py`,
  `integrations/test_parsed_store_schema_versions.py`, `integrations/local/`, the CLI's
  `commands/test_files.py` and `test_caselist_parse_newer_fingerprint_table.py`, `tests/architecture/`,
  `tests/specs/`, the CLI's `test_app.py` and `test_help_rendering.py` → `2365 passed in 99.34s`.
* `uv run --frozen ruff check .` → `All checks passed!`; `uv run --frozen ruff format --check .` →
  `1450 files already formatted`.
* `uv run pyright packages/debate_core packages/debate_cli` → `0 errors, 0 warnings, 0 informations`
  (after the last format; no source changed after it).
* `uv run --frozen lint-imports` → `Contracts: 18 kept, 0 broken.`;
  `uv run --frozen python scripts/check_thin_handlers.py` → `OK: 66 CLI command and API route
  handlers within 25 statements`.
* `uv run scripts/validate_specs.py` → `OK: 469 files, 40 epics, 407 tasks, 22 releases` (after the
  phase was set to Succeeded).

## Operator follow-ups

None.

## Follow-up work

1. **`files check` and `files publish` do not compare the sidecar's style profile** (E33, the
   quality checks of `v1-e33-t04`). The sidecar records `style_profile_version`
   (`domain/file_provenance.py`). `check_sidecar` (`evidence/file_checks/structure.py`) warns when
   the sidecar's parser version is not the running parser's, but says nothing about the profile. A
   file built under one profile and checked or published by a build with another gets per-card
   `evidence-identity` failures with no word on the cause, the same symptom this task removed from
   `files build`. The fix is a WARN beside the parser one, or a note like
   `rebuild_notes`. It is in `debate_core.evidence`, outside this task.
2. **The re-parse hint cannot tell an older profile from a newer one** (E31 parse pipeline or E33).
   Profile versions have no order, unlike fingerprint versions (`occurrence_table_guard`, "The
   order"). When the store's generation was read through a newer profile than the running build's,
   the hint still says "re-parse with this build". That starts `_reparse-<n+1>` under the older
   profile, which then becomes the caselist's current generation. The parse pipeline does the same
   with or without this hint. The parser-version case has the mirror problem: the existing "newer
   parser too" refusal's re-parse writes a directory that sorts below the newer one, so the build
   refuses again. Whether a newer store should say "install the newer build" instead is the PM's
   call.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
